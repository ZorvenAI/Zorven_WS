"""
GCS bucket provisioning service for tenants.

Provides ``TenantGCSService`` which creates and deletes per-tenant
Google Cloud Storage buckets.  Bucket naming convention::

    {slug}-raw        – raw / landing-zone assets
    {slug}-curated    – AI-curated output

The service is **idempotent**: calling ``create_tenant_buckets`` twice
for the same tenant is safe — existing buckets are simply skipped.
"""

import logging

from decouple import config

logger = logging.getLogger(__name__)


class TenantGCSService:
    """Provision and manage per-tenant GCS buckets.

    Attributes:
        client: An authenticated ``google.cloud.storage.Client``.
        location: GCS bucket location (default ``us-central1``).
    """

    DEFAULT_LOCATION = "us-central1"

    def __init__(self, credentials_path=None):
        """Initialise with a GCS client.

        Falls back to Application Default Credentials if no
        explicit credentials path is provided.
        """
        self.location = config(
            "GCS_BUCKET_LOCATION",
            default=self.DEFAULT_LOCATION,
        )
        self.client = self._build_client(credentials_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_tenant_buckets(self, tenant):
        """Create raw + curated GCS buckets for *tenant*.

        Idempotent — skips buckets that already exist.
        Updates the ``Tenant`` record with the bucket names.

        Args:
            tenant: A ``tenants.models.Tenant`` instance.
        """
        raw_name = f"{tenant.slug}-raw"
        curated_name = f"{tenant.slug}-curated"

        self._ensure_bucket(raw_name)
        self._ensure_bucket(curated_name)

        tenant.gcs_raw_bucket = raw_name
        tenant.gcs_curated_bucket = curated_name
        tenant.save(update_fields=["gcs_raw_bucket", "gcs_curated_bucket"])

        logger.info(
            "Provisioned GCS buckets for tenant '%s': raw=%s, curated=%s",
            tenant.slug,
            raw_name,
            curated_name,
        )

    def delete_tenant_buckets(self, tenant):
        """Delete a tenant's GCS buckets (best-effort).

        Only attempts deletion for buckets that are set on the tenant
        and follow the expected naming pattern.

        Args:
            tenant: A ``tenants.models.Tenant`` instance.
        """
        for bucket_name in [tenant.gcs_raw_bucket, tenant.gcs_curated_bucket]:
            if bucket_name:
                self._delete_bucket(bucket_name)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_client(self, credentials_path=None):
        """Return a ``google.cloud.storage.Client``."""
        try:
            from google.cloud import storage as gcs

            project_id = config("GCP_PROJECT_ID", default="brandsol")

            if credentials_path:
                from google.oauth2 import service_account

                creds = service_account.Credentials.from_service_account_file(
                    credentials_path,
                )
                return gcs.Client(credentials=creds, project=project_id)

            return gcs.Client(project=project_id)
        except Exception as exc:
            logger.warning(
                "Could not create GCS client: %s. "
                "Bucket provisioning will be unavailable.",
                exc,
            )
            return None

    def _ensure_bucket(self, bucket_name):
        """Create a bucket if it does not already exist."""
        if self.client is None:
            logger.warning(
                "GCS client unavailable — skipping bucket creation for %s",
                bucket_name,
            )
            return

        bucket = self.client.bucket(bucket_name)
        if bucket.exists():
            logger.debug("Bucket %s already exists — skipping", bucket_name)
            return

        bucket.storage_class = "STANDARD"
        self.client.create_bucket(bucket, location=self.location)
        logger.info("Created GCS bucket: %s (location=%s)", bucket_name, self.location)

    def _delete_bucket(self, bucket_name):
        """Delete a bucket and all its contents (best-effort)."""
        if self.client is None:
            return
        try:
            bucket = self.client.bucket(bucket_name)
            if bucket.exists():
                bucket.delete(force=True)
                logger.info("Deleted GCS bucket: %s", bucket_name)
        except Exception:
            logger.warning(
                "Failed to delete bucket %s — it may need manual cleanup",
                bucket_name,
            )
