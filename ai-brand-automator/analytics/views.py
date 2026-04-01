import hashlib
import logging
from datetime import date, timedelta

from django.conf import settings as django_settings
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
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
    query_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"analytics:cache:{tenant_id}:{query_hash}"


def _apply_brand_context_filter(qs, brand_context):
    """Apply brand_context filter to a MetricSnapshot queryset."""
    if brand_context:
        qs = qs.filter(metadata__brand_context_id=brand_context)
    return qs


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

        brand_ctx = request.query_params.get("brand_context", "")

        # Check cache
        ck = _cache_key(
            tenant.id,
            "scorecard",
            {
                "range": range_str,
                "s": str(start_date),
                "e": str(end_date),
                "bc": brand_ctx,
            },
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        # Calculate previous period for comparison
        duration = end - start
        prev_start = start - duration
        prev_end = start

        # Grouped aggregation to avoid N+1 per-metric queries
        tenant_filter = Q(tenant=tenant) | Q(tenant__isnull=True)

        current_qs = MetricSnapshot.objects.filter(
            tenant_filter,
            recorded_at__gte=start,
            recorded_at__lte=end,
        )
        current_qs = _apply_brand_context_filter(current_qs, brand_ctx)

        current_map = {}
        for row in current_qs.values("metric_name").annotate(
            avg_val=Avg("metric_value"), count=Count("id")
        ):
            current_map[row["metric_name"]] = (
                row["avg_val"],
                row["count"],
            )

        prev_qs = MetricSnapshot.objects.filter(
            tenant_filter,
            recorded_at__gte=prev_start,
            recorded_at__lt=prev_end,
        )
        prev_qs = _apply_brand_context_filter(prev_qs, brand_ctx)

        prev_map = {}
        for row in prev_qs.values("metric_name").annotate(
            avg_val=Avg("metric_value"),
        ):
            prev_map[row["metric_name"]] = row["avg_val"]

        definitions = MetricDefinition.objects.all()
        defn_map = {d.metric_name: d for d in definitions}
        results = []

        for metric_name, (current_avg, count) in current_map.items():
            defn = defn_map.get(metric_name)
            if not defn or not count:
                continue

            current_value = round(current_avg, 2)
            prev_avg = prev_map.get(metric_name)
            previous_value = round(prev_avg, 2) if prev_avg else None

            # Change calculation
            if previous_value and previous_value != 0:
                change_pct = round(
                    ((current_value - previous_value) / abs(previous_value)) * 100,
                    1,
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
            sparkline_qs = MetricSnapshot.objects.filter(
                tenant_filter,
                metric_name=metric_name,
                recorded_at__gte=start,
                recorded_at__lte=end,
            )
            sparkline_qs = _apply_brand_context_filter(sparkline_qs, brand_ctx)
            sparkline_values = list(
                sparkline_qs.order_by("recorded_at").values_list(
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

        # Sort by MetricDefinition display_order so tiles appear consistently
        def sort_key(result):
            definition = defn_map.get(result["metric_name"])
            return definition.display_order if definition is not None else 999

        results.sort(key=sort_key)

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

        brand_ctx = request.query_params.get("brand_context", "")

        ck = _cache_key(
            tenant.id,
            "trends",
            {
                "metric": metric,
                "range": range_str,
                "period": period,
                "pid": pipeline_id or "",
                "bc": brand_ctx,
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

        # Note: MetricRollup does not have a metadata field, so brand_context
        # filtering is not applied to trends. Rollups are pre-aggregated across
        # all brand contexts. Per-brand trend data would require rollup
        # partitioning (future enhancement).

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

        brand_ctx = request.query_params.get("brand_context", "")

        ck = _cache_key(
            tenant.id,
            "comparison",
            {"range": range_str, "compare": compare, "bc": brand_ctx},
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        # Grouped aggregation to avoid N+1 queries
        tenant_filter = Q(tenant=tenant) | Q(tenant__isnull=True)

        current_qs = MetricSnapshot.objects.filter(
            tenant_filter,
            recorded_at__gte=start,
            recorded_at__lte=end,
        )
        current_qs = _apply_brand_context_filter(current_qs, brand_ctx)

        current_map = {}
        for row in current_qs.values("metric_name").annotate(avg=Avg("metric_value")):
            current_map[row["metric_name"]] = row["avg"]

        prev_qs = MetricSnapshot.objects.filter(
            tenant_filter,
            recorded_at__gte=prev_start,
            recorded_at__lt=prev_end,
        )
        prev_qs = _apply_brand_context_filter(prev_qs, brand_ctx)

        prev_map = {}
        for row in prev_qs.values("metric_name").annotate(avg=Avg("metric_value")):
            prev_map[row["metric_name"]] = row["avg"]

        definitions = MetricDefinition.objects.all()
        defn_lookup = {d.metric_name: d for d in definitions}
        results = []

        for metric_name, current_avg in current_map.items():
            defn = defn_lookup.get(metric_name)
            if not defn or current_avg is None:
                continue

            current_avg = round(current_avg, 2)
            prev_avg = prev_map.get(metric_name)
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

        range_str = request.query_params.get("range", "30d")

        try:
            start, end = parse_time_range(range_str)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        brand_ctx = request.query_params.get("brand_context", "")

        ck = _cache_key(
            tenant.id,
            "distribution",
            {"range": range_str, "bc": brand_ctx},
        )
        cached = cache.get(ck)
        if cached:
            return Response(cached)

        base_filter = Q(tenant=tenant) | Q(tenant__isnull=True)
        time_filter = Q(recorded_at__gte=start, recorded_at__lte=end)

        pos_qs = MetricSnapshot.objects.filter(
            base_filter,
            time_filter,
            metric_name="sentiment_positive_pct",
        )
        pos_qs = _apply_brand_context_filter(pos_qs, brand_ctx)
        positive = pos_qs.aggregate(avg=Avg("metric_value"))["avg"] or 0

        neg_qs = MetricSnapshot.objects.filter(
            base_filter,
            time_filter,
            metric_name="sentiment_negative_pct",
        )
        neg_qs = _apply_brand_context_filter(neg_qs, brand_ctx)
        negative = neg_qs.aggregate(avg=Avg("metric_value"))["avg"] or 0

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

        brand_ctx = request.query_params.get("brand_context", "")

        from orchestration.models import AnalysisJob

        job_filter = Q(tenant=tenant) | Q(tenant__isnull=True)
        job_qs = AnalysisJob.objects.filter(
            job_filter, status=AnalysisJob.Status.COMPLETED
        )
        if brand_ctx:
            job_qs = job_qs.filter(input_context__brand_context_id=brand_ctx)

        total_jobs = job_qs.count()

        snapshot_qs = MetricSnapshot.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
        )
        snapshot_qs = _apply_brand_context_filter(snapshot_qs, brand_ctx)
        analytics_jobs = snapshot_qs.values("job_id").distinct().count()

        excluded_qs = AnalysisJob.objects.filter(
            job_filter,
            status=AnalysisJob.Status.COMPLETED,
            input_context__analytics_excluded=True,
        )
        if brand_ctx:
            excluded_qs = excluded_qs.filter(input_context__brand_context_id=brand_ctx)
        excluded_jobs = excluded_qs.count()

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


class WF1ContextView(APIView):
    """GET /api/v1/analytics/wf1-context/ — Latest WF1 Brand Discovery result.

    Used by WF2 agents (BPA, etc.) to consume WF1 intelligence
    without Django ORM access. Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth (same pattern as callback endpoints)
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # For service-to-service calls, prefer X-Tenant-ID header over
        # request.tenant (which DefaultTenantMiddleware sets to the public
        # tenant based on hostname).
        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from orchestration.models import AnalysisJob

        # WF1 node result keys that indicate a Brand Discovery pipeline
        WF1_NODE_KEYS = {
            "market_research",
            "competitor_intelligence",
            "audience_persona",
            "trend_cultural",
            "voice_of_customer",
        }

        # Find latest completed WF1 job — seeded manifests first
        job = (
            AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
                manifest__pipeline_id__in=[
                    "brand-discovery-complete",
                    "brand-discovery-full",
                ],
            )
            .select_related("manifest")
            .order_by("-completed_at")
            .first()
        )

        # Fallback: workspace copies that contain all 5 WF1 node results
        if not job:
            candidates = AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
            ).order_by("-completed_at")[:20]
            for candidate in candidates:
                nr = (candidate.result_data or {}).get("node_results", {})
                if WF1_NODE_KEYS.issubset(nr.keys()):
                    job = candidate
                    break

        if not job:
            return Response(
                {"error": "No WF1 data"},
                status=status.HTTP_404_NOT_FOUND,
            )

        result_data = job.result_data or {}
        node_results = result_data.get("node_results", {})

        return Response(
            {
                "mra": node_results.get("market_research", {}),
                "cia": node_results.get("competitor_intelligence", {}),
                "apa": node_results.get("audience_persona", {}),
                "tcia": node_results.get("trend_cultural", {}),
                "voca": node_results.get("voice_of_customer", {}),
                "wf1_completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "wf1_job_id": str(job.job_id),
            }
        )


class BPAContextView(APIView):
    """GET /api/v1/analytics/bpa-context/ — Latest BPA positioning result.

    Used by WF2 agents (BAA, etc.) to consume BPA positioning strategy.
    Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from orchestration.models import AnalysisJob

        # Find latest completed BPA job
        job = (
            AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
                manifest__pipeline_id="brand-strategy-positioning",
            )
            .select_related("manifest")
            .order_by("-completed_at")
            .first()
        )

        # Fallback: any job with brand_positioning node results
        if not job:
            candidates = AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
            ).order_by("-completed_at")[:20]
            for candidate in candidates:
                nr = (candidate.result_data or {}).get("node_results", {})
                if "brand_positioning" in nr:
                    job = candidate
                    break

        if not job:
            return Response(
                {"error": "No BPA data"},
                status=status.HTTP_404_NOT_FOUND,
            )

        result_data = job.result_data or {}
        node_results = result_data.get("node_results", {})
        bpa = node_results.get("brand_positioning", {})

        return Response(
            {
                "recommended_positioning": bpa.get("recommended_positioning", {}),
                "positioning_candidates": bpa.get("positioning_candidates", []),
                "canvas": bpa.get("canvas", {}),
                "perceptual_maps": bpa.get("perceptual_maps", []),
                "differentiation": bpa.get("differentiation", {}),
                "strategy": bpa.get("strategy", {}),
                "confidence_score": bpa.get("confidence_score", 0.0),
                "bpa_completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "bpa_job_id": str(job.job_id),
            }
        )


class CompanyContextView(APIView):
    """GET /api/v1/analytics/company-context/ — Company model + portfolio.

    Used by WF2 agents (BAA, etc.) to load brand identity and portfolio.
    Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from onboarding.models import Company

        try:
            company = Company.objects.get(Q(tenant=tenant) | Q(tenant__isnull=True))
        except Company.DoesNotExist:
            return Response(
                {"error": "No company data"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Company.MultipleObjectsReturned:
            company = Company.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True)
            ).first()

        return Response(
            {
                "name": company.name,
                "description": company.description,
                "industry": company.industry,
                "target_audience": company.target_audience,
                "core_problem": company.core_problem,
                "website": company.website,
                "brand_voice": company.brand_voice,
                "values": company.values,
                "vision_statement": company.vision_statement,
                "mission_statement": company.mission_statement,
                "positioning_statement": company.positioning_statement,
                "tagline": company.tagline,
                "value_proposition": company.value_proposition,
                "elevator_pitch": company.elevator_pitch,
                "demographics": company.demographics,
                "psychographics": company.psychographics,
                "pain_points": company.pain_points,
                "desired_outcomes": company.desired_outcomes,
                "products": [],  # Populated from Odoo or future product model
            }
        )


class BrandContextOptionsView(APIView):
    """GET /api/v1/analytics/brand-context-options/

    Returns all brand entities (parent + sub-brands) for the Brand Context
    Selector. Reads from onboarding Company model (parent) and BAA
    architecture registry in Django Redis (sub-brands, written by BAA
    via brand-context-sync/).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response(
                {"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST
            )

        options = []

        # 1. Parent brand from Company model (always present)
        try:
            from onboarding.models import Company

            company = Company.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True)
            ).first()
            if company:
                options.append(
                    {
                        "brand_context_id": "parent",
                        "name": company.name or "Parent Brand",
                        "brand_scope": "parent",
                        "parent_brand": company.name or "",
                        "relationship_to_parent": "root",
                        "target_persona": company.target_audience or None,
                        "industry": company.industry or "",
                    }
                )
        except Exception:
            logger.warning("Could not load company for tenant %s", tenant.id)

        # 2. Sub-brands from BAA registry (only after BAA runs)
        try:
            cache_key = f"brand_context:{tenant.id}:options"
            sub_brands = cache.get(cache_key)
            if sub_brands and isinstance(sub_brands, list):
                for sb in sub_brands:
                    if sb.get("brand_scope") != "parent":
                        options.append(sb)
        except Exception:
            logger.warning(
                "Could not load brand context options for tenant %s", tenant.id
            )

        return Response(options)


class BPVContextView(APIView):
    """GET /api/v1/analytics/bpv-context/ — Latest BPV personality result.

    Used by WF2 agents (NTA, etc.) to consume BPV personality data.
    Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from orchestration.models import AnalysisJob

        # Find latest completed BPV job
        job = (
            AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
                manifest__pipeline_id="brand-strategy-personality",
            )
            .select_related("manifest")
            .order_by("-completed_at")
            .first()
        )

        # Fallback: any job with brand_personality node results
        if not job:
            candidates = AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
            ).order_by("-completed_at")[:20]
            for candidate in candidates:
                nr = (candidate.result_data or {}).get("node_results", {})
                if "brand_personality" in nr:
                    job = candidate
                    break

        # Fallback: check Django Redis cache
        if not job:
            cache_key = f"brand_personality:{tenant.id}:parent"
            cached = cache.get(cache_key)
            if cached and isinstance(cached, dict):
                return Response(
                    {
                        "aaker_profile": cached.get("aaker_profile", {}),
                        "archetype": cached.get("archetype", {}),
                        "values_hierarchy": cached.get("values_hierarchy", {}),
                        "emotional_map": {},
                        "voice_matrix": {},
                        "character_brief": {},
                        "confidence_score": 0.0,
                        "bpv_completed_at": None,
                        "bpv_job_id": None,
                        "source": "cache",
                    }
                )

        if not job:
            return Response(
                {"error": "No BPV data"},
                status=status.HTTP_404_NOT_FOUND,
            )

        result_data = job.result_data or {}
        node_results = result_data.get("node_results", {})
        bpv = node_results.get("brand_personality", {})

        return Response(
            {
                "aaker_profile": bpv.get("aaker_profile", {}),
                "archetype": bpv.get("archetype", {}),
                "values_hierarchy": bpv.get("values_hierarchy", {}),
                "emotional_map": bpv.get("emotional_map", {}),
                "voice_matrix": bpv.get("voice_matrix", {}),
                "character_brief": bpv.get("character_brief", {}),
                "confidence_score": bpv.get("confidence_score", 0.0),
                "bpv_completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "bpv_job_id": str(job.job_id),
            }
        )


class NTAContextView(APIView):
    """GET /api/v1/analytics/nta-context/ — Latest NTA naming result.

    Used by WF2 agents (BSA, etc.) to consume NTA naming data.
    Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from orchestration.models import AnalysisJob

        # Find latest completed NTA job
        job = (
            AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
                manifest__pipeline_id="brand-strategy-naming",
            )
            .select_related("manifest")
            .order_by("-completed_at")
            .first()
        )

        # Fallback: any job with brand_naming node results
        if not job:
            candidates = AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
            ).order_by("-completed_at")[:20]
            for candidate in candidates:
                nr = (candidate.result_data or {}).get("node_results", {})
                if "brand_naming" in nr:
                    job = candidate
                    break

        # Fallback: check Django Redis cache
        if not job:
            cache_key = f"brand_naming:{tenant.id}:parent"
            cached = cache.get(cache_key)
            if cached and isinstance(cached, dict):
                return Response(
                    {
                        "name_candidates": cached.get("name_candidates", []),
                        "shortlisted_names": cached.get("shortlisted_names", []),
                        "taglines": cached.get("taglines", []),
                        "naming_brief": cached.get("naming_brief", {}),
                        "availability_results": cached.get("availability_results", {}),
                        "confidence_score": cached.get("confidence_score", 0.0),
                        "nta_completed_at": None,
                        "nta_job_id": None,
                        "source": "cache",
                    }
                )

        if not job:
            return Response(
                {"error": "No NTA data"},
                status=status.HTTP_404_NOT_FOUND,
            )

        result_data = job.result_data or {}
        node_results = result_data.get("node_results", {})
        nta = node_results.get("brand_naming", {})

        return Response(
            {
                "name_candidates": nta.get("name_candidates", []),
                "shortlisted_names": nta.get("shortlisted_names", []),
                "taglines": nta.get("taglines", []),
                "naming_brief": nta.get("naming_brief", {}),
                "availability_results": nta.get("availability_results", {}),
                "confidence_score": nta.get("confidence_score", 0.0),
                "nta_completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "nta_job_id": str(job.job_id),
            }
        )


class BSAContextView(APIView):
    """GET /api/v1/analytics/bsa-context/ — Latest BSA brand story result.

    Used by WF3 agents (CGA, etc.) to consume BSA story arcs.
    Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from orchestration.models import AnalysisJob

        # Find latest completed BSA job
        job = (
            AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
                manifest__pipeline_id="brand-strategy-story",
            )
            .select_related("manifest")
            .order_by("-completed_at")
            .first()
        )

        # Fallback: any job with brand_story node results
        if not job:
            candidates = AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
            ).order_by("-completed_at")[:20]
            for candidate in candidates:
                nr = (candidate.result_data or {}).get("node_results", {})
                if "brand_story" in nr:
                    job = candidate
                    break

        if not job:
            return Response(
                {"error": "No BSA data"},
                status=status.HTTP_404_NOT_FOUND,
            )

        result_data = job.result_data or {}
        node_results = result_data.get("node_results", {})
        bsa = node_results.get("brand_story", {})

        return Response(
            {
                "origin_story": bsa.get("origin_story", {}),
                "mission_vision": bsa.get("mission_vision", {}),
                "pitches": bsa.get("pitches", {}),
                "channel_narratives": bsa.get("channel_narratives", {}),
                "story_style_guide": bsa.get("story_style_guide", {}),
                "subbrand_stories": bsa.get("subbrand_stories", []),
                "narrative_package": bsa.get("narrative_package", {}),
                "confidence_score": bsa.get("confidence_score", 0.0),
                "bsa_completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "bsa_job_id": str(job.job_id),
            }
        )


class CAAContextView(APIView):
    """GET /api/v1/analytics/caa-context/ — Latest CAA campaign architecture.

    Used by WF3 agents (CGA, etc.) to consume CAA campaign blueprint.
    Authenticated via X-Service-Token.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            from tenants.models import Tenant

            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except (Tenant.DoesNotExist, ValueError):
                pass
        if not tenant:
            tenant = _get_tenant(request)

        if not tenant:
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from orchestration.models import AnalysisJob

        # Find latest completed CAA job
        job = (
            AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
                manifest__pipeline_id="meta-campaign-architecture",
            )
            .select_related("manifest")
            .order_by("-completed_at")
            .first()
        )

        # Fallback: any job with campaign_architecture node results
        if not job:
            candidates = AnalysisJob.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                status=AnalysisJob.Status.COMPLETED,
            ).order_by("-completed_at")[:20]
            for candidate in candidates:
                nr = (candidate.result_data or {}).get("node_results", {})
                if "campaign_architecture" in nr:
                    job = candidate
                    break

        if not job:
            return Response(
                {"error": "No CAA data"},
                status=status.HTTP_404_NOT_FOUND,
            )

        result_data = job.result_data or {}
        node_results = result_data.get("node_results", {})
        caa = node_results.get("campaign_architecture", {})

        return Response(
            {
                "blueprint": caa.get("blueprint", {}),
                "funnel_map": caa.get("funnel_map", {}),
                "targeting_specs": caa.get("targeting_specs", []),
                "placement_budget": caa.get("placement_budget", {}),
                "test_plan": caa.get("test_plan", {}),
                "kpi_targets": caa.get("kpi_targets", {}),
                "performance_projections": caa.get(
                    "performance_projections", {}
                ),
                "risk_assessment": caa.get("risk_assessment", {}),
                "creative_briefs": caa.get("creative_briefs", []),
                "special_ad_category": caa.get("special_ad_category", ""),
                "meta_api_compatible": caa.get("meta_api_compatible", False),
                "confidence_score": caa.get("confidence_score", 0.0),
                "caa_completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "caa_job_id": str(job.job_id),
            }
        )


class BrandPersonalitySyncView(APIView):
    """POST /api/v1/analytics/brand-personality-sync/

    Called by BPV personality_persister to cache personality data in Django Redis.
    Authenticated via X-Service-Token (service-to-service).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant_id = request.data.get("tenant_id")
        brand_context_id = request.data.get("brand_context_id", "parent")
        aaker_profile = request.data.get("aaker_profile", {})
        archetype = request.data.get("archetype", {})
        values_hierarchy = request.data.get("values_hierarchy", {})

        if not tenant_id:
            return Response(
                {"error": "tenant_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"brand_personality:{tenant_id}:{brand_context_id}"
        cache.set(
            cache_key,
            {
                "aaker_profile": aaker_profile,
                "archetype": archetype,
                "values_hierarchy": values_hierarchy,
            },
            timeout=None,
        )

        logger.info(
            "Brand personality synced for tenant %s (context: %s)",
            tenant_id,
            brand_context_id,
        )
        return Response({"synced": True, "brand_context_id": brand_context_id})


class BrandContextSyncView(APIView):
    """POST /api/v1/analytics/brand-context-sync/

    Called by BAA strategy_persister to sync brand options to Django Redis.
    Authenticated via X-Service-Token (service-to-service).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # Service-token auth
        service_token = request.headers.get("X-Service-Token", "")
        expected_token = getattr(
            django_settings,
            "ORCHESTRATOR_SERVICE_TOKEN",
            "dev-service-token",
        )
        if service_token != expected_token:
            return Response(
                {"error": "Invalid service token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant_id = request.data.get("tenant_id")
        options = request.data.get("options")

        if not tenant_id or not isinstance(options, list):
            return Response(
                {"error": "tenant_id and options[] required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Write to Django Redis (DB 0)
        cache_key = f"brand_context:{tenant_id}:options"
        cache.set(cache_key, options, timeout=None)

        # Bump version for cache busting
        version_key = f"brand_context:{tenant_id}:version"
        try:
            current = cache.get(version_key) or 0
            cache.set(version_key, int(current) + 1, timeout=None)
        except Exception:
            cache.set(version_key, 1, timeout=None)

        logger.info(
            "Brand context synced for tenant %s: %d options",
            tenant_id,
            len(options),
        )
        return Response({"synced": len(options)})
