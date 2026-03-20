import json
import logging
import sys

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Max result_data size (5 MB)
MAX_RESULT_SIZE = 5 * 1024 * 1024


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def extract_metrics_task(self, job_id: int):
    """Extract metrics from a completed AnalysisJob.

    Idempotent via Redis key. Runs brand affinity verification before extraction.
    """
    from orchestration.models import AnalysisJob
    from analytics.brand_affinity import BrandAffinityVerifier
    from analytics.extractors import PIPELINE_EXTRACTORS
    from analytics.kafka_events import emit_analytics_event
    from analytics.models import MetricDefinition, MetricSnapshot
    from analytics.rollups import update_rollups

    redis_key = f"analytics:extracted:{job_id}"

    # Atomic idempotency guard — cache.add() is a SET-if-not-exists
    if not cache.add(redis_key, "processing", 86400):
        logger.debug("Job %s already extracted, skipping", job_id)
        return

    # IG-01: Job exists and is COMPLETED
    try:
        job = AnalysisJob.objects.select_related("manifest", "tenant").get(id=job_id)
    except AnalysisJob.DoesNotExist:
        logger.warning("AnalysisJob %s not found", job_id)
        return

    if job.status != AnalysisJob.Status.COMPLETED:
        logger.debug("Job %s not completed (status=%s)", job_id, job.status)
        return

    # IG-03: result_data non-empty
    if not job.result_data:
        logger.debug("Job %s has no result_data", job_id)
        cache.set(redis_key, "empty", 86400)
        return

    # IG-06: result_data size check
    try:
        result_size = sys.getsizeof(json.dumps(job.result_data))
        if result_size > MAX_RESULT_SIZE:
            logger.warning(
                "Job %s result_data too large (%d bytes)", job_id, result_size
            )
            cache.set(redis_key, "oversized", 86400)
            return
    except (TypeError, ValueError):
        pass

    # IG-04: pipeline_id mapped to an extractor
    pipeline_id = _resolve_pipeline_id(job)
    if pipeline_id not in PIPELINE_EXTRACTORS:
        logger.debug("No extractor for pipeline %s (job %s)", pipeline_id, job_id)
        cache.set(redis_key, "unmapped", 86400)
        return

    # IG-05: tenant exists
    if not job.tenant:
        logger.debug("Job %s has no tenant", job_id)
        cache.set(redis_key, "no_tenant", 86400)
        return

    # IG-07: Brand affinity verification
    try:
        verifier = BrandAffinityVerifier(job.tenant)
        should_extract, reason, scores = verifier.verify(job)
    except Exception as e:
        logger.warning("Brand affinity check failed for job %s: %s", job_id, e)
        should_extract, reason, scores = True, "verification_error_passthrough", {}

    if not should_extract:
        logger.info(
            "Job %s excluded by brand affinity: %s (scores=%s)",
            job_id,
            reason,
            scores,
        )
        # Tag the job
        ctx = job.input_context or {}
        ctx["analytics_excluded"] = True
        ctx["analytics_exclusion_reason"] = reason
        job.input_context = ctx
        job.save(update_fields=["input_context"])
        cache.set(redis_key, "excluded", 86400)

        # Emit rejection event
        tenant_id = str(job.tenant_id) if job.tenant_id else "unknown"
        emit_analytics_event(
            "brand.affinity.rejected",
            tenant_id,
            {
                "job_id": str(job.job_id),
                "reason": reason,
                "scores": scores,
                "job_company_name": (job.input_context or {}).get("company_name", ""),
                "tenant_brand_name": verifier.brand_name,
            },
        )
        return

    # Extract metrics
    extractor = PIPELINE_EXTRACTORS[pipeline_id]
    try:
        metrics = extractor.extract(job)
    except Exception as e:
        logger.error("Extraction failed for job %s: %s", job_id, e)
        raise self.retry(exc=e)

    if not metrics:
        logger.debug("No metrics extracted from job %s", job_id)
        cache.set(redis_key, "no_metrics", 86400)
        return

    # PG-02: Clamp values per MetricDefinition ranges
    definitions = {
        d.metric_name: d
        for d in MetricDefinition.objects.filter(
            metric_name__in=[m.metric_name for m in metrics]
        )
    }
    for m in metrics:
        defn = definitions.get(m.metric_name)
        if defn:
            m.metric_value = max(
                defn.value_range_min,
                min(defn.value_range_max, m.metric_value),
            )

    # Bulk create with conflict handling
    MetricSnapshot.objects.bulk_create(metrics, ignore_conflicts=True)

    # Update rollups
    try:
        update_rollups(job.tenant, pipeline_id, metrics)
    except Exception as e:
        logger.warning("Rollup update failed for job %s: %s", job_id, e)

    # Mark as extracted
    cache.set(redis_key, "extracted", 86400)

    # Bust analytics cache for this tenant
    _invalidate_tenant_cache(job.tenant_id)

    logger.info(
        "Extracted %d metrics from job %s (pipeline=%s, reason=%s)",
        len(metrics),
        job_id,
        pipeline_id,
        reason,
    )

    # Emit extraction event
    tenant_id = str(job.tenant_id) if job.tenant_id else "unknown"
    emit_analytics_event(
        "metrics.extracted",
        tenant_id,
        {
            "job_id": str(job.job_id),
            "pipeline_id": pipeline_id,
            "metrics_count": len(metrics),
            "metric_names": [m.metric_name for m in metrics],
            "affinity_reason": reason,
        },
    )


@shared_task
def reconcile_rollups_task():
    """Nightly task to recalculate all rollups and purge old snapshots."""
    from analytics.kafka_events import emit_analytics_event
    from analytics.rollups import purge_old_snapshots, reconcile_all_rollups

    rollups_updated = reconcile_all_rollups()
    purged = purge_old_snapshots(days=730, batch_size=1000)

    logger.info(
        "Reconciliation complete: %d rollups updated, %d snapshots purged",
        rollups_updated,
        purged,
    )

    emit_analytics_event(
        "rollup.updated",
        "system",
        {
            "periods_updated": ["daily", "weekly", "monthly"],
            "metrics_count": rollups_updated,
            "purged_count": purged,
            "reconciliation": True,
        },
    )


def _resolve_pipeline_id(job) -> str:
    """Resolve pipeline ID from manifest or input_context."""
    if job.manifest:
        return job.manifest.pipeline_id
    return (job.input_context or {}).get("pipeline_id", "unknown")


def _invalidate_tenant_cache(tenant_id):
    """Bust analytics cache entries for a tenant."""
    if tenant_id:
        try:
            # Django cache doesn't support wildcard delete natively,
            # so we use the cache key version pattern
            cache.set(f"analytics:version:{tenant_id}", str(id(object())), 300)
        except Exception:
            pass
