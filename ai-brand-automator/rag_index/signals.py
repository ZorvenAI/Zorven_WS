"""
Signal handlers for DB-to-RAG synchronization.

Listens to post_save signals on RAG-valuable models and dispatches
Celery tasks to sync them to per-tenant Vertex AI data stores.

All handlers:
- Import tasks inside the handler (avoid circular imports)
- Use apply_async with countdown for debouncing
- Wrap in try/except so model saves never fail if Celery is down
- Are controlled by the RAG_DB_SYNC_ENABLED setting
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_tenant_id(instance) -> str | None:
    """Extract tenant ID from a model instance."""
    tenant = getattr(instance, "tenant", None)
    if tenant:
        return str(tenant.id)
    session = getattr(instance, "session", None)
    if session:
        tenant = getattr(session, "tenant", None)
        if tenant:
            return str(tenant.id)
    return None


@receiver(post_save, sender="onboarding.Company")
def sync_company_to_rag(sender, instance, created, **kwargs):
    """Sync Company to RAG on create/update."""
    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    tenant_id = _get_tenant_id(instance)
    try:
        sync_model_to_rag.apply_async(
            args=["Company", instance.pk, tenant_id],
            countdown=0 if created else 5,
        )
    except Exception as e:
        logger.warning(
            "Failed to queue Company RAG sync for pk=%s: %s",
            instance.pk,
            e,
        )


@receiver(post_save, sender="orchestration.AnalysisJob")
def sync_analysis_job_to_rag(sender, instance, **kwargs):
    """Sync completed AnalysisJob results to RAG."""
    if instance.status != "completed":
        return

    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    tenant_id = _get_tenant_id(instance)
    try:
        sync_model_to_rag.apply_async(
            args=["AnalysisJob", instance.pk, tenant_id],
            countdown=2,
        )
    except Exception as e:
        logger.warning(
            "Failed to queue AnalysisJob RAG sync for pk=%s: %s",
            instance.pk,
            e,
        )


@receiver(post_save, sender="ai_services.ChatMessage")
def sync_chat_message_to_rag(sender, instance, **kwargs):
    """Sync assistant ChatMessages to RAG."""
    if instance.role != "assistant":
        return

    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    tenant_id = _get_tenant_id(instance)
    try:
        sync_model_to_rag.apply_async(
            args=["ChatMessage", instance.pk, tenant_id],
            countdown=10,  # longer debounce for streaming messages
        )
    except Exception as e:
        logger.warning(
            "Failed to queue ChatMessage RAG sync for pk=%s: %s",
            instance.pk,
            e,
        )


@receiver(post_save, sender="ai_services.AIGeneration")
def sync_ai_generation_to_rag(sender, instance, **kwargs):
    """Sync AIGeneration to RAG."""
    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    tenant_id = _get_tenant_id(instance)
    try:
        sync_model_to_rag.apply_async(
            args=["AIGeneration", instance.pk, tenant_id],
            countdown=5,
        )
    except Exception as e:
        logger.warning(
            "Failed to queue AIGeneration RAG sync for pk=%s: %s",
            instance.pk,
            e,
        )


@receiver(post_save, sender="automation.ContentCalendar")
def sync_content_calendar_to_rag(sender, instance, **kwargs):
    """Sync published ContentCalendar entries to RAG."""
    if instance.status != "published":
        return

    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    tenant_id = _get_tenant_id(instance)
    try:
        sync_model_to_rag.apply_async(
            args=["ContentCalendar", instance.pk, tenant_id],
            countdown=2,
        )
    except Exception as e:
        logger.warning(
            "Failed to queue ContentCalendar RAG sync for pk=%s: %s",
            instance.pk,
            e,
        )
