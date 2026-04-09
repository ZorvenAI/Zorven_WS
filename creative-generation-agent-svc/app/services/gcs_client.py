"""GCS client for creative asset persistence."""

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Signed URL validity for images handed off to APA/Meta. 7 days is the
# max supported by v4 signing and comfortably longer than any WF3 run.
_SIGNED_URL_TTL = timedelta(days=7)


class GCSClient:
    """Async GCS client for image and creative package persistence.

    Supports 3 auth modes: JSON string, file path, ADC (Application Default
    Credentials). Returns empty strings in stub mode (no config).
    """

    def __init__(
        self,
        project_id: str = "",
        bucket_name: str = "",
        credentials_json: str = "",
        credentials_path: str = "",
    ) -> None:
        self._project_id = project_id
        self._bucket_name = bucket_name
        self._credentials_json = credentials_json
        self._credentials_path = credentials_path
        self._client: Any = None
        self._bucket: Any = None

    def _ensure_client(self) -> bool:
        """Lazy-init the GCS client."""
        if self._client is not None:
            return True
        if not self._bucket_name:
            return False
        try:
            from google.cloud import storage

            if self._credentials_json:
                from google.oauth2 import service_account

                info = json.loads(self._credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    info
                )
                self._client = storage.Client(
                    project=self._project_id, credentials=credentials
                )
            elif self._credentials_path:
                self._client = storage.Client.from_service_account_json(
                    self._credentials_path
                )
            else:
                self._client = storage.Client(project=self._project_id)
            self._bucket = self._client.bucket(self._bucket_name)
            return True
        except Exception as exc:
            logger.warning("GCS client init failed: %s", exc)
            return False

    async def upload_image(
        self,
        tenant_id: str,
        job_id: str,
        image_data: bytes,
        filename: str,
        content_type: str = "image/png",
    ) -> str:
        """Upload image bytes to GCS. Returns GCS URI or empty string."""
        if not self._ensure_client():
            logger.info("GCS not configured, returning data URI")
            if image_data and len(image_data) > 8:
                b64 = base64.b64encode(image_data).decode("ascii")
                return f"data:{content_type};base64,{b64}"
            return ""
        try:
            path = f"cga/{tenant_id}/{job_id}/images/{filename}"
            blob = self._bucket.blob(path)
            await asyncio.to_thread(
                blob.upload_from_string,
                image_data,
                content_type=content_type,
            )
            # Return an HTTPS signed URL so APA / Meta / the frontend can
            # fetch without needing GCS credentials. gs:// URIs are not
            # usable by httpx or the Meta Ads image upload endpoint.
            try:
                signed_url = await asyncio.to_thread(
                    blob.generate_signed_url,
                    version="v4",
                    expiration=_SIGNED_URL_TTL,
                    method="GET",
                )
                logger.info(
                    "Uploaded image to gs://%s/%s (signed URL issued)",
                    self._bucket_name,
                    path,
                )
                return signed_url
            except Exception as exc:
                # ADC / workload identity can't sign — fall back to the
                # public URL (works if the bucket is public) and log.
                logger.warning(
                    "GCS signed URL generation failed (%s); "
                    "returning unsigned public URL",
                    exc,
                )
                return (
                    f"https://storage.googleapis.com/"
                    f"{self._bucket_name}/{path}"
                )
        except Exception as exc:
            logger.warning("GCS image upload failed: %s", exc)
            return ""

    async def upload_package(
        self,
        tenant_id: str,
        job_id: str,
        package_data: dict[str, Any],
    ) -> str:
        """Upload creative package JSON to GCS. Returns GCS URI or empty string."""
        if not self._ensure_client():
            logger.info("GCS not configured, skipping package upload")
            return ""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = f"cga/{tenant_id}/{job_id}/package_{timestamp}.json"
            blob = self._bucket.blob(path)
            await asyncio.to_thread(
                blob.upload_from_string,
                json.dumps(package_data, default=str),
                content_type="application/json",
            )
            uri = f"gs://{self._bucket_name}/{path}"
            logger.info("Uploaded creative package to %s", uri)
            return uri
        except Exception as exc:
            logger.warning("GCS package upload failed: %s", exc)
            return ""

    async def download_package(self, package_path: str) -> dict[str, Any] | None:
        """Download a creative package from GCS."""
        if not self._ensure_client():
            return None
        try:
            blob = self._bucket.blob(package_path)
            data = await asyncio.to_thread(blob.download_as_text)
            return json.loads(data)
        except Exception as exc:
            logger.warning("GCS package download failed: %s", exc)
            return None

    async def get_public_url(self, gcs_uri: str) -> str:
        """Convert gs:// URI to a public URL (unsigned)."""
        if not gcs_uri.startswith("gs://"):
            return gcs_uri
        path = gcs_uri.replace(f"gs://{self._bucket_name}/", "")
        return f"https://storage.googleapis.com/{self._bucket_name}/{path}"
