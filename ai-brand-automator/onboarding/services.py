"""
Pipeline Integration Service for Onboarding.

This service integrates the onboarding module with the data pipeline,
publishing events to Kafka when brand assets are uploaded.
"""

import logging
import mimetypes
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from django.conf import settings

from onboarding.models import BrandAsset


logger = logging.getLogger(__name__)

# Explicit extension-to-MIME mapping — the system /etc/mime.types
# may be absent in Docker containers, so we cannot rely on
# mimetypes.guess_type() alone.
_EXTENSION_MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "csv": "text/csv",
    "html": "text/html",
    "md": "text/markdown",
}


def _guess_mime_type(filename: str) -> Optional[str]:
    """Reliably detect MIME type from a filename.

    Uses an explicit built-in mapping first, then falls back to
    Python's mimetypes module.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = _EXTENSION_MIME_MAP.get(ext)
    if mime:
        return mime
    guessed, _ = mimetypes.guess_type(filename)
    return guessed


class OnboardingPipelineService:
    """
    Service to integrate onboarding with the data pipeline.

    Publishes events to Kafka when:
    - Brand assets are uploaded (triggers ingestion pipeline)
    - Company data is updated (triggers RAG export)
    """

    def __init__(self):
        """Initialize the pipeline service."""
        self._producer = None
        self._kafka_enabled = getattr(settings, "ONBOARDING_KAFKA_ENABLED", True)

    @property
    def producer(self):
        """Lazy-load Kafka producer."""
        if self._producer is None and self._kafka_enabled:
            try:
                from data_ingestion.factory import create_kafka_producer

                self._producer = create_kafka_producer()
                logger.info("Kafka producer initialized for onboarding")
            except Exception as e:
                logger.warning(f"Failed to create Kafka producer: {e}")
                self._kafka_enabled = False
        return self._producer

    def publish_asset_event(self, asset: BrandAsset) -> Optional[str]:
        """
        Publish an asset upload event to the raw-ingestion-topic.

        Args:
            asset: The BrandAsset that was uploaded

        Returns:
            The trace_id if successful, None if failed
        """
        if not self._kafka_enabled:
            logger.info(
                "Kafka disabled — marking asset as ingested (sync fallback)",
                extra={"asset_id": asset.id},
            )
            asset.pipeline_status = "ingested"
            asset.save(update_fields=["pipeline_status"])
            return None

        try:
            trace_id = uuid4()
            event = self._build_ingestion_event(asset, trace_id)

            # Update asset with trace_id
            asset.pipeline_trace_id = trace_id
            asset.pipeline_status = "pending"
            asset.save(update_fields=["pipeline_trace_id", "pipeline_status"])

            # Publish to Kafka
            topic = self._get_input_topic()
            if self.producer is None:
                logger.error(
                    "Kafka producer is not available, cannot publish asset event",
                    extra={"asset_id": asset.id},
                )
                asset.pipeline_status = "failed"
                asset.pipeline_error = "Kafka producer is not available"
                asset.save(update_fields=["pipeline_status", "pipeline_error"])
                return None

            self.producer.publish_raw(topic, event, key=str(trace_id))

            logger.info(
                "Published asset event to Kafka",
                extra={
                    "asset_id": asset.id,
                    "trace_id": str(trace_id),
                    "topic": topic,
                },
            )

            return str(trace_id)

        except Exception as e:
            logger.error(
                f"Failed to publish asset event: {e}",
                extra={"asset_id": asset.id},
                exc_info=True,
            )
            # Mark asset as failed
            asset.pipeline_status = "failed"
            asset.pipeline_error = f"Failed to publish to Kafka: {str(e)}"
            asset.save(update_fields=["pipeline_status", "pipeline_error"])
            return None

    def _build_ingestion_event(self, asset: BrandAsset, trace_id) -> dict:
        """
        Build an ingestion event from a BrandAsset.

        Args:
            asset: The BrandAsset to create an event for
            trace_id: UUID for distributed tracing

        Returns:
            Dict representing the ingestion event
        """
        # Detect MIME type from filename
        mime_type = _guess_mime_type(asset.file_name)

        # Last-resort fallback based on file_type category
        if not mime_type:
            mime_type_map = {
                "image": "image/jpeg",
                "video": "video/mp4",
                "document": "application/octet-stream",
                "other": "application/octet-stream",
            }
            mime_type = mime_type_map.get(asset.file_type, "application/octet-stream")

        # Build the full GCS URI
        bucket = asset.gcs_bucket or self._get_default_bucket()
        gcs_uri = f"gs://{bucket}/{asset.gcs_path}"

        return {
            "event_id": str(uuid4()),
            "trace_id": str(trace_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "django-backend",
            "tenant_id": str(asset.tenant.id) if asset.tenant else "public",
            "file_path": gcs_uri,
            "file_type": mime_type,  # Use detected MIME type
            "file_size_bytes": asset.file_size,
            "metadata": {
                "original_filename": asset.file_name,
                "asset_id": asset.id,
                "company_id": asset.company.id if asset.company else None,
                "uploaded_at": asset.uploaded_at.isoformat(),
                "source_service": "onboarding",
            },
        }

    def _get_input_topic(self) -> str:
        """Get the Kafka input topic for ingestion events."""
        config = getattr(settings, "DATA_INGESTION", {})
        return config.get("KAFKA_INPUT_TOPIC", "raw-ingestion-topic")

    def _get_default_bucket(self) -> str:
        """Get the default GCS bucket name."""
        config = getattr(settings, "DATA_INGESTION", {})
        return config.get("GCP_BUCKET_NAME", "onboarding-brandsol-customer-bucket-1")

    def retry_asset_pipeline(self, asset: BrandAsset) -> Optional[str]:
        """
        Retry pipeline processing for a failed asset.

        Routes the retry to the appropriate pipeline stage based on what has
        already completed:
        - If the file is still in _landing/ (or has no path) → re-publish to
          the ingestion topic so the pipeline can re-run from the start
        - If the file has already been moved out of _landing/ (e.g. in raw/ or
          later stages, including curated) → publish directly to the curation
          topic so ingestion doesn't try to move an already-moved file

        Args:
            asset: The BrandAsset to retry

        Returns:
            The new trace_id if successful, None if failed
        """
        if asset.pipeline_status not in ("failed", "pending"):
            logger.warning(
                f"Cannot retry asset {asset.id} with status {asset.pipeline_status}"
            )
            return None

        # Reset error and re-publish
        asset.pipeline_error = ""
        asset.save(update_fields=["pipeline_error"])

        gcs_path = asset.gcs_path or ""

        # Determine which stage to retry from based on gcs_path location
        if not gcs_path or "_landing/" in gcs_path:
            # File still in landing zone (or no path) — start from ingestion
            return self.publish_asset_event(asset)

        if "/raw/" in gcs_path:
            # File is already in raw/ zone — skip ingestion, publish to curation
            return self._publish_curation_event(asset)

        # Path is neither landing nor clearly raw (e.g., legacy assets/ paths);
        # treat as not-yet-ingested and route through ingestion.
        logger.warning(
            "Ambiguous gcs_path for asset %s during retry (%s); "
            "falling back to ingestion pipeline.",
            asset.id,
            gcs_path,
        )
        return self.publish_asset_event(asset)

    def _publish_curation_event(self, asset: BrandAsset) -> Optional[str]:
        """
        Publish an event directly to the curation-needed topic.

        Used when retrying a failed asset that has already been ingested
        (file is in raw/ zone), so ingestion can be skipped.

        Args:
            asset: The BrandAsset to publish for curation

        Returns:
            The new trace_id if successful, None if failed
        """
        if not self._kafka_enabled:
            logger.info(
                "Kafka disabled — cannot publish curation event",
                extra={"asset_id": asset.id},
            )
            return None

        try:
            trace_id = uuid4()

            # Detect MIME type
            mime_type = _guess_mime_type(asset.file_name)
            if not mime_type:
                mime_type_map = {
                    "image": "image/jpeg",
                    "video": "video/mp4",
                    "document": "application/octet-stream",
                    "other": "application/octet-stream",
                }
                mime_type = mime_type_map.get(
                    asset.file_type, "application/octet-stream"
                )

            bucket = asset.gcs_bucket or self._get_default_bucket()
            raw_gcs_uri = f"gs://{bucket}/{asset.gcs_path}"

            event = {
                "event_id": str(uuid4()),
                "trace_id": str(trace_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tenant_id": str(asset.tenant.id) if asset.tenant else "public",
                "source_path": raw_gcs_uri,
                "destination_path": raw_gcs_uri,
                "status": "raw_stored",
                "processing_duration_ms": 0,
                # Curation-expected fields
                "file_id": str(uuid4()),
                "raw_gcs_uri": raw_gcs_uri,
                "mime_type": mime_type,
                "content_type": "unknown",
                "source_service": "data-ingestion",
                "metadata": {
                    "original_filename": asset.file_name,
                    "asset_id": asset.id,
                    "company_id": asset.company.id if asset.company else None,
                    "uploaded_at": asset.uploaded_at.isoformat(),
                    "source_service": "onboarding",
                    "file_size_bytes": asset.file_size,
                },
            }

            # Update asset with new trace_id
            asset.pipeline_trace_id = trace_id
            asset.pipeline_status = "ingested"  # Already ingested, going to curation
            asset.save(
                update_fields=["pipeline_trace_id", "pipeline_status", "pipeline_error"]
            )

            # Publish directly to curation topic
            config = getattr(settings, "DATA_INGESTION", {})
            curation_topic = config.get("KAFKA_OUTPUT_TOPIC", "curation-needed-topic")

            if self.producer is None:
                logger.error(
                    "Kafka producer not available for curation retry",
                    extra={"asset_id": asset.id},
                )
                asset.pipeline_status = "failed"
                asset.pipeline_error = "Kafka producer is not available"
                asset.save(update_fields=["pipeline_status", "pipeline_error"])
                return None

            self.producer.publish_raw(curation_topic, event, key=str(trace_id))

            logger.info(
                "Published curation retry event (skipping ingestion)",
                extra={
                    "asset_id": asset.id,
                    "trace_id": str(trace_id),
                    "topic": curation_topic,
                    "raw_gcs_uri": raw_gcs_uri,
                },
            )

            return str(trace_id)

        except Exception as e:
            logger.error(
                f"Failed to publish curation retry event: {e}",
                extra={"asset_id": asset.id},
                exc_info=True,
            )
            asset.pipeline_status = "failed"
            asset.pipeline_error = f"Failed to publish curation retry: {str(e)}"
            asset.save(update_fields=["pipeline_status", "pipeline_error"])
            return None

    def publish_company_document(self, company_doc: dict) -> str:
        """
        Publish a company document to the RAG sync topic.

        Args:
            company_doc: The structured company document for RAG indexing.

        Returns:
            The trace_id for the published document.

        Raises:
            Exception: If publishing fails.
        """
        trace_id = uuid4()
        topic = self._get_rag_topic()

        # Enrich the document with trace info
        event = {
            "event_id": str(uuid4()),
            "trace_id": str(trace_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "onboarding-company-export",
            **company_doc,
        }

        if not self._kafka_enabled:
            logger.info(
                "Kafka disabled, would publish company document",
                extra={
                    "company_id": company_doc.get("company_id"),
                    "trace_id": str(trace_id),
                },
            )
            return trace_id

        try:
            if self.producer is None:
                logger.error(
                    "Kafka producer is not available, cannot publish company document",
                    extra={"company_id": company_doc.get("company_id")},
                )
                raise RuntimeError("Kafka producer is not available")

            self.producer.publish_raw(topic, event, key=str(trace_id))
            logger.info(
                "Published company document to RAG topic",
                extra={
                    "company_id": company_doc.get("company_id"),
                    "trace_id": str(trace_id),
                    "topic": topic,
                },
            )
            return trace_id
        except Exception as e:
            logger.error(
                f"Failed to publish company document: {e}",
                extra={"company_id": company_doc.get("company_id")},
                exc_info=True,
            )
            raise

    def _get_rag_topic(self) -> str:
        """Get the Kafka topic for RAG sync events."""
        config = getattr(settings, "DATA_INGESTION", {})
        return config.get("KAFKA_RAG_TOPIC", "rag-sync-ready-topic")

    def setup_tenant_pipeline_config(self, tenant_id: int | str) -> dict:
        """
        Set up default pipeline configuration for a new tenant.

        Creates Redis configuration entries that the data pipeline services
        use to customize behavior per tenant.

        Args:
            tenant_id: The tenant ID to configure.

        Returns:
            Dict with the configuration that was set.
        """
        from django.core.cache import cache

        tenant_id_str = str(tenant_id)

        # Default pipeline configuration for new tenants
        default_config = {
            "enabled": True,
            "auto_curation": True,
            "rag_indexing": True,
            "retention_days": 90,
            "max_file_size_mb": 50,
            "allowed_file_types": ["image", "video", "document"],
        }

        # Store in Redis with tenant-specific key
        config_key = f"pipeline:tenant:{tenant_id_str}:config"

        try:
            cache.set(config_key, default_config, timeout=None)  # No expiry
            logger.info(
                f"Set up pipeline config for tenant {tenant_id_str}",
                extra={"config_key": config_key, "config": default_config},
            )
        except Exception as e:
            # Log but don't fail - pipeline will use defaults
            logger.warning(
                f"Failed to set pipeline config for tenant {tenant_id_str}: {e}"
            )

        return default_config

    def get_tenant_pipeline_config(self, tenant_id: int | str) -> dict:
        """
        Get pipeline configuration for a tenant.

        Args:
            tenant_id: The tenant ID to get config for.

        Returns:
            Dict with the tenant's pipeline configuration, or defaults.
        """
        from django.core.cache import cache

        tenant_id_str = str(tenant_id)
        config_key = f"pipeline:tenant:{tenant_id_str}:config"

        try:
            config = cache.get(config_key)
            if config:
                return config
        except Exception as e:
            logger.warning(f"Failed to get pipeline config: {e}")

        # Return defaults if not found
        return {
            "enabled": True,
            "auto_curation": True,
            "rag_indexing": True,
            "retention_days": 90,
            "max_file_size_mb": 50,
            "allowed_file_types": ["image", "video", "document"],
        }


# Singleton instance for use across the application
_pipeline_service: Optional[OnboardingPipelineService] = None


def get_pipeline_service() -> OnboardingPipelineService:
    """Get or create the singleton pipeline service instance."""
    global _pipeline_service
    if _pipeline_service is None:
        _pipeline_service = OnboardingPipelineService()
    return _pipeline_service
