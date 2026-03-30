from django.urls import path

from analytics.views import (
    BPAContextView,
    BPVContextView,
    BrandContextOptionsView,
    BrandContextSyncView,
    BrandPersonalitySyncView,
    CompanyContextView,
    ComparisonView,
    CoverageView,
    DistributionView,
    MetricsListView,
    NTAContextView,
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
    path("bpa-context/", BPAContextView.as_view(), name="analytics-bpa-context"),
    path("bpv-context/", BPVContextView.as_view(), name="analytics-bpv-context"),
    path(
        "company-context/",
        CompanyContextView.as_view(),
        name="analytics-company-context",
    ),
    path(
        "brand-context-options/",
        BrandContextOptionsView.as_view(),
        name="analytics-brand-context-options",
    ),
    path(
        "brand-context-sync/",
        BrandContextSyncView.as_view(),
        name="analytics-brand-context-sync",
    ),
    path(
        "brand-personality-sync/",
        BrandPersonalitySyncView.as_view(),
        name="analytics-brand-personality-sync",
    ),
    path("nta-context/", NTAContextView.as_view(), name="analytics-nta-context"),
]
