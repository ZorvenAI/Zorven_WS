"""
Celery tasks for DB-to-RAG synchronization.

Provides event-driven (signal-triggered) and periodic sync of Django
model data to per-tenant Vertex AI RAG stores.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, Reject

from rag_index.domain.exceptions import (
    RateLimitExceededError,
    SyncError,
    SyncValidationError,
)

logger = logging.getLogger(__name__)

# Redis key pattern for periodic sync checkpoints
_CHECKPOINT_KEY = "rag:db-sync:checkpoint:{tenant_id}:{model_name}"


@shared_task(
    bind=True,
    name="rag_index.tasks.sync_model_to_rag",
    max_retries=3,
    autoretry_for=(SyncError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    acks_late=True,
)
def sync_model_to_rag(
    self,
    model_name: str,
    pk: int,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Sync a single model instance to Vertex AI RAG store.

    Args:
        model_name: Short model name (e.g., "Company", "AnalysisJob")
        pk: Primary key of the model instance
        tenant_id: Tenant ID for per-tenant data store resolution

    Returns:
        Dict with sync result
    """
    from rag_index.services.db_sync_service import DbSyncService
    from rag_index.domain.models import SyncAction, SyncEvent
    from rag_index.tasks.sync_tasks import get_orchestrator, run_async

    logger.info(
        "Syncing %s pk=%s to RAG (tenant=%s)",
        model_name,
        pk,
        tenant_id,
    )

    # 1. Load model instance
    db_sync = DbSyncService()
    try:
        model_class = db_sync.get_model_class(model_name)
    except ValueError as e:
        raise Reject(reason=str(e), requeue=False)

    try:
        if model_name == "ChatMessage":
            instance = model_class.objects.select_related("session").get(pk=pk)
        elif model_name == "Company":
            instance = model_class.objects.select_related("tenant").get(pk=pk)
        else:
            instance = model_class.objects.get(pk=pk)
    except model_class.DoesNotExist:
        logger.warning("%s pk=%s not found, skipping RAG sync", model_name, pk)
        return {"status": "skipped", "reason": "not_found"}

    # 2. Check if eligible for sync
    if not db_sync.should_sync(model_name, instance):
        logger.debug("%s pk=%s not eligible for sync", model_name, pk)
        return {"status": "skipped", "reason": "not_eligible"}

    # 3. Build document
    document = db_sync.build_document(model_name, instance)
    if document is None:
        return {"status": "skipped", "reason": "no_document"}

    # 4. Resolve tenant if not provided
    if not tenant_id:
        tenant_id = db_sync.get_tenant_id(instance)
    if not tenant_id:
        logger.warning(
            "%s pk=%s has no tenant, using default data store",
            model_name,
            pk,
        )
        tenant_id = "public"

    # 5. Create SyncEvent and dispatch
    document_id = db_sync.get_document_id(model_name, instance)
    event = SyncEvent(
        event_id=uuid4(),
        trace_id=f"db-sync-{uuid4().hex[:16]}",
        tenant_id=tenant_id,
        file_id=document_id,
        action=SyncAction.UPSERT,
        metadata={
            "source": "db_sync",
            "model_name": model_name,
            "pk": pk,
        },
    )

    try:
        orchestrator = get_orchestrator()
        result = run_async(orchestrator.process_inline_document(event, document))

        logger.info(
            "DB sync completed: %s pk=%s → %s",
            model_name,
            pk,
            result.status,
        )
        return result.to_dict()

    except RateLimitExceededError as e:
        logger.warning(
            "Rate limit hit during DB sync for %s pk=%s",
            model_name,
            pk,
        )
        try:
            raise self.retry(
                exc=e,
                countdown=max(e.retry_after_seconds, 30),
                max_retries=10,
            )
        except MaxRetriesExceededError:
            raise Reject(reason="Rate limit retries exhausted", requeue=False)

    except SyncValidationError as e:
        raise Reject(reason=str(e), requeue=False)

    except SyncError:
        raise  # auto-retried via autoretry_for


@shared_task(
    bind=True,
    name="rag_index.tasks.periodic_db_rag_sync",
    max_retries=1,
    acks_late=True,
)
def periodic_db_rag_sync(
    self,
    tenant_id: int | None = None,
) -> dict[str, Any]:
    """Periodic sync — finds records updated since last checkpoint.

    For each syncable model, queries records where updated_at > checkpoint
    and dispatches individual sync_model_to_rag tasks.

    Args:
        tenant_id: Optional tenant PK to sync. If None, syncs all tenants.

    Returns:
        Dict with sync stats.
    """
    from django.conf import settings
    from rag_index.services.db_sync_service import DbSyncService

    enabled_models = getattr(
        settings,
        "RAG_DB_SYNC_MODELS",
        "Company,AnalysisJob,ChatMessage,AIGeneration,ContentCalendar",
    )
    if isinstance(enabled_models, str):
        enabled_models = [m.strip() for m in enabled_models.split(",") if m.strip()]

    tenants = _get_tenants(tenant_id)
    db_sync = DbSyncService()

    stats = {"tenants": len(tenants), "dispatched": 0, "models": {}}

    for t_id in tenants:
        for model_name in enabled_models:
            dispatched = _sync_model_since_checkpoint(db_sync, model_name, str(t_id))
            stats["dispatched"] += dispatched
            stats["models"][model_name] = (
                stats["models"].get(model_name, 0) + dispatched
            )

    logger.info("Periodic DB-RAG sync complete: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="rag_index.tasks.full_db_rag_resync",
    max_retries=0,
    acks_late=True,
)
def full_db_rag_resync(
    self,
    tenant_id: int | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Manual full re-sync — resets checkpoint and syncs all records.

    Args:
        tenant_id: Optional tenant PK. If None, re-syncs all.
        model_name: Optional model name. If None, re-syncs all models.

    Returns:
        Dict with resync stats.
    """
    from rag_index.services.db_sync_service import DbSyncService, SYNCABLE_MODELS

    enabled_models = [model_name] if model_name else list(SYNCABLE_MODELS.keys())
    tenants = _get_tenants(tenant_id)
    db_sync = DbSyncService()

    stats = {"tenants": len(tenants), "dispatched": 0, "models": {}}

    for t_id in tenants:
        t_str = str(t_id)
        for mname in enabled_models:
            # Reset checkpoint
            _set_checkpoint(t_str, mname, None)
            dispatched = _sync_model_since_checkpoint(db_sync, mname, t_str)
            stats["dispatched"] += dispatched
            stats["models"][mname] = stats["models"].get(mname, 0) + dispatched

    logger.info("Full DB-RAG resync complete: %s", stats)
    return stats


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _get_tenants(tenant_id: int | None) -> list[int]:
    """Get list of tenant PKs to process."""
    if tenant_id is not None:
        return [tenant_id]
    try:
        from tenants.models import Tenant

        return list(
            Tenant.objects.exclude(schema_name="public").values_list("id", flat=True)
        )
    except Exception:
        logger.warning("Could not query tenants, using empty list")
        return []


def _sync_model_since_checkpoint(
    db_sync,
    model_name: str,
    tenant_id: str,
) -> int:
    """Query records updated since checkpoint and dispatch sync tasks."""
    try:
        model_class = db_sync.get_model_class(model_name)
    except ValueError:
        return 0

    checkpoint = _get_checkpoint(tenant_id, model_name)

    # Build queryset with tenant filter
    qs = model_class.objects.all()
    try:
        tenant_pk = int(tenant_id)
    except (ValueError, TypeError):
        tenant_pk = None

    if tenant_pk is not None:
        if hasattr(model_class, "tenant"):
            qs = qs.filter(tenant_id=tenant_pk)
        elif hasattr(model_class, "session"):
            # ChatMessage: filter via session__tenant
            qs = qs.filter(session__tenant_id=tenant_pk)

    if checkpoint:
        qs = qs.filter(updated_at__gt=checkpoint)

    # Apply model-specific filters
    if model_name == "AnalysisJob":
        qs = qs.filter(status="completed")
    elif model_name == "ChatMessage":
        qs = qs.filter(role="assistant")
    elif model_name == "ContentCalendar":
        qs = qs.filter(status="published")

    dispatched = 0
    latest_updated = checkpoint

    for i, record in enumerate(qs.order_by("updated_at").iterator(chunk_size=200)):
        sync_model_to_rag.apply_async(
            args=[model_name, record.pk, tenant_id],
            countdown=i * 0.1,  # 100ms stagger
        )
        dispatched += 1
        record_updated = getattr(record, "updated_at", None)
        if record_updated and (
            latest_updated is None or record_updated > latest_updated
        ):
            latest_updated = record_updated

    # Update checkpoint
    if latest_updated and latest_updated != checkpoint:
        _set_checkpoint(tenant_id, model_name, latest_updated)

    return dispatched


def _get_checkpoint(tenant_id: str, model_name: str) -> datetime | None:
    """Read last sync checkpoint from Django cache."""
    from django.core.cache import cache

    key = _CHECKPOINT_KEY.format(tenant_id=tenant_id, model_name=model_name)
    val = cache.get(key)
    if val and isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
    return val


def _set_checkpoint(
    tenant_id: str,
    model_name: str,
    timestamp: datetime | None,
) -> None:
    """Write sync checkpoint to Django cache."""
    from django.core.cache import cache

    key = _CHECKPOINT_KEY.format(tenant_id=tenant_id, model_name=model_name)
    if timestamp is None:
        cache.delete(key)
    else:
        cache.set(key, timestamp.isoformat(), timeout=None)
