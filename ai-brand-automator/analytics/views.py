import hashlib
import logging
from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.models import MetricDefinition, MetricRollup, MetricSnapshot
from analytics.serializers import (
    ComparisonSerializer,
    MetricDefinitionSerializer,
    ScorecardItemSerializer,
    TrendPointSerializer,
    parse_time_range,
)

logger = logging.getLogger(__name__)

# Max data points per response (OG-03)
MAX_DATA_POINTS = 10000
CACHE_TTL = 300  # 5 minutes


def _cache_key(tenant_id, endpoint, params):
    """Generate cache key with tenant-scoped version."""
    version = cache.get(f"analytics:version:{tenant_id}", "v0")
    raw = f"{endpoint}:{sorted(params.items())}:{version}"
    query_hash = hashlib.md5(raw.encode()).hexdigest()
    return f"analytics:cache:{tenant_id}:{query_hash}"


def _get_tenant(request):
    """Get tenant from request with defensive access."""
    return getattr(request, "tenant", None)


class ScorecardView(APIView):
    """GET /api/v1/analytics/scorecard/ — KPI cards with sparklines."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response(
                {"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST
            )

        range_str = request.query_params.get("range", "30d")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        try:
            if start_date:
                start_date = date.fromisoformat(start_date)
            if end_date:
                end_date = date.fromisoformat(end_date)
            start, end = parse_time_range(range_str, start_date, end_date)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Check cache
        ck = _cache_key(
            tenant.id,
            "scorecard",
            {"range": range_str, "s": str(start_date), "e": str(end_date)},
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        # Calculate previous period for comparison
        duration = end - start
        prev_start = start - duration
        prev_end = start

        definitions = MetricDefinition.objects.all()
        results = []

        for defn in definitions:
            # Current period
            current_qs = MetricSnapshot.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                metric_name=defn.metric_name,
                recorded_at__gte=start,
                recorded_at__lte=end,
            )
            current_agg = current_qs.aggregate(
                avg_val=Avg("metric_value"), count=Count("id")
            )

            if not current_agg["count"]:
                continue

            current_value = round(current_agg["avg_val"], 2)

            # Previous period
            prev_qs = MetricSnapshot.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                metric_name=defn.metric_name,
                recorded_at__gte=prev_start,
                recorded_at__lt=prev_end,
            )
            prev_agg = prev_qs.aggregate(avg_val=Avg("metric_value"))
            previous_value = (
                round(prev_agg["avg_val"], 2) if prev_agg["avg_val"] else None
            )

            # Change calculation
            if previous_value and previous_value != 0:
                change_pct = round(
                    ((current_value - previous_value) / abs(previous_value)) * 100, 1
                )
            else:
                change_pct = 0.0

            # Trend direction
            if abs(change_pct) < 2:
                trend = "stable"
            elif change_pct > 0:
                trend = "improving"
            else:
                trend = "declining"

            # Sparkline data (last N values ordered chronologically)
            sparkline_values = list(
                current_qs.order_by("recorded_at").values_list(
                    "metric_value", flat=True
                )[:20]
            )

            results.append(
                {
                    "metric_name": defn.metric_name,
                    "display_name": defn.display_name,
                    "current_value": current_value,
                    "previous_value": previous_value,
                    "change_pct": change_pct,
                    "trend": trend,
                    "sparkline_data": sparkline_values,
                    "unit": defn.unit,
                    "color": defn.chart_color,
                    "higher_is_better": defn.higher_is_better,
                }
            )

        serializer = ScorecardItemSerializer(results, many=True)
        cache.set(ck, serializer.data, CACHE_TTL)
        return Response(serializer.data)


class TrendsView(APIView):
    """GET /api/v1/analytics/trends/ — Time-series data for a metric."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response(
                {"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST
            )

        metric = request.query_params.get("metric")
        if not metric:
            return Response(
                {"error": "metric parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        range_str = request.query_params.get("range", "30d")
        period = request.query_params.get("period", "daily")
        pipeline_id = request.query_params.get("pipeline_id")

        try:
            start, end = parse_time_range(range_str)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        ck = _cache_key(
            tenant.id,
            "trends",
            {
                "metric": metric,
                "range": range_str,
                "period": period,
                "pid": pipeline_id or "",
            },
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        qs = MetricRollup.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            metric_name=metric,
            period=period,
            period_start__gte=start.date(),
            period_start__lte=end.date(),
        )

        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)

        # OG-03: limit data points
        qs = qs.order_by("period_start")[:MAX_DATA_POINTS]

        data = list(
            qs.values(
                "period_start", "avg_value", "min_value", "max_value", "sample_count"
            )
        )

        serializer = TrendPointSerializer(data, many=True)
        cache.set(ck, serializer.data, CACHE_TTL)
        return Response(serializer.data)


class ComparisonView(APIView):
    """GET /api/v1/analytics/comparison/ — Period-over-period comparison."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response(
                {"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST
            )

        range_str = request.query_params.get("range", "30d")
        compare = request.query_params.get("compare", "previous")

        try:
            start, end = parse_time_range(range_str)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        duration = end - start
        if compare == "yoy":
            prev_start = start - timedelta(days=365)
            prev_end = end - timedelta(days=365)
        else:
            prev_start = start - duration
            prev_end = start

        ck = _cache_key(
            tenant.id,
            "comparison",
            {"range": range_str, "compare": compare},
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        definitions = MetricDefinition.objects.all()
        results = []

        for defn in definitions:
            current_avg = MetricSnapshot.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                metric_name=defn.metric_name,
                recorded_at__gte=start,
                recorded_at__lte=end,
            ).aggregate(avg=Avg("metric_value"))["avg"]

            if current_avg is None:
                continue

            prev_avg = MetricSnapshot.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                metric_name=defn.metric_name,
                recorded_at__gte=prev_start,
                recorded_at__lt=prev_end,
            ).aggregate(avg=Avg("metric_value"))["avg"]

            current_avg = round(current_avg, 2)
            prev_avg = round(prev_avg, 2) if prev_avg else 0.0

            if prev_avg != 0:
                change_pct = round(((current_avg - prev_avg) / abs(prev_avg)) * 100, 1)
            else:
                change_pct = 0.0

            if abs(change_pct) < 2:
                trend = "stable"
            elif change_pct > 0:
                trend = "improving"
            else:
                trend = "declining"

            results.append(
                {
                    "metric": defn.metric_name,
                    "display_name": defn.display_name,
                    "current_avg": current_avg,
                    "previous_avg": prev_avg,
                    "change_pct": change_pct,
                    "trend": trend,
                }
            )

        serializer = ComparisonSerializer(results, many=True)
        cache.set(ck, serializer.data, CACHE_TTL)
        return Response(serializer.data)


class DistributionView(APIView):
    """GET /api/v1/analytics/distribution/ — Sentiment distribution."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response(
                {"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST
            )

        metric = request.query_params.get("metric", "sentiment_positive_pct")
        range_str = request.query_params.get("range", "30d")

        try:
            start, end = parse_time_range(range_str)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        ck = _cache_key(
            tenant.id,
            "distribution",
            {"metric": metric, "range": range_str},
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        base_filter = Q(tenant=tenant) | Q(tenant__isnull=True)
        time_filter = Q(recorded_at__gte=start, recorded_at__lte=end)

        positive = (
            MetricSnapshot.objects.filter(
                base_filter,
                time_filter,
                metric_name="sentiment_positive_pct",
            ).aggregate(avg=Avg("metric_value"))["avg"]
            or 0
        )

        negative = (
            MetricSnapshot.objects.filter(
                base_filter,
                time_filter,
                metric_name="sentiment_negative_pct",
            ).aggregate(avg=Avg("metric_value"))["avg"]
            or 0
        )

        neutral = max(0, 100 - positive - negative)

        data = {
            "positive_pct": round(positive, 1),
            "neutral_pct": round(neutral, 1),
            "negative_pct": round(negative, 1),
        }

        cache.set(ck, data, CACHE_TTL)
        return Response(data)


class MetricsListView(APIView):
    """GET /api/v1/analytics/metrics/ — MetricDefinition list."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        definitions = MetricDefinition.objects.all()
        serializer = MetricDefinitionSerializer(definitions, many=True)
        return Response(serializer.data)


class CoverageView(APIView):
    """GET /api/v1/analytics/coverage/ — Analytics coverage stats."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response(
                {"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST
            )

        from orchestration.models import AnalysisJob

        total_jobs = AnalysisJob.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            status=AnalysisJob.Status.COMPLETED,
        ).count()

        analytics_jobs = (
            MetricSnapshot.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
            )
            .values("job_id")
            .distinct()
            .count()
        )

        excluded_jobs = AnalysisJob.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            status=AnalysisJob.Status.COMPLETED,
            input_context__analytics_excluded=True,
        ).count()

        coverage_pct = (
            round((analytics_jobs / total_jobs) * 100, 1) if total_jobs else 0
        )

        return Response(
            {
                "total_jobs": total_jobs,
                "analytics_jobs": analytics_jobs,
                "excluded_jobs": excluded_jobs,
                "coverage_pct": coverage_pct,
            }
        )
