"""
Django signals for onboarding pipeline integration.

These signals trigger pipeline operations when models are saved or updated.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Company

logger = logging.getLogger(__name__)


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

    # Queue the export task
    # Using apply_async with countdown to debounce rapid updates
    export_company_for_rag.apply_async(
        args=[instance.id],
        countdown=5 if not created else 0,  # 5s delay for updates to debounce
    )
