"""
File Storage Services for Zorven AI
Integration with Google Cloud Storage
"""

import json
import os
import time
import logging
from datetime import timedelta
import google.auth
from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.full_control"]

# MIME types that browsers can display inline (used by generate_signed_url)
_BROWSER_VIEWABLE_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "text/plain",
    "text/html",
    "text/csv",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
}

# Explicit extension → MIME map for reliable content-type on signed URLs
_EXTENSION_CONTENT_TYPE = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument" ".wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": ("application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet"),
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument" ".presentationml.presentation"
    ),
}


class GCSService:
    """
    Service for interacting with Google Cloud Storage.

    Credentials are resolved in order:
    1. GCS_CREDENTIALS_JSON env var (inline JSON - for Railway/Heroku)
    2. GS_CREDENTIALS_PATH file on disk (local dev with service account key)
    3. Application Default Credentials (GCP-hosted environments)
    """

    def __init__(self):
        self.bucket_name = settings.GS_BUCKET_NAME
        self.project_id = settings.GS_PROJECT_ID
        self.credentials_path = settings.GS_CREDENTIALS_PATH

        # Initialize GCS client
        self._init_error = None
        try:
            credentials = self._resolve_credentials()
            self.client = storage.Client(
                credentials=credentials, project=self.project_id
            )
        except Exception as e:
            self._init_error = str(e)
            # Use print() because logging may not be configured yet
            # at module import time
            print(
                f"[GCS] WARNING: Initialization failed: {e}. "
                f"File uploads will not work."
            )
            logger.warning("GCS initialization failed: %s. Using mock service.", e)
            self.client = None

        if self.client:
            self.bucket = self.client.bucket(self.bucket_name)
            print(
                f"[GCS] OK: project={self.project_id} "
                f"bucket={self.bucket_name}"
            )
            logger.info(
                "GCS service initialized: project=%s bucket=%s",
                self.project_id,
                self.bucket_name,
            )
        else:
            self.bucket = None
            print(
                f"[GCS] ERROR: GCS not available. "
                f"bucket={self.bucket_name} project={self.project_id} "
                f"error={self._init_error}"
            )
            logger.error(
                "GCS service NOT available — file uploads will fail. "
                "Set GCS_CREDENTIALS_JSON env var. (bucket=%s, project=%s, "
                "error=%s)",
                self.bucket_name,
                self.project_id,
                self._init_error,
            )

    def get_bucket(self, bucket_name=None):
        """Return a GCS bucket object.

        If *bucket_name* is provided, return that bucket.
        Otherwise return the default bucket configured at init time.

        Args:
            bucket_name: Optional override bucket name.

        Returns:
            A ``google.cloud.storage.Bucket`` or *None* if no GCS client.
        """
        if bucket_name and self.client:
            return self.client.bucket(bucket_name)
        return self.bucket

    def _resolve_credentials(self):
        """Resolve GCS credentials from env var, file, or return None for ADC."""
        # 1. Inline JSON from environment variable (Railway / Heroku / CI)
        creds_json = os.environ.get("GCS_CREDENTIALS_JSON", "").strip()
        if creds_json:
            print(f"[GCS] Loading credentials from GCS_CREDENTIALS_JSON ({len(creds_json)} chars)")
            try:
                info = json.loads(creds_json)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=GCS_SCOPES
                )
                print(f"[GCS] Credentials loaded: {info.get('client_email', '?')}")
                return creds
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[GCS] Invalid GCS_CREDENTIALS_JSON: {e}")
                logger.warning(
                    "Invalid GCS_CREDENTIALS_JSON env var; falling back: %s", e
                )

        # 2. Service account key file on disk (local development)
        if self.credentials_path and os.path.exists(self.credentials_path):
            print(f"[GCS] Loading credentials from file: {self.credentials_path}")
            return service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=GCS_SCOPES
            )

        # 3. Fall back to Application Default Credentials (with explicit scopes)
        print("[GCS] No explicit credentials found, trying ADC")
        credentials, project = google.auth.default(scopes=GCS_SCOPES)
        return credentials

    def upload_file(
        self, file_obj, file_path, content_type=None, max_retries=3, bucket_name=None
    ):
        """
        Upload a file to Google Cloud Storage with retry logic.

        Args:
            file_obj: File object to upload.
            file_path: Path in GCS where to store the file.
            content_type: MIME type of the file.
            max_retries: Maximum number of retry attempts (default: 3).
            bucket_name: Optional bucket override (for per-tenant routing).

        Returns:
            str: Public URL of the uploaded file.
        """
        target_bucket = self.get_bucket(bucket_name)
        target_name = bucket_name or self.bucket_name

        if not target_bucket:
            # Mock upload for development
            return f"https://storage.googleapis.com/{target_name}/{file_path}"

        last_error = None
        for attempt in range(max_retries):
            try:
                blob = target_bucket.blob(file_path)

                # Set content type if provided
                if content_type:
                    blob.content_type = content_type

                # Reset file position for retry attempts
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)

                # Upload the file
                blob.upload_from_file(file_obj, content_type=content_type)

                # Not calling make_public() - bucket uses uniform bucket-level access
                # Access is controlled via IAM policies at bucket level
                logger.info(f"Successfully uploaded file to GCS: {file_path}")
                return blob.public_url

            except Exception as e:
                last_error = e
                wait_time = (2**attempt) + 1  # Exponential backoff: 2, 3, 5 seconds
                logger.warning(
                    f"GCS upload attempt {attempt + 1}/{max_retries} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                if attempt < max_retries - 1:
                    time.sleep(wait_time)

        raise Exception(
            f"Failed to upload to GCS after {max_retries} attempts: {last_error}"
        )

    def delete_file(self, file_path, bucket_name=None):
        """
        Delete a file from Google Cloud Storage.

        Args:
            file_path: Path of the file to delete.
            bucket_name: Optional bucket override (for per-tenant routing).
        """
        try:
            target_bucket = self.get_bucket(bucket_name)
            if not target_bucket:
                logger.warning("GCS bucket unavailable — cannot delete %s", file_path)
                return
            blob = target_bucket.blob(file_path)
            blob.delete()
        except Exception as e:
            raise Exception(f"Failed to delete file from GCS: {str(e)}")

    def file_exists(self, file_path, bucket_name=None):
        """
        Check if a file exists in Google Cloud Storage.

        Args:
            file_path: Path of the file to check.
            bucket_name: Optional bucket override (for per-tenant routing).

        Returns:
            bool: True if file exists, False otherwise.
        """
        try:
            target_bucket = self.get_bucket(bucket_name)
            if not target_bucket:
                return False
            blob = target_bucket.blob(file_path)
            return blob.exists()
        except Exception:
            return False

    def generate_signed_url(
        self,
        file_path,
        expiration_minutes=15,
        for_download=False,
        filename=None,
        bucket_name=None,
    ):
        """
        Generate a signed URL for temporary access to a file.

        Args:
            file_path: Path of the file in GCS.
            expiration_minutes: How long the URL should be valid (default: 15).
            for_download: If True, sets content-disposition to attachment.
                Non-browser-viewable types (e.g. .docx, .xlsx, .pptx) will
                always be served as attachments even when for_download=False.
            filename: Original filename for download (used with for_download).
            bucket_name: Optional bucket override (for per-tenant routing).

        Returns:
            dict: Contains 'url' and 'expires_at' timestamp.
        """
        target_bucket = self.get_bucket(bucket_name)
        target_name = bucket_name or self.bucket_name

        if not target_bucket:
            # Mock URL for development
            from datetime import datetime, timezone

            mock_url = (
                f"https://storage.googleapis.com/{target_name}/{file_path}"
                f"?mock_signed=true"
            )
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=expiration_minutes
            )
            return {
                "url": mock_url,
                "expires_at": expires_at.isoformat(),
            }

        try:
            from datetime import datetime, timezone

            blob = target_bucket.blob(file_path)

            # Determine content type from file extension
            ext = os.path.splitext(file_path)[1].lower()
            content_type = _EXTENSION_CONTENT_TYPE.get(ext)

            # For non-browser-viewable types, always force
            # Content-Disposition: attachment even when for_download=False
            # (i.e. when the caller asks for a "view" URL). Browsers cannot
            # render .docx, .xlsx, .pptx etc. inline and will show "could not
            # load plugin", so we override the caller's preference.
            force_download = (
                content_type is not None and content_type not in _BROWSER_VIEWABLE_TYPES
            )

            # Build response disposition header
            response_disposition = None
            safe_name = (filename or os.path.basename(file_path)).replace('"', '\\"')
            if for_download or force_download:
                response_disposition = f'attachment; filename="{safe_name}"'

            # Generate signed URL
            expiration = timedelta(minutes=expiration_minutes)

            url_kwargs = {
                "version": "v4",
                "expiration": expiration,
                "method": "GET",
            }
            if response_disposition:
                url_kwargs["response_disposition"] = response_disposition
            if content_type:
                url_kwargs["response_type"] = content_type

            url = blob.generate_signed_url(**url_kwargs)

            expires_at = datetime.now(timezone.utc) + expiration

            logger.info(
                f"Generated signed URL for {file_path}, "
                f"expires in {expiration_minutes} minutes"
            )

            return {
                "url": url,
                "expires_at": expires_at.isoformat(),
            }

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {file_path}: {e}")
            raise Exception(f"Failed to generate signed URL: {str(e)}")


# Global service instance
gcs_service = GCSService()
