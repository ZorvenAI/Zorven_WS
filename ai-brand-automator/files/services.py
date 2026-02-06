"""
File Storage Services for BrandForge AI
Integration with Google Cloud Storage
"""

import json
import os
import time
import logging
from datetime import timedelta
from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.full_control"]


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
        try:
            credentials = self._resolve_credentials()
            if credentials:
                self.client = storage.Client(
                    credentials=credentials, project=self.project_id
                )
            else:
                # Application Default Credentials (GCP environments)
                self.client = storage.Client(project=self.project_id)
        except Exception as e:
            # Fallback: create a mock client for development
            logger.warning("GCS initialization failed: %s. Using mock service.", e)
            self.client = None

        if self.client:
            self.bucket = self.client.bucket(self.bucket_name)
        else:
            self.bucket = None

    def _resolve_credentials(self):
        """Resolve GCS credentials from env var, file, or return None for ADC."""
        # 1. Inline JSON from environment variable (Railway / Heroku / CI)
        creds_json = os.environ.get("GCS_CREDENTIALS_JSON", "").strip()
        if creds_json:
            logger.info("Loading GCS credentials from GCS_CREDENTIALS_JSON env var")
            info = json.loads(creds_json)
            return service_account.Credentials.from_service_account_info(
                info, scopes=GCS_SCOPES
            )

        # 2. Service account key file on disk (local development)
        if self.credentials_path and os.path.exists(self.credentials_path):
            logger.info("Loading GCS credentials from file: %s", self.credentials_path)
            return service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=GCS_SCOPES
            )

        # 3. Fall back to Application Default Credentials
        logger.info("No explicit GCS credentials found, using ADC")
        return None

    def upload_file(self, file_obj, file_path, content_type=None, max_retries=3):
        """
        Upload a file to Google Cloud Storage with retry logic

        Args:
            file_obj: File object to upload
            file_path: Path in GCS where to store the file
            content_type: MIME type of the file
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            str: Public URL of the uploaded file
        """
        if not self.bucket:
            # Mock upload for development
            return f"https://storage.googleapis.com/{self.bucket_name}/{file_path}"

        last_error = None
        for attempt in range(max_retries):
            try:
                blob = self.bucket.blob(file_path)

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

    def delete_file(self, file_path):
        """
        Delete a file from Google Cloud Storage

        Args:
            file_path: Path of the file to delete
        """
        try:
            blob = self.bucket.blob(file_path)
            blob.delete()
        except Exception as e:
            raise Exception(f"Failed to delete file from GCS: {str(e)}")

    def file_exists(self, file_path):
        """
        Check if a file exists in Google Cloud Storage

        Args:
            file_path: Path of the file to check

        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            blob = self.bucket.blob(file_path)
            return blob.exists()
        except Exception:
            return False

    def generate_signed_url(
        self,
        file_path,
        expiration_minutes=15,
        for_download=False,
        filename=None,
    ):
        """
        Generate a signed URL for temporary access to a file.

        Args:
            file_path: Path of the file in GCS
            expiration_minutes: How long the URL should be valid (default: 15)
            for_download: If True, sets content-disposition to attachment
            filename: Original filename for download (used with for_download)

        Returns:
            dict: Contains 'url' and 'expires_at' timestamp
        """
        if not self.bucket:
            # Mock URL for development
            from datetime import datetime, timezone

            mock_url = (
                f"https://storage.googleapis.com/{self.bucket_name}/{file_path}"
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

            blob = self.bucket.blob(file_path)

            # Note: We don't check if file exists - signed URL generation works
            # even for non-existent files. GCS returns 404 when accessed.
            # This allows viewing files in different paths or being processed.

            # Build response disposition header if downloading
            response_disposition = None
            if for_download and filename:
                # Sanitize filename for header
                safe_filename = filename.replace('"', '\\"')
                response_disposition = f'attachment; filename="{safe_filename}"'

            # Generate signed URL
            expiration = timedelta(minutes=expiration_minutes)
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET",
                response_disposition=response_disposition,
            )

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
