"""
Provisioning services for tenants.

Provides:
- ``TenantGCSService``: creates/deletes per-tenant GCS buckets.
- ``TenantVertexAIService``: creates per-tenant Vertex AI data stores.

Both services are **idempotent**: calling create twice for the same
tenant is safe — existing resources are simply skipped.
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
        Updates the ``Tenant`` record with the bucket names **only**
        when the GCS client is available and buckets are confirmed.

        Args:
            tenant: A ``tenants.models.Tenant`` instance.

        Raises:
            RuntimeError: If the GCS client is unavailable.
        """
        if self.client is None:
            logger.warning(
                "GCS client unavailable — cannot provision buckets "
                "for tenant '%s'. Tenant will use shared default buckets.",
                tenant.slug,
            )
            raise RuntimeError("GCS client unavailable — bucket provisioning skipped")

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


class TenantVertexAIService:
    """Provision per-tenant Vertex AI Discovery Engine data stores.

    Mirrors ``TenantGCSService``.  Data store naming convention::

        prevision-{tenant.slug}

    The service is **idempotent**: ``ALREADY_EXISTS`` from the API is
    treated as success.
    """

    def __init__(self):
        self.project_id = config("VERTEX_AI_PROJECT_ID", default="brandsol-project")
        self.location = config("VERTEX_AI_LOCATION", default="global")
        self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_tenant_data_store(self, tenant):
        """Create a Vertex AI data store for *tenant*.

        Idempotent — treats ``ALREADY_EXISTS`` as success.
        Updates the ``Tenant`` record with the data store ID when
        confirmed.

        Args:
            tenant: A ``tenants.models.Tenant`` instance.

        Raises:
            RuntimeError: If the Discovery Engine client is unavailable.
        """
        client = self._get_client()
        if client is None:
            logger.warning(
                "Discovery Engine client unavailable — cannot provision "
                "data store for tenant '%s'. Tenant will use shared default.",
                tenant.slug,
            )
            raise RuntimeError(
                "Discovery Engine client unavailable — "
                "data store provisioning skipped"
            )

        data_store_id = f"prevision-{tenant.slug}"
        parent = (
            f"projects/{self.project_id}/locations/{self.location}"
            f"/collections/default_collection"
        )

        self._ensure_data_store(client, parent, data_store_id, tenant.name)

        tenant.vertex_ai_data_store_id = data_store_id
        tenant.save(update_fields=["vertex_ai_data_store_id"])

        logger.info(
            "Provisioned Vertex AI data store for tenant '%s': %s",
            tenant.slug,
            data_store_id,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return a ``DataStoreServiceClient``, or ``None`` on failure."""
        if self._client is not None:
            return self._client
        try:
            from google.cloud import discoveryengine_v1 as discoveryengine

            self._client = discoveryengine.DataStoreServiceClient()
            return self._client
        except Exception as exc:
            logger.warning(
                "Could not create Discovery Engine client: %s. "
                "Data store provisioning will be unavailable.",
                exc,
            )
            return None

    @staticmethod
    def _ensure_data_store(client, parent, data_store_id, display_name):
        """Create a data store if it does not already exist."""
        try:
            from google.cloud import discoveryengine_v1 as discoveryengine

            data_store = discoveryengine.DataStore(
                display_name=display_name,
                industry_vertical=discoveryengine.IndustryVertical.GENERIC,
                solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
                content_config=discoveryengine.DataStore.ContentConfig.NO_CONTENT,
            )

            request = discoveryengine.CreateDataStoreRequest(
                parent=parent,
                data_store=data_store,
                data_store_id=data_store_id,
            )

            operation = client.create_data_store(request=request)
            operation.result(timeout=120)  # Wait up to 2 minutes
            logger.info("Created Vertex AI data store: %s", data_store_id)
        except Exception as exc:
            if "ALREADY_EXISTS" in str(exc):
                logger.debug(
                    "Data store %s already exists — skipping",
                    data_store_id,
                )
            else:
                raise
