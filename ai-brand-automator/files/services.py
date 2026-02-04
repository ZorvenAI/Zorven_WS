"""
File Storage Services for BrandForge AI
Integration with Google Cloud Storage
"""

import os
import time
import logging
from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class GCSService:
    """
    Service for interacting with Google Cloud Storage
    """

    def __init__(self):
        self.bucket_name = settings.GS_BUCKET_NAME
        self.project_id = settings.GS_PROJECT_ID
        self.credentials_path = settings.GS_CREDENTIALS_PATH

        # Initialize GCS client
        try:
            if self.credentials_path and os.path.exists(self.credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                self.client = storage.Client(
                    credentials=credentials, project=self.project_id
                )
            else:
                # Try to use default credentials (for GCP environments)
                self.client = storage.Client(project=self.project_id)
        except Exception as e:
            # Fallback: create a mock client for development
            print(f"GCS initialization failed: {e}. Using mock service.")
            self.client = None

        if self.client:
            self.bucket = self.client.bucket(self.bucket_name)
        else:
            self.bucket = None

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
            f"Failed to upload file to GCS after {max_retries} attempts: {str(last_error)}"
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


# Global service instance
gcs_service = GCSService()
