"""Async GCS file reader for downloading chat attachments."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from google.cloud import storage
from google.oauth2 import service_account

from app.core.config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


def _build_storage_client() -> storage.Client:
    """Build a GCS client using service account JSON from config, or ADC."""
    if settings.GCS_CREDENTIALS_JSON:
        try:
            info = json.loads(settings.GCS_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(info)
            return storage.Client(
                credentials=credentials, project=info.get("project_id")
            )
        except Exception:
            logger.warning("Failed to parse GCS_CREDENTIALS_JSON, falling back to ADC")
    return storage.Client()


async def download_from_gcs(
    bucket_name: str, blob_path: str
) -> tuple[str, bytes] | None:
    """Download a file from GCS and return (filename, content).

    Returns None on error (non-fatal).
    """
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor, _download_sync, bucket_name, blob_path
        )
    except Exception:
        logger.warning(
            "GCS download failed: %s/%s", bucket_name, blob_path, exc_info=True
        )
        return None


def _download_sync(bucket_name: str, blob_path: str) -> tuple[str, bytes]:
    """Synchronous GCS download."""
    client = _build_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    content = blob.download_as_bytes()
    filename = blob_path.rsplit("/", 1)[-1]
    return filename, content
