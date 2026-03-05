"""
Django signals for onboarding pipeline integration.

These signals trigger pipeline operations when models are saved or updated.

NOTE: The Company post_save RAG sync handler has been moved to
``rag_index/signals.py`` as part of the unified DB-to-RAG sync system.
It is registered when ``RAG_DB_SYNC_ENABLED=True``. When that flag is
off, ``export_company_for_rag`` can still be called manually.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BrandAsset

logger = logging.getLogger(__name__)

# Map BrandAsset pipeline statuses to SessionAttachment statuses.
# BrandAsset: pending | ingested | curated | indexed | failed
# SessionAttachment: pending | processing | indexed | failed
_ATTACHMENT_STATUS_MAP = {
    "pending": "pending",
    "ingested": "processing",
    "curated": "processing",
    "indexed": "indexed",
    "failed": "failed",
}


@receiver(post_save, sender=BrandAsset)
def sync_session_attachment_status(sender, instance, **kwargs):
    """Cascade BrandAsset.pipeline_status changes to linked SessionAttachments.

    When a BrandAsset is processed through the data pipeline (ingestion →
    curation → indexing), the status updates only touch the BrandAsset model.
    Any SessionAttachment records linked via FK need their own pipeline_status
    updated so the chat UI reflects the real state.
    """
    update_fields = kwargs.get("update_fields")
    if update_fields and "pipeline_status" not in update_fields:
        return

    attachment_status = _ATTACHMENT_STATUS_MAP.get(instance.pipeline_status)
    if not attachment_status:
        return

    # Import here to avoid circular imports between apps
    from ai_services.models import SessionAttachment

    updated = (
        SessionAttachment.objects.filter(asset=instance)
        .exclude(
            pipeline_status=attachment_status,
        )
        .update(pipeline_status=attachment_status)
    )

    if updated:
        logger.info(
            "Synced %d SessionAttachment(s) for BrandAsset %s → %s",
            updated,
            instance.id,
            attachment_status,
        )
