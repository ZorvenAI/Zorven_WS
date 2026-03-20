import logging
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min
from django.utils import timezone

from analytics.models import MetricRollup, MetricSnapshot

logger = logging.getLogger(__name__)


def _get_period_start(dt, period: str):
    """Calculate the period start date for a given datetime."""
    d = dt.date() if hasattr(dt, "date") else dt
    if period == "daily":
        return d
    elif period == "weekly":
        return d - timedelta(days=d.weekday())  # Monday
    elif period == "monthly":
        return d.replace(day=1)
    return d


def _calculate_trend(current_avg: float, previous_avg: float | None) -> tuple:
    """Calculate trend direction and change percentage.

    Returns:
        (trend_direction, change_pct)
    """
    if previous_avg is None or previous_avg == 0:
        return MetricRollup.TrendDirection.STABLE, 0.0

    change_pct = ((current_avg - previous_avg) / abs(previous_avg)) * 100

    if abs(change_pct) < 2.0:
        direction = MetricRollup.TrendDirection.STABLE
    elif change_pct > 0:
        direction = MetricRollup.TrendDirection.IMPROVING
    else:
        direction = MetricRollup.TrendDirection.DECLINING

    return direction, round(change_pct, 2)


def update_rollups(tenant, pipeline_id: str, metrics: list[MetricSnapshot]):
    """Update rollup aggregates for the given metrics.

    Called after each extraction to keep rollups up to date.
    """
    # Group metrics by (metric_name, metric_category)
    metric_groups = {}
    for m in metrics:
        key = (m.metric_name, m.metric_category)
        metric_groups.setdefault(key, []).append(m)

    for (metric_name, category), group_metrics in metric_groups.items():
        for period in ["daily", "weekly", "monthly"]:
            for m in group_metrics:
                period_start = _get_period_start(m.recorded_at, period)

                # Get all snapshots for this period
                qs = MetricSnapshot.objects.filter(
                    tenant=tenant,
                    pipeline_id=pipeline_id,
                    metric_name=metric_name,
                    recorded_at__date__gte=period_start,
                )
                if period == "daily":
                    qs = qs.filter(
                        recorded_at__date__lte=period_start,
                    )
                elif period == "weekly":
                    qs = qs.filter(
                        recorded_at__date__lt=period_start + timedelta(days=7),
                    )
                elif period == "monthly":
                    next_month = period_start.replace(day=28) + timedelta(days=4)
                    next_month = next_month.replace(day=1)
                    qs = qs.filter(recorded_at__date__lt=next_month)

                aggs = qs.aggregate(
                    avg_val=Avg("metric_value"),
                    min_val=Min("metric_value"),
                    max_val=Max("metric_value"),
                    count=Count("id"),
                )

                if not aggs["count"]:
                    continue

                # Get latest value in period
                latest = (
                    qs.order_by("-recorded_at")
                    .values_list("metric_value", flat=True)
                    .first()
                )

                # Get previous period's avg for trend calc
                prev_rollup = (
                    MetricRollup.objects.filter(
                        tenant=tenant,
                        pipeline_id=pipeline_id,
                        metric_name=metric_name,
                        period=period,
                        period_start__lt=period_start,
                    )
                    .order_by("-period_start")
                    .values_list("avg_value", flat=True)
                    .first()
                )

                trend_dir, change_pct = _calculate_trend(aggs["avg_val"], prev_rollup)

                MetricRollup.objects.update_or_create(
                    tenant=tenant,
                    pipeline_id=pipeline_id,
                    metric_name=metric_name,
                    period=period,
                    period_start=period_start,
                    defaults={
                        "metric_category": category,
                        "avg_value": round(aggs["avg_val"], 4),
                        "min_value": round(aggs["min_val"], 4),
                        "max_value": round(aggs["max_val"], 4),
                        "latest_value": round(latest, 4) if latest else 0,
                        "sample_count": aggs["count"],
                        "trend_direction": trend_dir,
                        "change_pct": change_pct,
                    },
                )


def reconcile_all_rollups():
    """Recalculate all rollups from MetricSnapshot source of truth.

    Called by nightly reconciliation task.
    """
    # Get distinct tenant/pipeline/metric combos
    combos = MetricSnapshot.objects.values(
        "tenant_id", "pipeline_id", "metric_name", "metric_category"
    ).distinct()

    count = 0
    for combo in combos:
        tenant_id = combo["tenant_id"]
        pipeline_id = combo["pipeline_id"]
        metric_name = combo["metric_name"]
        category = combo["metric_category"]

        for period in ["daily", "weekly", "monthly"]:
            snapshots = MetricSnapshot.objects.filter(
                tenant_id=tenant_id,
                pipeline_id=pipeline_id,
                metric_name=metric_name,
            ).order_by("recorded_at")

            if not snapshots.exists():
                continue

            # Group by period
            period_buckets = {}
            for snap in snapshots:
                ps = _get_period_start(snap.recorded_at, period)
                period_buckets.setdefault(ps, []).append(snap.metric_value)

            prev_avg = None
            for period_start in sorted(period_buckets.keys()):
                values = period_buckets[period_start]
                avg_val = sum(values) / len(values)
                min_val = min(values)
                max_val = max(values)
                latest_val = values[-1]

                trend_dir, change_pct = _calculate_trend(avg_val, prev_avg)

                MetricRollup.objects.update_or_create(
                    tenant_id=tenant_id,
                    pipeline_id=pipeline_id,
                    metric_name=metric_name,
                    period=period,
                    period_start=period_start,
                    defaults={
                        "metric_category": category,
                        "avg_value": round(avg_val, 4),
                        "min_value": round(min_val, 4),
                        "max_value": round(max_val, 4),
                        "latest_value": round(latest_val, 4),
                        "sample_count": len(values),
                        "trend_direction": trend_dir,
                        "change_pct": change_pct,
                    },
                )
                prev_avg = avg_val
                count += 1

    return count


def purge_old_snapshots(days: int = 730, batch_size: int = 1000):
    """Purge MetricSnapshot records older than the specified number of days."""
    cutoff = timezone.now() - timedelta(days=days)
    total_deleted = 0

    while True:
        ids = list(
            MetricSnapshot.objects.filter(recorded_at__lt=cutoff).values_list(
                "id", flat=True
            )[:batch_size]
        )
        if not ids:
            break
        deleted, _ = MetricSnapshot.objects.filter(id__in=ids).delete()
        total_deleted += deleted

    if total_deleted:
        logger.info("Purged %d old MetricSnapshot records", total_deleted)

    return total_deleted
