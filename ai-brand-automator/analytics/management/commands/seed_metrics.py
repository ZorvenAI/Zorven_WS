from django.core.management.base import BaseCommand

from analytics.models import MetricDefinition

METRIC_DEFINITIONS = [
    {
        "metric_name": "nps",
        "display_name": "Net Promoter Score",
        "category": "customer_voice",
        "unit": "score",
        "value_range_min": -100,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#00F5FF",
        "display_order": 1,
        "description": "Net Promoter Score from Voice of Customer analysis",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
            "brand-analysis",
        ],
    },
    {
        "metric_name": "voc_health_score",
        "display_name": "VoC Health Score",
        "category": "customer_voice",
        "unit": "score",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#10B981",
        "display_order": 2,
        "description": "Overall Voice of Customer health score",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
            "brand-analysis",
        ],
    },
    {
        "metric_name": "sentiment_positive_pct",
        "display_name": "Positive Sentiment",
        "category": "customer_voice",
        "unit": "percent",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#34D399",
        "display_order": 3,
        "description": "Percentage of positive sentiment in customer feedback",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
        ],
    },
    {
        "metric_name": "sentiment_negative_pct",
        "display_name": "Negative Sentiment",
        "category": "customer_voice",
        "unit": "percent",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": False,
        "chart_color": "#EF4444",
        "display_order": 4,
        "description": "Percentage of negative sentiment in customer feedback",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
        ],
    },
    {
        "metric_name": "pain_points_count",
        "display_name": "Pain Points Identified",
        "category": "customer_voice",
        "unit": "count",
        "value_range_min": 0,
        "value_range_max": 1000,
        "higher_is_better": False,
        "chart_color": "#F59E0B",
        "display_order": 5,
        "description": "Number of customer pain points identified",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
        ],
    },
    {
        "metric_name": "data_coverage_pct",
        "display_name": "Data Coverage",
        "category": "customer_voice",
        "unit": "percent",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#8B5CF6",
        "display_order": 6,
        "description": "Percentage of data sources covered in VoC analysis",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
        ],
    },
    {
        "metric_name": "trends_identified",
        "display_name": "Trends Identified",
        "category": "trend_analysis",
        "unit": "count",
        "value_range_min": 0,
        "value_range_max": 1000,
        "higher_is_better": True,
        "chart_color": "#06B6D4",
        "display_order": 7,
        "description": "Number of cultural and market trends identified",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
        ],
    },
    {
        "metric_name": "personas_count",
        "display_name": "Personas Profiled",
        "category": "audience",
        "unit": "count",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#EC4899",
        "display_order": 8,
        "description": "Number of audience personas profiled",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
        ],
    },
    {
        "metric_name": "competitors_tracked",
        "display_name": "Competitors Tracked",
        "category": "competitive",
        "unit": "count",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#F97316",
        "display_order": 9,
        "description": "Number of competitors analyzed",
        "source_pipelines": [
            "brand-discovery-complete",
            "brand-discovery-full",
            "brand-analysis",
            "competitor-audit",
        ],
    },
    {
        "metric_name": "brand_equity_awareness",
        "display_name": "Brand Awareness",
        "category": "brand_equity",
        "unit": "score",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#3B82F6",
        "display_order": 10,
        "description": "ISO 10668 brand awareness score",
        "source_pipelines": ["iso-brand-equity"],
    },
    {
        "metric_name": "brand_equity_sentiment",
        "display_name": "Brand Sentiment",
        "category": "brand_equity",
        "unit": "score",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#6366F1",
        "display_order": 11,
        "description": "ISO 10668 brand sentiment score",
        "source_pipelines": ["iso-brand-equity"],
    },
    {
        "metric_name": "brand_equity_financials",
        "display_name": "Brand Financials",
        "category": "brand_equity",
        "unit": "score",
        "value_range_min": 0,
        "value_range_max": 100,
        "higher_is_better": True,
        "chart_color": "#14B8A6",
        "display_order": 12,
        "description": "ISO 10668 brand financial strength score",
        "source_pipelines": ["iso-brand-equity"],
    },
    {
        "metric_name": "brand_value_npv",
        "display_name": "Brand Value (NPV)",
        "category": "brand_equity",
        "unit": "currency",
        "value_range_min": 0,
        "value_range_max": 999999999999,
        "higher_is_better": True,
        "chart_color": "#22C55E",
        "display_order": 13,
        "description": "Net present value of brand equity",
        "source_pipelines": ["iso-brand-equity"],
    },
]


class Command(BaseCommand):
    help = "Seed MetricDefinition rows for workflow analytics"

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for defn in METRIC_DEFINITIONS:
            _, was_created = MetricDefinition.objects.update_or_create(
                metric_name=defn["metric_name"],
                defaults=defn,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated} existing "
                f"MetricDefinition rows (total: {len(METRIC_DEFINITIONS)})"
            )
        )
