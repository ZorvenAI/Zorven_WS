"""
Shared result handler for pipeline job updates.

Extracted from the HTTP callback view so both the HTTP callback endpoint
and the Kafka result consumer can reuse the same logic.

handle_pipeline_result() is the single entry-point:
  - Atomic row lock (select_for_update)
  - Updates job fields (progress, status, result_data, error, manifest)
  - Caches state in Redis for fast UI polling
  - On COMPLETED: auto-creates an assistant ChatMessage with the summary
"""

import logging

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import AnalysisJob, PipelineManifest

logger = logging.getLogger(__name__)


def handle_pipeline_result(
    job_id,
    *,
    status=None,
    progress=None,
    result_data=None,
    error_message=None,
    resolved_manifest_id=None,
):
    """Process a pipeline result update for the given job.

    Called by both the HTTP callback endpoint and the Kafka result consumer.
    Uses ``select_for_update()`` row locking for idempotent processing
    when both paths fire for the same event.

    Returns:
        True if the update was applied, False if the job was not found.
    """
    with transaction.atomic():
        try:
            job = AnalysisJob.objects.select_for_update().get(job_id=job_id)
        except AnalysisJob.DoesNotExist:
            logger.warning("handle_pipeline_result: job %s not found", job_id)
            return False

        update_fields = ["updated_at"]

        # Update progress
        if progress is not None:
            job.progress = progress
            update_fields.append("progress")

        # Update status
        if status is not None:
            job.status = status
            update_fields.append("status")

            if status in (
                AnalysisJob.Status.COMPLETED,
                AnalysisJob.Status.FAILED,
            ):
                job.completed_at = timezone.now()
                update_fields.append("completed_at")

        # Update result_data
        if result_data is not None:
            job.result_data = result_data
            update_fields.append("result_data")

        # Update error_message
        if error_message is not None:
            job.error_message = error_message
            update_fields.append("error_message")

        # Handle resolved_manifest_id (intent routing resolution)
        if resolved_manifest_id and job.manifest is None:
            try:
                resolved = PipelineManifest.objects.get(
                    pipeline_id=resolved_manifest_id,
                    is_active=True,
                )
                job.manifest = resolved
                update_fields.append("manifest")
                logger.info(
                    "Job %s: manifest resolved to %s via intent routing",
                    job.job_id,
                    resolved_manifest_id,
                )
            except PipelineManifest.DoesNotExist:
                logger.warning(
                    "Job %s: resolved_manifest_id '%s' not found",
                    job.job_id,
                    resolved_manifest_id,
                )

        job.save(update_fields=update_fields)

    # Cache job status in Redis for fast polling
    _update_redis_cache(job)

    # On terminal states: auto-create ChatMessage and release session lock
    if status in (AnalysisJob.Status.COMPLETED, AnalysisJob.Status.FAILED):
        _release_session_lock(job)
        if status == AnalysisJob.Status.COMPLETED:
            _save_final_chat_message(job)

    logger.info("Job %s result processed (status=%s)", job.job_id, status)
    return True


def _release_session_lock(job):
    """Clear the pipeline session lock so new chat messages can proceed."""
    session_id = (job.input_context or {}).get("session_id")
    if not session_id:
        return
    try:
        cache.delete(f"lock:chat:pipeline:{session_id}")
    except Exception:
        pass


def _update_redis_cache(job):
    """Push lightweight job state into Redis for quick-status polling."""
    try:
        cache_data = {
            "status": job.status,
            "progress": job.progress,
        }
        if job.status == AnalysisJob.Status.COMPLETED:
            cache_data["result_data"] = job.result_data
            cache_data["manifest_name"] = (
                job.manifest.name if job.manifest else None
            )
        elif job.status == AnalysisJob.Status.FAILED:
            cache_data["error_message"] = job.error_message
        cache.set(f"job:status:{job.job_id}", cache_data, timeout=3600)
    except Exception:
        pass  # Cache failures must not break result processing


def _save_final_chat_message(job):
    """Create an assistant ChatMessage with the pipeline result summary.

    Looks up the originating ChatSession via ``input_context["session_id"]``
    and appends a summary message so the user sees the result in their
    chat history.
    """
    session_id = (job.input_context or {}).get("session_id")
    if not session_id:
        return

    try:
        from ai_services.models import ChatMessage, ChatSession

        session = ChatSession.objects.get(session_id=session_id)
    except ChatSession.DoesNotExist:
        logger.warning(
            "Job %s: session '%s' not found for final message",
            job.job_id,
            session_id,
        )
        return
    except Exception:
        logger.exception("Job %s: error looking up session", job.job_id)
        return

    # Build a human-readable summary from result_data
    summary = _build_result_summary(job)

    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=summary,
        metadata={
            "job_id": str(job.job_id),
            "source": "pipeline_result",
            "manifest_name": job.manifest.name if job.manifest else None,
        },
    )
    logger.info(
        "Job %s: final ChatMessage created in session %s",
        job.job_id,
        session_id,
    )


def _build_result_summary(job):
    """Build a concise text summary from the pipeline result_data."""
    result = job.result_data or {}

    # If the orchestrator provides a ready-made summary, use it
    if "final_response" in result:
        return result["final_response"]
    if "summary" in result:
        return result["summary"]

    # Fallback: generic completion notice
    manifest_name = job.manifest.name if job.manifest else "Pipeline"
    return (
        f"{manifest_name} analysis completed successfully. "
        "View the full results in the pipeline card above."
    )
