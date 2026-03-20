from django.contrib import admin
from analytics.models import MetricSnapshot, MetricRollup, MetricDefinition


@admin.register(MetricSnapshot)
class MetricSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "metric_name",
        "metric_value",
        "metric_unit",
        "pipeline_id",
        "tenant",
        "recorded_at",
    )
    list_filter = ("metric_category", "pipeline_id", "metric_unit")
    search_fields = ("metric_name", "pipeline_id")
    raw_id_fields = ("job", "tenant")
    readonly_fields = ("created_at",)


@admin.register(MetricRollup)
class MetricRollupAdmin(admin.ModelAdmin):
    list_display = (
        "metric_name",
        "period",
        "period_start",
        "avg_value",
        "sample_count",
        "trend_direction",
        "tenant",
    )
    list_filter = ("period", "trend_direction", "metric_category")
    search_fields = ("metric_name", "pipeline_id")
    raw_id_fields = ("tenant",)


@admin.register(MetricDefinition)
class MetricDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "metric_name",
        "display_name",
        "category",
        "unit",
        "higher_is_better",
        "display_order",
    )
    list_filter = ("category", "higher_is_better")
    search_fields = ("metric_name", "display_name")
