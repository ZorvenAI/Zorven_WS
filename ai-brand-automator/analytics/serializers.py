from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from analytics.models import MetricDefinition, MetricRollup, MetricSnapshot


class MetricSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricSnapshot
        fields = [
            "id",
            "pipeline_id",
            "metric_name",
            "metric_value",
            "metric_unit",
            "metric_category",
            "agent_source",
            "metadata",
            "recorded_at",
        ]


class MetricRollupSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricRollup
        fields = [
            "id",
            "pipeline_id",
            "metric_name",
            "metric_category",
            "period",
            "period_start",
            "avg_value",
            "min_value",
            "max_value",
            "latest_value",
            "sample_count",
            "trend_direction",
            "change_pct",
        ]


class MetricDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricDefinition
        fields = [
            "metric_name",
            "display_name",
            "category",
            "unit",
            "value_range_min",
            "value_range_max",
            "higher_is_better",
            "chart_color",
            "display_order",
            "description",
            "source_pipelines",
        ]


class ScorecardItemSerializer(serializers.Serializer):
    metric_name = serializers.CharField()
    display_name = serializers.CharField()
    current_value = serializers.FloatField()
    previous_value = serializers.FloatField(allow_null=True)
    change_pct = serializers.FloatField()
    trend = serializers.CharField()
    sparkline_data = serializers.ListField(child=serializers.FloatField())
    unit = serializers.CharField()
    color = serializers.CharField()
    higher_is_better = serializers.BooleanField()


class TrendPointSerializer(serializers.Serializer):
    period_start = serializers.DateField()
    avg_value = serializers.FloatField()
    min_value = serializers.FloatField()
    max_value = serializers.FloatField()
    sample_count = serializers.IntegerField()


class ComparisonSerializer(serializers.Serializer):
    metric = serializers.CharField()
    display_name = serializers.CharField()
    current_avg = serializers.FloatField()
    previous_avg = serializers.FloatField()
    change_pct = serializers.FloatField()
    trend = serializers.CharField()


# --- Utility ---


def parse_time_range(range_str: str, start_date=None, end_date=None):
    """Parse time range string or custom dates into (start, end) datetimes.

    Returns:
        Tuple of (start_datetime, end_datetime)

    Raises:
        serializers.ValidationError: if range is invalid or exceeds 2 years.
    """
    now = timezone.now()

    if start_date and end_date:
        start = (
            timezone.make_aware(
                timezone.datetime.combine(start_date, timezone.datetime.min.time())
            )
            if timezone.is_naive(
                timezone.datetime.combine(start_date, timezone.datetime.min.time())
            )
            else timezone.datetime.combine(start_date, timezone.datetime.min.time())
        )
        end = (
            timezone.make_aware(
                timezone.datetime.combine(end_date, timezone.datetime.max.time())
            )
            if timezone.is_naive(
                timezone.datetime.combine(end_date, timezone.datetime.max.time())
            )
            else timezone.datetime.combine(end_date, timezone.datetime.max.time())
        )
    else:
        range_map = {
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "90d": timedelta(days=90),
            "1y": timedelta(days=365),
        }
        delta = range_map.get(range_str)
        if not delta:
            raise serializers.ValidationError(
                f"Invalid range: {range_str}. Use 7d, 30d, 90d, 1y, or custom."
            )
        start = now - delta
        end = now

    # OG-02: max 2 year range
    if (end - start).days > 730:
        raise serializers.ValidationError("Time range cannot exceed 2 years.")

    return start, end
