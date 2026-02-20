"""
File handler — GCS upload and data ingestion handoff.

When the discovery agent encounters a downloadable file (PDF/Excel),
this handler uploads it to GCS _landing/ and emits an IngestionEvent
to raw-ingestion-topic for the data-ingestion pipeline.

In stub mode (no GCS credentials), returns a source reference
without uploading.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from app.api.schemas import SourceItem

logger = logging.getLogger(__name__)


class FileHandler:
    """Handles downloadable files: upload to GCS, emit ingestion event."""

    def __init__(
        self,
        gcs_project_id: str = "",
        gcs_bucket: str = "",
        gcs_credentials_path: str = "",
        kafka_producer: Any = None,
    ) -> None:
        self.gcs_project_id = gcs_project_id
        self.gcs_bucket = gcs_bucket
        self.gcs_credentials_path = gcs_credentials_path
        self.kafka_producer = kafka_producer
        self._gcs_client: Any = None
        self._stub_mode = not (gcs_project_id and gcs_bucket)

        if self._stub_mode:
            logger.info("FileHandler in stub mode (no GCS credentials)")

    def _get_gcs_client(self) -> Any:
        """Lazily initialize GCS client."""
        if self._gcs_client is None and not self._stub_mode:
            try:
                from google.cloud import storage

                if self.gcs_credentials_path:
                    self._gcs_client = storage.Client.from_service_account_json(
                        self.gcs_credentials_path,
                        project=self.gcs_project_id,
                    )
                else:
                    self._gcs_client = storage.Client(project=self.gcs_project_id)
            except Exception as exc:
                logger.error("Failed to initialize GCS client: %s", exc)
                self._stub_mode = True
        return self._gcs_client

    async def handle_downloadable(
        self,
        url: str,
        content_type: str,
        content_bytes: bytes,
        tenant_id: str,
        job_id: str = "",
    ) -> SourceItem:
        """
        Handle a downloadable file: upload to GCS and emit ingestion event.

        In stub mode, returns a SourceItem pointing to the original URL.
        """
        filename = PurePosixPath(url.split("?")[0]).name or "unknown_file"
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        gcs_path = f"gs://{self.gcs_bucket}/_landing/{unique_filename}"

        # Upload to GCS
        if not self._stub_mode:
            try:
                client = self._get_gcs_client()
                if client:
                    bucket = client.bucket(self.gcs_bucket)
                    blob = bucket.blob(f"_landing/{unique_filename}")
                    blob.upload_from_string(content_bytes, content_type=content_type)
                    logger.info("Uploaded %s to %s", filename, gcs_path)
                else:
                    logger.warning("GCS client unavailable, skipping upload")
                    gcs_path = url
            except Exception as exc:
                logger.error("GCS upload failed for %s: %s", url, exc)
                gcs_path = url
        else:
            logger.debug("Stub mode: skipping GCS upload for %s", url)
            gcs_path = url

        # Emit ingestion event
        await self._emit_ingestion_event(
            gcs_path=gcs_path,
            content_type=content_type,
            content_size=len(content_bytes),
            tenant_id=tenant_id,
            job_id=job_id,
            source_url=url,
        )

        return SourceItem(
            type="document",
            title=filename,
            url=gcs_path,
        )

    async def _emit_ingestion_event(
        self,
        gcs_path: str,
        content_type: str,
        content_size: int,
        tenant_id: str,
        job_id: str,
        source_url: str,
    ) -> None:
        """Emit an IngestionEvent to raw-ingestion-topic."""
        if self.kafka_producer is None:
            logger.debug("No Kafka producer, skipping ingestion event")
            return

        event = {
            "event_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "api-integration",
            "tenant_id": tenant_id,
            "file_path": gcs_path,
            "file_type": content_type,
            "file_size_bytes": content_size,
            "metadata": {
                "source_url": source_url,
                "job_id": job_id,
            },
        }

        try:
            if (
                hasattr(self.kafka_producer, "_producer")
                and self.kafka_producer._producer
            ):
                await self.kafka_producer._producer.send_and_wait(
                    "raw-ingestion-topic",
                    json.dumps(event).encode("utf-8"),
                )
                logger.info("Ingestion event emitted for %s", gcs_path)
            else:
                logger.debug("Kafka producer not connected, skipping ingestion event")
        except Exception as exc:
            logger.warning("Failed to emit ingestion event: %s", exc)
