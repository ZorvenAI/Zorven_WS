"""
Tests for TrendsView cross-pipeline aggregation.

Verifies that when multiple pipeline_ids produce rollups for the same
metric on the same date, the endpoint returns one data point per date
using a weighted average (by sample_count).
"""

import pytest
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from analytics.models import MetricDefinition, MetricRollup

User = get_user_model()


@pytest.fixture
def trend_tenant(db):
    from tenants.models import Tenant, Domain
    from django.db import connection

    connection.set_schema_to_public()
    tenant = Tenant.objects.create(
        name="Trend Test",
        schema_name="trend_test",
        subscription_status="active",
        max_users=10,
        storage_limit_gb=5,
    )
    Domain.objects.create(tenant=tenant, domain="trendtest.localhost", is_primary=True)
    return tenant


@pytest.fixture
def trend_user(db):
    return User.objects.create_user(
        username="trend_user", email="trend@example.com", password="TestPass123!"
    )


@pytest.fixture
def trend_membership(db, trend_user, trend_tenant):
    from tenants.models import Membership

    return Membership.objects.create(
        user=trend_user,
        tenant=trend_tenant,
        role=Membership.Role.OWNER,
    )


@pytest.fixture
def trend_client(trend_user, trend_tenant, trend_membership):
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=trend_user)
    client.defaults["HTTP_X_TENANT_ID"] = str(trend_tenant.id)
    return client


@pytest.fixture
def metric_def(db):
    defn, _ = MetricDefinition.objects.get_or_create(
        metric_name="test_metric",
        defaults={
            "display_name": "Test Metric",
            "category": "test",
            "unit": "score",
            "higher_is_better": True,
            "chart_color": "#00F5FF",
            "display_order": 999,
        },
    )
    return defn


@pytest.fixture
def multi_pipeline_rollups(db, trend_tenant, metric_def):
    """Create rollups for the same metric/date from two different pipelines."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    rollups = []
    # Yesterday: single pipeline — no aggregation needed
    rollups.append(
        MetricRollup.objects.create(
            tenant=trend_tenant,
            pipeline_id="pipeline-a",
            metric_name="test_metric",
            metric_category="test",
            period="daily",
            period_start=yesterday,
            avg_value=10.0,
            min_value=8.0,
            max_value=12.0,
            latest_value=11.0,
            sample_count=2,
        )
    )
    # Today: two pipelines — must be aggregated
    rollups.append(
        MetricRollup.objects.create(
            tenant=trend_tenant,
            pipeline_id="pipeline-a",
            metric_name="test_metric",
            metric_category="test",
            period="daily",
            period_start=today,
            avg_value=20.0,
            min_value=18.0,
            max_value=22.0,
            latest_value=21.0,
            sample_count=1,
        )
    )
    rollups.append(
        MetricRollup.objects.create(
            tenant=trend_tenant,
            pipeline_id="pipeline-b",
            metric_name="test_metric",
            metric_category="test",
            period="daily",
            period_start=today,
            avg_value=10.0,
            min_value=5.0,
            max_value=15.0,
            latest_value=12.0,
            sample_count=3,
        )
    )
    return rollups


@pytest.mark.django_db
class TestTrendsViewAggregation:
    def test_returns_one_point_per_date(self, trend_client, multi_pipeline_rollups):
        """Multiple pipelines on the same date produce a single data point."""
        resp = trend_client.get(
            "/api/v1/analytics/trends/?metric=test_metric&range=7d&period=daily"
        )
        assert resp.status_code == 200
        data = resp.json()
        dates = [point["period_start"] for point in data]
        assert len(dates) == len(
            set(dates)
        ), "Expected one data point per date, got duplicates"
        assert len(data) == 2  # yesterday + today

    def test_uses_weighted_average(self, trend_client, multi_pipeline_rollups):
        """Aggregated avg_value uses weighted average by sample_count."""
        resp = trend_client.get(
            "/api/v1/analytics/trends/?metric=test_metric&range=7d&period=daily"
        )
        assert resp.status_code == 200
        data = resp.json()

        today_str = str(date.today())
        today_point = next(p for p in data if p["period_start"] == today_str)

        # Weighted avg: (20*1 + 10*3) / (1+3) = 50/4 = 12.5
        assert today_point["avg_value"] == 12.5
        assert today_point["sample_count"] == 4
        assert today_point["min_value"] == 5.0
        assert today_point["max_value"] == 22.0

    def test_single_pipeline_unchanged(self, trend_client, multi_pipeline_rollups):
        """Dates with a single pipeline return exact rollup values."""
        resp = trend_client.get(
            "/api/v1/analytics/trends/?metric=test_metric&range=7d&period=daily"
        )
        assert resp.status_code == 200
        data = resp.json()

        yesterday_str = str(date.today() - timedelta(days=1))
        yesterday_point = next(p for p in data if p["period_start"] == yesterday_str)

        assert yesterday_point["avg_value"] == 10.0
        assert yesterday_point["sample_count"] == 2

    def test_pipeline_id_filter_skips_aggregation(
        self, trend_client, multi_pipeline_rollups
    ):
        """When pipeline_id is specified, return that pipeline's raw rollups."""
        resp = trend_client.get(
            "/api/v1/analytics/trends/?metric=test_metric&range=7d"
            "&period=daily&pipeline_id=pipeline-a"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2  # pipeline-a has yesterday + today
        today_str = str(date.today())
        today_point = next(p for p in data if p["period_start"] == today_str)
        assert today_point["avg_value"] == 20.0  # raw, not weighted
