"""
Django signals for onboarding pipeline integration.

These signals trigger pipeline operations when models are saved or updated.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BrandAsset, Company

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


@receiver(post_save, sender=Company)
def company_saved_handler(sender, instance, created, **kwargs):
    """
    Trigger RAG export when a Company is created or updated.

    This signal handler queues a Celery task to export company data
    to the RAG pipeline for indexing. We use a task to avoid blocking
    the save operation and to ensure retries on failure.

    Args:
        sender: The Company model class.
        instance: The Company instance that was saved.
        created: True if this is a new company, False for update.
        **kwargs: Additional signal arguments.
    """
    # Import here to avoid circular imports and ensure Celery is ready
    from .tasks import export_company_for_rag

    action = "created" if created else "updated"
    logger.info(
        f"Company {action}, queuing RAG export",
        extra={"company_id": instance.id, "is_new": created},
    )

    # Queue the export task with error handling
    # Using apply_async with countdown to debounce rapid updates
    # Wrap in try/except so company save doesn't fail if Celery/Redis is down
    try:
        export_company_for_rag.apply_async(
            args=[instance.id],
            countdown=5 if not created else 0,  # 5s delay for updates to debounce
        )
    except Exception as e:
        # Log the error but don't fail the company save
        logger.warning(
            f"Failed to queue RAG export task for company {instance.id}: {e}. "
            "Company was saved but RAG export was not triggered."
        )


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
