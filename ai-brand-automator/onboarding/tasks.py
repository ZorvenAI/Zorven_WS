"""
Celery tasks for onboarding pipeline integration.

These tasks handle asynchronous operations for the data pipeline,
including exporting company data for RAG indexing and running the
full asset processing pipeline when Kafka is disabled.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from celery import shared_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sync Pipeline Task — runs ingestion → curation via Celery (no Kafka)
# ---------------------------------------------------------------------------


def _update_asset_status(
    asset_id: int,
    status: str,
    error_msg: str = "",
    new_gcs_path: str = "",
    tenant_id: str = "",
) -> bool:
    """Update BrandAsset pipeline status.

    Args:
        asset_id: BrandAsset primary key.
        status: New ``pipeline_status`` value.
        error_msg: Error message (for ``failed`` status).
        new_gcs_path: Updated ``gcs_path`` after ingestion move.
        tenant_id: Tenant pk — used for FK-based tenant filtering.

    Returns:
        ``True`` if update succeeded, ``False`` otherwise.
    """
    from onboarding.models import BrandAsset
    from brand_automator.tenant_utils import (
        parse_tenant_pk,
        ensure_public_db_connection,
    )

    tenant_pk = parse_tenant_pk(tenant_id)

    for attempt in range(2):
        try:
            # Pin DB connection to public schema. On retry, also
            # force-close the stale connection that Neon may have dropped.
            ensure_public_db_connection(close_existing=(attempt > 0))

            def _do_update():
                # Build base filter with optional tenant FK isolation
                filters = {"id": asset_id}
                if tenant_pk is not None:
                    filters["tenant_id"] = tenant_pk

                asset = BrandAsset.objects.filter(**filters).first()
                if not asset:
                    logger.warning(
                        "BrandAsset %s not found for status update", asset_id
                    )
                    return False

                asset.pipeline_status = status
                update_fields = ["pipeline_status"]

                if new_gcs_path:
                    from data_ingestion.domain.path_generator import (
                        extract_object_path as _extract,
                    )

                    asset.gcs_path = _extract(new_gcs_path)
                    update_fields.append("gcs_path")

                if status == "failed" and error_msg:
                    asset.pipeline_error = error_msg
                    update_fields.append("pipeline_error")
                elif status in ("ingested", "curated", "indexed"):
                    asset.pipeline_error = ""
                    update_fields.append("pipeline_error")

                # Mark asset as processed once curation or indexing succeeds
                if status in ("curated", "indexed"):
                    asset.processed = True
                    update_fields.append("processed")

                asset.save(update_fields=update_fields)
                logger.info("Updated BrandAsset %s → status=%s", asset.id, status)
                return True

            result = _do_update()
            return result

        except Exception:
            if attempt == 0:
                logger.warning(
                    "DB error updating BrandAsset %s (will retry)",
                    asset_id,
                    exc_info=True,
                )
                continue
            logger.exception("Failed to update BrandAsset %s after retry", asset_id)
            return False

    return False


@shared_task(
    bind=True,
    name="onboarding.process_asset_pipeline_sync",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    acks_late=True,
)
def process_asset_pipeline_sync(
    self,
    asset_id: int,
    tenant_id: str,
    event_data: dict,
) -> dict:
    """
    Run the full asset pipeline synchronously via Celery.

    This task replaces the Kafka-based pipeline when
    ``ONBOARDING_KAFKA_ENABLED=false``.  It chains:

    1. **Ingestion** — validate & move file from ``_landing/`` → ``raw/``
    2. **Curation** — extract text, redact PII, save curated JSON
    3. **Indexing** — sync curated document to Vertex AI (RAG)

    Both ingestion and curation stages use NoOp Kafka producers so the
    domain services complete without attempting real Kafka publishes.
    The indexing stage reuses the ``SyncOrchestrator`` from ``rag_index``.

    Args:
        asset_id: ``BrandAsset.id``
        tenant_id: Tenant pk (as string).
        event_data: Dict built by
            ``OnboardingPipelineService._build_ingestion_event()``.

    Returns:
        Dict summarising the pipeline result.
    """
    logger.info(
        "Starting sync pipeline for asset %s (tenant %s)",
        asset_id,
        tenant_id,
    )

    # ---- resolve tenant (required for per-tenant bucket resolution) ----
    from brand_automator.tenant_utils import (
        parse_tenant_pk,
        ensure_public_db_connection,
    )

    tenant = None
    tenant_pk = parse_tenant_pk(tenant_id)
    if tenant_pk is not None:
        for attempt in range(2):
            try:
                ensure_public_db_connection(close_existing=(attempt > 0))
                from tenants.models import Tenant

                tenant = Tenant.objects.filter(pk=tenant_pk).first()
                break
            except Exception:
                if attempt == 0:
                    logger.warning(
                        "DB error resolving tenant %s (will retry)",
                        tenant_id,
                        exc_info=True,
                    )
                    continue
                logger.error(
                    "Failed to resolve tenant %s after retry", tenant_id, exc_info=True
                )

    if tenant is None and tenant_pk is not None:
        logger.error(
            "Tenant %s not found — pipeline will use default buckets, "
            "which may cause file-not-found errors for tenant-specific uploads",
            tenant_id,
        )

    # ======================================================================
    # Stage 1 — Ingestion
    # ======================================================================
    ingestion_result = _run_ingestion(self, asset_id, tenant, event_data)
    if ingestion_result.get("status") == "failed":
        return ingestion_result

    # ======================================================================
    # Stage 2 — Curation
    # ======================================================================
    curation_result = _run_curation(
        self, asset_id, tenant, event_data, ingestion_result
    )
    if curation_result.get("status") == "failed":
        return {
            "status": "failed",
            "asset_id": asset_id,
            "ingestion": ingestion_result,
            "curation": curation_result,
        }

    # ======================================================================
    # Stage 3 — RAG Indexing (non-fatal: curation already succeeded)
    # ======================================================================
    indexing_result = _run_indexing(
        self, asset_id, tenant_id, event_data, curation_result
    )

    indexing_status = indexing_result.get("status", "completed")
    if indexing_status in ("success", "skipped"):
        final_status = "indexed" if indexing_status == "success" else "curated"
    else:
        # Indexing failed but curation succeeded — mark as curated,
        # not failed.  The file is processed and usable; RAG indexing
        # can be retried via retry_asset_pipeline().
        logger.warning(
            "Indexing failed for asset %s but curation succeeded — "
            "marking as curated.  Error: %s",
            asset_id,
            indexing_result.get("error", "unknown"),
        )
        _update_asset_status(
            asset_id,
            "curated",
            tenant_id=tenant_id,
        )
        final_status = "curated"

    return {
        "status": final_status,
        "asset_id": asset_id,
        "ingestion": ingestion_result,
        "curation": curation_result,
        "indexing": indexing_result,
    }


def _run_ingestion(self, asset_id: int, tenant, event_data: dict) -> dict:
    """Execute the ingestion stage with a NoOp Kafka producer."""
    from data_ingestion.domain.models import IngestionEvent, EventSource
    from data_ingestion.domain.services import IngestionService
    from data_ingestion.factory import create_gcs_adapter, create_redis_adapter
    from data_ingestion.adapters.noop_adapter import NoOpProducerAdapter

    try:
        # Build IngestionEvent from the event_data dict
        event = IngestionEvent(
            event_id=UUID(event_data["event_id"]),
            tenant_id=event_data.get("tenant_id", "public"),
            file_path=event_data["file_path"],
            file_type=event_data.get("file_type", "application/octet-stream"),
            timestamp=(
                datetime.fromisoformat(event_data["timestamp"])
                if event_data.get("timestamp")
                else datetime.now(timezone.utc)
            ),
            source=EventSource.FRONTEND_UPLOAD,
            trace_id=(
                UUID(event_data["trace_id"]) if event_data.get("trace_id") else uuid4()
            ),
            metadata=event_data.get("metadata"),
            raw_bucket=event_data.get("raw_bucket"),
            curated_bucket=event_data.get("curated_bucket"),
        )

        # Create service with NoOp producer (skip Kafka at step 8)
        service = IngestionService(
            storage=create_gcs_adapter(tenant=tenant),
            cache=create_redis_adapter(),
            producer=NoOpProducerAdapter(),
            output_topic="curation-needed-topic",
            dlq_topic="ingestion-dlq",
        )

        result = service.process_event(event)

        # Update BrandAsset → ingested
        _update_asset_status(
            asset_id,
            "ingested",
            new_gcs_path=result.destination_path,
            tenant_id=event_data.get("tenant_id", ""),
        )

        logger.info(
            "Ingestion succeeded for asset %s → %s",
            asset_id,
            result.destination_path,
        )
        return {
            "status": "success",
            "destination_path": result.destination_path,
            "duration_ms": result.processing_duration_ms,
            "event_id": str(result.event_id),
            "trace_id": str(result.trace_id),
        }

    except Exception as e:
        error_msg = f"Ingestion failed: {e}"
        logger.error(error_msg, extra={"asset_id": asset_id}, exc_info=True)
        _update_asset_status(
            asset_id,
            "failed",
            error_msg=str(e),
            tenant_id=event_data.get("tenant_id", ""),
        )
        return {"status": "failed", "error": str(e)}


def _run_curation(
    self,
    asset_id: int,
    tenant,
    event_data: dict,
    ingestion_result: dict,
) -> dict:
    """Execute the curation stage with a NoOp Kafka producer."""
    from media_curation.domain.models import CurationEvent, ContentType
    from media_curation.factory import (
        create_processor_factory,
        create_cache_adapter,
        create_storage_adapter,
        create_dlp_adapter,
        get_media_curation_config,
    )
    from media_curation.domain.services import CurationService
    from media_curation.adapters.noop_producer import (
        NoOpProducerAdapter as CurationNoOpProducer,
    )

    # Initialise before try so they're available in the except block.
    storage_bucket = ""
    mime_type = "application/octet-stream"

    try:
        config = get_media_curation_config()
        kafka_config = config.get("KAFKA", {})

        # Resolve curated bucket — fall back to raw bucket if curated is
        # not configured, since we know the raw bucket exists (ingestion
        # already wrote to it successfully).
        curated_bucket = event_data.get("curated_bucket")
        if not curated_bucket and tenant and hasattr(tenant, "get_curated_bucket"):
            curated_bucket = tenant.get_curated_bucket()
        raw_bucket = event_data.get("raw_bucket")
        storage_bucket = (
            curated_bucket
            or config.get("STORAGE", {}).get("CURATED_BUCKET", "")
            or raw_bucket
            or "zorven-curated-assets"
        )

        # Build CurationEvent from ingestion result
        dest_path = ingestion_result.get(
            "destination_path", event_data.get("file_path", "")
        )
        mime_type = event_data.get("file_type", "application/octet-stream")

        logger.info(
            "Curation stage: raw_gcs_uri=%s, curated_bucket=%s, mime=%s",
            dest_path,
            storage_bucket,
            mime_type,
        )

        def _detect(mt: str) -> ContentType:
            if mt.startswith("video/"):
                return ContentType.VIDEO
            if mt.startswith("audio/"):
                return ContentType.AUDIO
            if mt.startswith("image/"):
                return ContentType.IMAGE
            return ContentType.DOCUMENT

        curation_event = CurationEvent(
            event_id=uuid4(),
            trace_id=(
                UUID(ingestion_result["trace_id"])
                if ingestion_result.get("trace_id")
                else uuid4()
            ),
            timestamp=datetime.now(timezone.utc),
            tenant_id=event_data.get("tenant_id", "public"),
            file_id=uuid4(),
            raw_gcs_uri=dest_path,
            mime_type=mime_type,
            content_type=_detect(mime_type),
            source_service="data-ingestion",
            metadata={
                **(event_data.get("metadata") or {}),
                "curated_bucket": curated_bucket,
            },
            curated_bucket=curated_bucket,
        )

        # Create CurationService with NoOp producer
        service = CurationService(
            processor_factory=create_processor_factory(config, tenant=tenant),
            cache=create_cache_adapter(config),
            storage=create_storage_adapter(config, tenant=tenant),
            producer=CurationNoOpProducer(),
            dlp=create_dlp_adapter(config),
            output_topic=kafka_config.get("OUTPUT_TOPIC", "rag-sync-ready-topic"),
            dlq_topic=kafka_config.get("DLQ_TOPIC", "curation-dlq"),
            output_bucket=storage_bucket,
        )

        result = service.process_event(curation_event)

        # Update BrandAsset → curated
        _update_asset_status(
            asset_id,
            "curated",
            tenant_id=event_data.get("tenant_id", ""),
        )

        logger.info(
            "Curation succeeded for asset %s (doc_id=%s)",
            asset_id,
            result.document_id if result else "N/A",
        )
        return {
            "status": "success",
            "document_id": str(result.document_id) if result else None,
            "output_uri": result.output_gcs_uri if result else None,
        }

    except Exception as e:
        error_msg = (
            f"Curation failed (bucket={storage_bucket}, " f"mime={mime_type}): {e}"
        )
        logger.error(error_msg, extra={"asset_id": asset_id}, exc_info=True)
        _update_asset_status(
            asset_id,
            "failed",
            error_msg=error_msg,
            tenant_id=event_data.get("tenant_id", ""),
        )
        return {"status": "failed", "error": error_msg}


def _run_indexing(
    self,
    asset_id: int,
    tenant_id: str,
    event_data: dict,
    curation_result: dict,
) -> dict:
    """Execute the RAG indexing stage via the existing sync_document task.

    Builds a ``SyncEvent`` dict from the curation output and dispatches
    it **synchronously** through the ``SyncOrchestrator`` (same pattern
    as ``sync_document`` Celery task in ``rag_index``).

    Args:
        self: Parent Celery task (for logging context).
        asset_id: ``BrandAsset.id``.
        tenant_id: Tenant pk as string.
        event_data: Original ingestion event dict.
        curation_result: Dict returned by ``_run_curation()``.

    Returns:
        Dict summarising the indexing result.
    """
    from rag_index.domain.models import SyncAction, SyncEvent
    from rag_index.tasks.sync_tasks import get_orchestrator, run_async

    # Initialise before try so it's available in the except block.
    output_uri = ""

    try:
        output_uri = curation_result.get("output_uri", "")
        document_id = curation_result.get("document_id", "")
        trace_id = event_data.get("trace_id", str(uuid4()))

        if not output_uri:
            logger.warning(
                "No output_uri from curation for asset %s — skipping indexing",
                asset_id,
            )
            # Still mark curated (indexing skipped, not failed)
            return {"status": "skipped", "reason": "no output_uri from curation"}

        sync_event = SyncEvent(
            event_id=uuid4(),
            trace_id=trace_id,
            tenant_id=tenant_id,
            file_id=document_id or str(asset_id),
            processed_gcs_uri=output_uri,
            action=SyncAction.UPSERT,
            metadata={
                **(event_data.get("metadata") or {}),
                "asset_id": asset_id,
                "source_task": "process_asset_pipeline_sync",
            },
        )

        orchestrator = get_orchestrator()
        result = run_async(orchestrator.process_event(sync_event))

        # Update BrandAsset → indexed
        _update_asset_status(asset_id, "indexed", tenant_id=tenant_id)

        logger.info(
            "Indexing succeeded for asset %s (operation=%s)",
            asset_id,
            result.operation_id if result else "N/A",
        )
        return {
            "status": "success",
            "operation_id": result.operation_id if result else None,
            "processing_time_ms": result.processing_time_ms if result else 0,
        }

    except Exception as e:
        error_msg = (
            f"Indexing failed (output_uri={output_uri}, " f"tenant={tenant_id}): {e}"
        )
        logger.error(error_msg, extra={"asset_id": asset_id}, exc_info=True)
        # Don't mark as "failed" here — the caller
        # (process_asset_pipeline_sync) handles indexing failures as
        # non-fatal when curation has succeeded.
        return {"status": "failed", "error": error_msg}


@shared_task(bind=True, max_retries=3, ignore_result=True)
def export_company_for_rag(self, company_id: int) -> dict[str, Any]:
    """Export company data for RAG indexing.

    Delegates to the unified ``sync_model_to_rag`` task from
    ``rag_index.tasks.db_sync_tasks``. Kept for backward compatibility
    with manual invocations and existing beat schedules.
    """
    from .models import Company
    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    try:
        company = Company.objects.select_related("tenant").get(id=company_id)
    except Company.DoesNotExist:
        logger.error("Company %s not found, cannot export for RAG", company_id)
        return {"status": "error", "message": f"Company {company_id} not found"}

    tenant_id = str(company.tenant.id) if company.tenant else None

    try:
        sync_model_to_rag.apply_async(
            args=["Company", company_id, tenant_id],
        )
        logger.info("Delegated company %s RAG export to sync_model_to_rag", company_id)
        return {"status": "delegated", "company_id": company_id}
    except Exception as exc:
        logger.exception("Failed to delegate company %s RAG export", company_id)
        raise self.retry(exc=exc, countdown=2**self.request.retries * 10)


@shared_task(bind=True, max_retries=3, ignore_result=True)
def batch_export_companies_for_rag(
    self, tenant_id: int | None = None
) -> dict[str, Any]:
    """Export all companies for RAG indexing.

    Delegates to the unified ``sync_model_to_rag`` task.
    """
    from .models import Company
    from rag_index.tasks.db_sync_tasks import sync_model_to_rag

    if tenant_id:
        companies = Company.objects.filter(tenant_id=tenant_id)
    else:
        companies = Company.objects.all()

    count = 0
    for company in companies.select_related("tenant").iterator():
        t_id = str(company.tenant.id) if company.tenant else None
        sync_model_to_rag.apply_async(
            args=["Company", company.id, t_id],
            countdown=count * 0.1,
        )
        count += 1

    logger.info("Queued %d companies for RAG export (tenant_id=%s)", count, tenant_id)
    return {"status": "success", "queued_count": count, "tenant_id": tenant_id}


# ---------------------------------------------------------------------------
# Brand asset summarization — feeds the orchestrator's BRAND CONTEXT preamble
# ---------------------------------------------------------------------------


def _build_asset_summary_prompt(asset, company) -> str:
    """Prompt for a short description of what a brand asset likely contains."""
    from brand_automator.validators import sanitize_ai_prompt

    def _clean(value, default=""):
        raw = value if value else default
        if not raw:
            return ""
        try:
            return sanitize_ai_prompt(str(raw))
        except Exception:  # pragma: no cover — defensive
            return str(raw)

    location = ""
    if company and getattr(company, "has_local_scope", False):
        location = f" at {_clean(company.formatted_address)}"
    industry = _clean(getattr(company, "industry", ""), "unspecified")
    brand_name = _clean(getattr(company, "name", ""), "the brand")
    description = _clean(getattr(company, "description", ""))
    file_name = _clean(getattr(asset, "file_name", ""))
    file_type = _clean(getattr(asset, "file_type", ""))

    return (
        "You are describing a file that was uploaded to a brand's onboarding. "
        "Produce a SINGLE SENTENCE (max 25 words) describing what this file "
        "most likely contains and how downstream marketing agents should use "
        "it. Be specific to the brand's industry — do not give a generic "
        "description. Do not speculate beyond what the filename suggests.\n\n"
        f"Brand: {brand_name}\n"
        f"Industry: {industry}{location}\n"
        f"Brand description: {description}\n"
        f"File name: {file_name}\n"
        f"File type: {file_type}\n\n"
        "Respond with ONLY the one-sentence description — no preamble, no "
        "quotes, no trailing notes."
    )


@shared_task(
    bind=True,
    name="onboarding.tasks.generate_brand_asset_summary",
    max_retries=2,
    default_retry_delay=30,
)
def generate_brand_asset_summary(self, asset_id: int, tenant_id: str = "") -> dict:
    """
    Generate a short LLM description of a BrandAsset and store it on
    ``BrandAsset.summary``. This summary is injected into the orchestrator's
    BRAND CONTEXT preamble so every downstream agent knows what each file
    is about without needing to retrieve it from RAG first.

    This is a "fast tier" summary — it uses only the file metadata plus
    the tenant's company context (industry, description, location). It
    does NOT fetch file contents from GCS. A future enhancement can add
    actual content extraction (PDF text, image vision) for higher-fidelity
    summaries.

    Idempotent: returns early if ``summary`` is already populated.
    No-op when Gemini is not configured.
    """
    from onboarding.models import BrandAsset
    from brand_automator.tenant_utils import (
        parse_tenant_pk,
        ensure_public_db_connection,
    )

    try:
        ensure_public_db_connection()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("ensure_public_db_connection failed: %s", exc)

    tenant_pk = parse_tenant_pk(tenant_id) if tenant_id else None
    qs = BrandAsset.objects.select_related("company", "company__tenant")
    if tenant_pk is not None:
        qs = qs.filter(tenant_id=tenant_pk)

    try:
        asset = qs.get(pk=asset_id)
    except BrandAsset.DoesNotExist:
        logger.warning(
            "generate_brand_asset_summary: asset %s not found (tenant=%s)",
            asset_id,
            tenant_id,
        )
        return {"status": "not_found", "asset_id": asset_id}

    if asset.summary:
        return {
            "status": "already_summarized",
            "asset_id": asset_id,
            "summary": asset.summary,
        }

    try:
        from ai_services.services import GeminiAIService

        gemini = GeminiAIService()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("GeminiAIService unavailable: %s", exc)
        return {"status": "llm_unavailable", "asset_id": asset_id}

    if getattr(gemini, "model", None) is None:
        logger.info(
            "generate_brand_asset_summary: Gemini not configured, skipping " "asset %s",
            asset_id,
        )
        return {"status": "llm_unavailable", "asset_id": asset_id}

    prompt = _build_asset_summary_prompt(asset, asset.company)

    try:
        response = gemini.model.generate_content(prompt)
        text = (getattr(response, "text", "") or "").strip()
    except Exception as exc:
        logger.warning("Gemini summary failed for asset %s: %s", asset_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "failed", "asset_id": asset_id, "error": str(exc)}

    # Trim to a sane length — preamble token budget matters.
    if len(text) > 400:
        text = text[:400].rsplit(" ", 1)[0] + "…"

    if not text:
        return {"status": "empty", "asset_id": asset_id}

    BrandAsset.objects.filter(pk=asset_id).update(summary=text)
    logger.info("Generated summary for asset %s: %s", asset_id, text[:80])
    return {"status": "success", "asset_id": asset_id, "summary": text}
