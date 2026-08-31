"""
Signals for the Tenants app.

Handles automatic provisioning when a new tenant is created:
- GCS buckets (controlled by ``GCS_AUTO_PROVISION``)
- Vertex AI data stores (controlled by ``VERTEX_AI_AUTO_PROVISION``)
- Prompt optimization scaffolding (controlled by ``POI_AUTO_SCAFFOLD``)
"""

import logging

import requests
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


@receiver(post_save, sender=Tenant)
def provision_tenant_data_store(sender, instance, created, **kwargs):
    """Auto-provision a Vertex AI data store when a new tenant is created.

    Skips when:
    - The save is an update (not a create).
    - The tenant is the public tenant.
    - The tenant already has a data store set.
    - ``VERTEX_AI_AUTO_PROVISION`` is not enabled.
    """
    if not created:
        return

    if instance.schema_name == "public":
        return

    if instance.vertex_ai_data_store_id:
        return  # Already provisioned

    if not decouple_config("VERTEX_AI_AUTO_PROVISION", default=False, cast=bool):
        logger.debug(
            "VERTEX_AI_AUTO_PROVISION is disabled — skipping data store "
            "creation for tenant '%s'",
            instance.slug,
        )
        return

    try:
        from .services import TenantVertexAIService

        service = TenantVertexAIService()
        service.create_tenant_data_store(instance)
    except Exception:
        logger.warning(
            "Failed to auto-provision Vertex AI data store for tenant '%s'. "
            "Run scripts/provision_tenant_data_stores.py to retry.",
            instance.slug,
            exc_info=True,
        )


@receiver(post_save, sender=Tenant)
def scaffold_tenant_prompts(sender, instance, created, **kwargs):
    """Scaffold OIA prompt overrides when a new tenant is created (L-04).

    Fire-and-forget — a failed scaffold is retried manually via
    ``POST /v1/prompts/scaffold-tenant`` on the POI service.
    """
    if not created:
        return

    if instance.schema_name == "public":
        return

    if not decouple_config("POI_AUTO_SCAFFOLD", default=False, cast=bool):
        return

    poi_url = decouple_config("POI_SERVICE_URL", default="")
    if not poi_url:
        logger.debug(
            "POI_SERVICE_URL not configured — skipping prompt scaffold "
            "for tenant '%s'",
            instance.slug,
        )
        return

    try:
        resp = requests.post(
            f"{poi_url.rstrip('/')}/v1/prompts/scaffold-tenant",
            json={"tenant_id": str(instance.pk)},
            headers={"X-User-Role": "ADMIN"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "Prompt scaffold for tenant '%s': scaffolded=%d, skipped=%d",
            instance.slug,
            data.get("scaffolded", 0),
            data.get("skipped", 0),
        )
    except Exception:
        logger.warning(
            "Failed to scaffold prompts for tenant '%s'. "
            "Call POST /v1/prompts/scaffold-tenant manually to retry.",
            instance.slug,
            exc_info=True,
        )
