"""
Curation Service - Main Orchestrator.

This module contains the CurationService class which orchestrates
the entire media curation pipeline following the Hexagonal Architecture pattern.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from media_curation.domain.models import (
    CurationEvent,
    TenantConfig,
    ProcessorResult,
    CuratedDocument,
    CurationStatusRecord,
    CurationStatus,
    DocumentMetadata,
)
from media_curation.domain.schemas import (
    CurationCompletedEvent,
    CurationFailedEvent,
)
from media_curation.domain.exceptions import (
    RetryableError,
    NonRetryableError,
    ProcessorNotFoundError,
    StorageError,
    AIModelError,
)
from media_curation.ports.ai_port import ContentProcessorPort
from media_curation.ports.dlp_port import DLPPort
from media_curation.ports.storage_port import StoragePort
from media_curation.ports.cache_port import CachePort
from media_curation.ports.event_port import EventProducerPort


logger = logging.getLogger(__name__)


class ProcessorFactory:
    """
    Strategy selector based on MIME type.

    Implements the Factory pattern to select the appropriate
    content processor based on the input MIME type.
    """

    def __init__(self, processors: list[ContentProcessorPort]):
        """
        Initialize with a list of content processors.

        Args:
            processors: List of ContentProcessorPort implementations
        """
        self.processors = processors

    def get_processor(self, mime_type: str) -> ContentProcessorPort:
        """
        Get the appropriate processor for a MIME type.

        Args:
            mime_type: The MIME type to find a processor for

        Returns:
            A ContentProcessorPort that supports the MIME type

        Raises:
            ProcessorNotFoundError: If no processor supports the MIME type
        """
        for processor in self.processors:
            if processor.supports(mime_type):
                return processor
        raise ProcessorNotFoundError(
            f"No processor available for MIME type: {mime_type}"
        )

    def list_supported_types(self) -> list[str]:
        """
        Get all supported MIME types across all processors.

        Returns:
            List of supported MIME type patterns
        """
        supported = []
        for processor in self.processors:
            supported.extend(getattr(processor, "SUPPORTED_MIME_TYPES", []))
        return supported


class CurationService:
    """
    Main orchestrator for media curation pipeline.

    This service coordinates the entire curation flow:
    1. Fetch tenant config from cache
    2. Select processor via Factory (Strategy pattern)
    3. Extract text from media
    4. Optionally redact PII based on tenant config
    5. Build CuratedDocument
    6. Save to GCS
    7. Publish rag-sync-ready event
    8. Update status in cache

    Follows the Hexagonal Architecture pattern where all external
    dependencies are injected through port interfaces.
    """

    def __init__(
        self,
        processor_factory: ProcessorFactory,
        dlp: DLPPort,
        storage: StoragePort,
        cache: CachePort,
        producer: EventProducerPort,
        output_topic: str,
        dlq_topic: str,
        output_bucket: str,
    ):
        """
        Initialize the curation service with dependencies.

        Args:
            processor_factory: Factory to select content processors
            dlp: DLP port for PII redaction
            storage: Storage port for saving curated documents
            cache: Cache port for status tracking and tenant config
            producer: Event producer for publishing events
            output_topic: Kafka topic for successful curation events
            dlq_topic: Kafka topic for failed events (DLQ)
            output_bucket: GCS bucket for curated documents
        """
        self.processor_factory = processor_factory
        self.dlp = dlp
        self.storage = storage
        self.cache = cache
        self.producer = producer
        self.output_topic = output_topic
        self.dlq_topic = dlq_topic
        self.output_bucket = output_bucket

    def process_event(self, event: CurationEvent) -> CuratedDocument:
        """
        Process a single curation event through the pipeline.

        Args:
            event: The curation event to process

        Returns:
            The curated document result

        Raises:
            ProcessorNotFoundError: If no processor supports the MIME type
            ConfigurationError: If tenant config is invalid
            AIModelError: If AI processing fails
            StorageError: If saving to GCS fails

        Note:
            DLP (PII redaction) errors are non-fatal and handled internally.
            Curation continues with original text if DLP fails.
        """
        trace_id = str(event.trace_id)
        logger.info(
            "Starting curation",
            extra={
                "event_id": str(event.event_id),
                "trace_id": trace_id,
                "tenant_id": event.tenant_id,
                "file_id": str(event.file_id),
                "mime_type": event.mime_type,
            },
        )

        # Update status to PROCESSING
        self._update_status(
            event,
            CurationStatus.PROCESSING,
            message="Starting content extraction",
        )

        try:
            # 1. Fetch tenant config
            tenant_config = self._get_tenant_config(event.tenant_id)

            # 2. Select processor via Strategy pattern
            processor = self.processor_factory.get_processor(event.mime_type)
            logger.debug(
                f"Selected processor: {processor.__class__.__name__}",
                extra={"trace_id": trace_id},
            )

            # 3. Extract text from media
            self._update_status(
                event,
                CurationStatus.PROCESSING,
                message="Extracting content from media",
            )
            # Call async processor in sync context
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                processor_result = loop.run_until_complete(
                    processor.process(
                        event=event,
                        tenant_config=tenant_config,
                    )
                )
            finally:
                loop.close()

            # 4. Optionally redact PII
            extracted_text = processor_result.extracted_text
            pii_detected = False

            if tenant_config.dlp_enabled and extracted_text and self.dlp:
                self._update_status(
                    event,
                    CurationStatus.PROCESSING,
                    message="Scanning for PII",
                )
                redacted_text, pii_detected = self._redact_pii(
                    extracted_text,
                    tenant_config,
                )
                extracted_text = redacted_text

            # 5. Build CuratedDocument
            curated_doc = self._build_curated_document(
                event=event,
                extracted_text=extracted_text,
                processor_result=processor_result,
                pii_redacted=pii_detected,
            )

            # 6. Save to GCS
            self._update_status(
                event,
                CurationStatus.PROCESSING,
                message="Saving curated document",
            )
            output_uri = self._save_to_storage(curated_doc)
            curated_doc = curated_doc.model_copy(update={"output_gcs_uri": output_uri})

            # 7. Publish rag-sync-ready event
            self._publish_success_event(event, curated_doc)

            # 8. Update status to CURATED
            self._update_status(
                event,
                CurationStatus.CURATED,
                message="Curation completed successfully",
                output_uri=output_uri,
            )

            logger.info(
                "Curation completed",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": trace_id,
                    "output_uri": output_uri,
                },
            )

            return curated_doc

        except ProcessorNotFoundError as e:
            # Non-retryable - no processor for this MIME type
            self._handle_failure(event, e, retryable=False)
            raise

        except AIModelError as e:
            # May be retryable depending on the error
            is_retryable = isinstance(e, RetryableError)
            self._handle_failure(event, e, retryable=is_retryable)
            raise

        except StorageError as e:
            # Storage errors are typically retryable
            self._handle_failure(event, e, retryable=True)
            raise

        except RetryableError as e:
            # Retryable errors are re-raised for Celery retry mechanism
            self._handle_failure(event, e, retryable=True)
            raise

        except NonRetryableError as e:
            # Non-retryable errors go straight to DLQ
            self._handle_failure(event, e, retryable=False)
            raise

        except Exception as e:
            # Unexpected error - send to DLQ
            logger.exception(
                "Unexpected error during curation",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": trace_id,
                },
            )
            self._handle_failure(event, e, retryable=False)
            raise NonRetryableError(f"Unexpected error: {e}") from e

    def process_with_retry(
        self,
        event: CurationEvent,
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
    ) -> Optional[CuratedDocument]:
        """
        Process event with retry logic and DLQ handling.

        Args:
            event: The curation event to process
            max_retries: Maximum retry attempts
            backoff_seconds: Initial backoff delay (doubles each retry)

        Returns:
            CuratedDocument if successful, None if failed and sent to DLQ
        """
        import time

        retry_count = 0
        backoff = backoff_seconds

        while retry_count <= max_retries:
            try:
                return self.process_event(event)

            except RetryableError as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(
                        "Max retries exceeded, sending to DLQ",
                        extra={
                            "event_id": str(event.event_id),
                            "trace_id": str(event.trace_id),
                            "retry_count": retry_count,
                        },
                    )
                    self._send_to_dlq(event, e)
                    return None

                logger.warning(
                    f"Retrying after {backoff}s (attempt {retry_count}/{max_retries})",
                    extra={
                        "event_id": str(event.event_id),
                        "trace_id": str(event.trace_id),
                        "error": str(e),
                    },
                )
                time.sleep(backoff)
                backoff *= 2

            except NonRetryableError as e:
                logger.error(
                    "Non-retryable error, sending to DLQ",
                    extra={
                        "event_id": str(event.event_id),
                        "trace_id": str(event.trace_id),
                        "error": str(e),
                    },
                )
                self._send_to_dlq(event, e)
                return None

    def get_status(
        self, trace_id: UUID, tenant_id: Optional[str] = None
    ) -> Optional[CurationStatusRecord]:
        """
        Get the current status of a curation job.

        Args:
            trace_id: The trace ID to look up
            tenant_id: Optional tenant ID for key namespacing

        Returns:
            CurationStatusRecord if found, None otherwise
        """
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.cache.get_status(str(trace_id), tenant_id=tenant_id)
            )
        finally:
            loop.close()

    def _get_tenant_config(self, tenant_id: UUID) -> TenantConfig:
        """Fetch tenant configuration from cache or use defaults."""
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            config = loop.run_until_complete(
                self.cache.get_tenant_config(str(tenant_id))
            )
        finally:
            loop.close()

        if config:
            return config

        # Return default config if not found
        logger.debug(
            "No tenant config found, using defaults",
            extra={"tenant_id": str(tenant_id)},
        )
        return TenantConfig(tenant_id=tenant_id)

    def _redact_pii(
        self,
        text: str,
        tenant_config: TenantConfig,
    ) -> tuple[str, bool]:
        """
        Redact PII from text using async DLP port.

        Args:
            text: Text to scan and redact
            tenant_config: Tenant configuration with PII settings

        Returns:
            Tuple of (redacted_text, pii_was_detected)
        """
        import asyncio

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.dlp.redact_pii(
                        text=text,
                        tenant_config=tenant_config,
                    )
                )
            finally:
                loop.close()

            return result.redacted_text, result.has_pii
        except Exception:
            # DLP is non-fatal: log with traceback and continue with original text
            logger.warning(
                "DLP redaction failed, continuing curation without PII redaction",
                exc_info=True,
            )
            return text, False

    def _build_curated_document(
        self,
        event: CurationEvent,
        extracted_text: str,
        processor_result: ProcessorResult,
        pii_redacted: bool,
    ) -> CuratedDocument:
        """Build the curated document from processing results."""
        return CuratedDocument(
            document_id=uuid4(),
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            file_id=event.file_id,
            source_gcs_uri=event.raw_gcs_uri,
            output_gcs_uri=None,  # Will be set after saving
            mime_type=event.mime_type,
            extracted_text=extracted_text,
            struct_data=processor_result.struct_data,
            pii_redacted=pii_redacted,
            processing_time_ms=processor_result.processing_time_ms,
            metadata=DocumentMetadata(
                original_filename=event.metadata.get("filename")
                if event.metadata
                else None,
                file_size_bytes=event.metadata.get("file_size")
                if event.metadata
                else None,
                content_type=event.mime_type,
                word_count=len(extracted_text.split()) if extracted_text else 0,
                language_code=processor_result.language_code,
            ),
            created_at=datetime.now(timezone.utc),
        )

    def _save_to_storage(self, doc: CuratedDocument) -> str:
        """Save curated document to GCS and return the URI."""
        import asyncio
        import json

        try:
            # Build the output path
            path = (
                f"gs://{self.output_bucket}/curated/"
                f"{doc.tenant_id}/{doc.file_id}/{doc.document_id}.json"
            )

            # Convert to JSON bytes
            doc_data = doc.model_dump(mode="json")
            content = json.dumps(doc_data, indent=2).encode("utf-8")

            # Save to storage using async upload_from_bytes
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                file_info = loop.run_until_complete(
                    self.storage.upload_from_bytes(
                        content=content,
                        destination_path=path,
                        content_type="application/json",
                        metadata={"document_id": str(doc.document_id)},
                    )
                )
            finally:
                loop.close()

            return file_info.path

        except Exception as e:
            logger.error(f"Failed to save to storage: {e}")
            raise StorageError(f"Failed to save curated document: {e}") from e

    def _publish_success_event(
        self,
        event: CurationEvent,
        doc: CuratedDocument,
    ) -> None:
        """Publish a rag-sync-ready event."""
        try:
            output_event = CurationCompletedEvent(
                id=str(uuid4()),
                source="media-curation-svc",
                type="brandsol.curation.completed.v1",
                datacontenttype="application/json",
                time=datetime.now(timezone.utc),
                subject=f"tenant:{event.tenant_id}/file:{event.file_id}",
                traceid=str(event.trace_id),
                data={
                    "trace_id": str(event.trace_id),
                    "tenant_id": event.tenant_id,
                    "file_id": str(event.file_id),
                    "document_id": str(doc.document_id),
                    "curated_gcs_uri": doc.output_gcs_uri,
                    # Alias for rag-index compatibility
                    "processed_gcs_uri": doc.output_gcs_uri,
                    "mime_type": doc.mime_type,
                    "pii_redacted": doc.pii_redacted,
                    "action": "UPSERT",  # Required by rag-index consumer
                    "metadata": event.metadata
                    or {},  # Pass through metadata (includes asset_id)
                },
            )
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.producer.publish_raw(
                        topic=self.output_topic,
                        payload=output_event.model_dump(mode="json"),
                        key=event.tenant_id,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to publish success event: {e}")
            raise

    def _handle_failure(
        self,
        event: CurationEvent,
        error: Exception,
        retryable: bool,
    ) -> None:
        """Handle a processing failure."""
        self._update_status(
            event,
            CurationStatus.FAILED,
            message=str(error),
            error_code=error.__class__.__name__,
        )

        if not retryable:
            self._send_to_dlq(event, error)

    def _send_to_dlq(self, event: CurationEvent, error: Exception) -> None:
        """Send failed event to dead letter queue."""
        import asyncio

        try:
            failed_event = CurationFailedEvent(
                id=str(uuid4()),
                source="media-curation-svc",
                type="brandsol.curation.failed.v1",
                datacontenttype="application/json",
                time=datetime.now(timezone.utc),
                subject=f"tenant:{event.tenant_id}/file:{event.file_id}",
                traceid=str(event.trace_id),
                data={
                    "trace_id": str(event.trace_id),
                    "tenant_id": event.tenant_id,
                    "file_id": str(event.file_id),
                    "raw_gcs_uri": event.raw_gcs_uri,
                    "mime_type": event.mime_type,
                    "error_code": error.__class__.__name__,
                    "error_message": str(error),
                    "retry_count": getattr(event, "retry_count", 0),
                },
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.producer.publish_raw(
                        topic=self.dlq_topic,
                        payload=failed_event.model_dump(mode="json"),
                        key=event.tenant_id,
                    )
                )
            finally:
                loop.close()
            logger.info(
                "Event sent to DLQ",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": str(event.trace_id),
                    "dlq_topic": self.dlq_topic,
                },
            )
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")

    def _update_status(
        self,
        event: CurationEvent,
        status: CurationStatus,
        message: str = "",
        output_uri: str = None,
        error_code: str = None,
    ) -> None:
        """Update curation status in cache."""
        import asyncio

        try:
            status_record = CurationStatusRecord(
                trace_id=event.trace_id,
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                file_id=event.file_id,
                status=status,
                message=message,
                output_gcs_uri=output_uri,
                error_code=error_code,
                updated_at=datetime.now(timezone.utc),
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.cache.set_status(
                        str(event.trace_id),
                        status_record,
                        ttl_seconds=604800,  # 7 days
                        tenant_id=event.tenant_id,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            logger.warning(f"Failed to update status: {e}")
