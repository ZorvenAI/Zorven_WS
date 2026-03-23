from django.urls import path

from analytics.views import (
    ComparisonView,
    CoverageView,
    DistributionView,
    MetricsListView,
    ScorecardView,
    TrendsView,
    WF1ContextView,
)

urlpatterns = [
    path("scorecard/", ScorecardView.as_view(), name="analytics-scorecard"),
    path("trends/", TrendsView.as_view(), name="analytics-trends"),
    path("comparison/", ComparisonView.as_view(), name="analytics-comparison"),
    path("distribution/", DistributionView.as_view(), name="analytics-distribution"),
    path("metrics/", MetricsListView.as_view(), name="analytics-metrics"),
    path("coverage/", CoverageView.as_view(), name="analytics-coverage"),
    path("wf1-context/", WF1ContextView.as_view(), name="analytics-wf1-context"),
]
