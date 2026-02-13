"""
Signals for the Tenants app.

Handles automatic GCS bucket provisioning when a new tenant is created.
Controlled by the ``GCS_AUTO_PROVISION`` environment variable (default: off).
"""

import logging

from decouple import config as decouple_config
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Tenant

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Tenant)
def provision_tenant_buckets(sender, instance, created, **kwargs):
    """Auto-provision GCS buckets when a new tenant is created.

    Skips when:
    - The save is an update (not a create).
    - The tenant is the public tenant.
    - The tenant already has both buckets set.
    - ``GCS_AUTO_PROVISION`` is not enabled.
    """
    if not created:
        return

    if instance.schema_name == "public":
        return

    if instance.gcs_raw_bucket and instance.gcs_curated_bucket:
        return  # Already provisioned

    if not decouple_config("GCS_AUTO_PROVISION", default=False, cast=bool):
        logger.debug(
            "GCS_AUTO_PROVISION is disabled — skipping bucket "
            "creation for tenant '%s'",
            instance.slug,
        )
        return

    try:
        from .services import TenantGCSService

        service = TenantGCSService()
        service.create_tenant_buckets(instance)
    except Exception:
        logger.warning(
            "Failed to auto-provision GCS buckets for tenant '%s'. "
            "Run scripts/provision_tenant_buckets.py to retry.",
            instance.slug,
            exc_info=True,
        )
