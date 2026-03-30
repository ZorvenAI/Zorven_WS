"""Tests for CampaignArchitectureExtractor."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from analytics.extractors.campaign_architecture import CampaignArchitectureExtractor


def _mock_job(result_data, tenant=None, manifest=None):
    """Build a mock AnalysisJob with result_data."""
    job = MagicMock()
    job.result_data = result_data
    job.tenant = tenant
    job.manifest = manifest
    job.input_context = {"pipeline_id": "campaign-architecture"}
    job.completed_at = None
    job.updated_at = None
    return job


def _full_caa_result():
    """Return a realistic CAA result nested under node_results."""
    return {
        "node_results": {
            "campaign_architecture": {
                "funnel_map": {
                    "stages": [
                        {"stage": "TOFU", "budget_pct": 0.40},
                        {"stage": "MOFU", "budget_pct": 0.25},
                        {"stage": "BOFU", "budget_pct": 0.20},
                        {"stage": "Retention", "budget_pct": 0.15},
                    ],
                },
                "blueprint": {
                    "campaign": {
                        "daily_budget": 250.00,
                        "objective": "conversions",
                    },
                    "ad_sets": [
                        {"name": "Tech Enthusiasts", "targeting": {}},
                        {"name": "Early Adopters", "targeting": {}},
                        {"name": "Budget Shoppers", "targeting": {}},
                    ],
                },
                "test_plan": {
                    "total_variants": 6,
                    "tests": [
                        {"type": "headline", "variants": 3},
                        {"type": "creative", "variants": 3},
                    ],
                },
                "performance_projections": {
                    "estimated_reach": 450000,
                    "estimated_ctr": 0.032,
                },
                "confidence_score": 0.87,
                "execution_time_ms": 3800,
            },
        },
    }


class TestCampaignArchitectureExtractor:
    """Test CAA metric extraction."""

    def setup_method(self):
        self.extractor = CampaignArchitectureExtractor()

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_empty_result_data(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job({"node_results": {"campaign_architecture": {}}})
        metrics = self.extractor.extract(job)
        assert metrics == []

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_funnel_stages_count(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        stages = next(
            m for m in metrics if m.metric_name == "campaign_funnel_stages_count"
        )
        assert stages.metric_value == 4.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_budget_tofu_pct(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        tofu = next(m for m in metrics if m.metric_name == "budget_tofu_pct")
        # 0.40 * 100 = 40.0
        assert tofu.metric_value == 40.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_budget_bofu_pct(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        bofu = next(m for m in metrics if m.metric_name == "budget_bofu_pct")
        # 0.20 * 100 = 20.0
        assert bofu.metric_value == 20.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_audience_segments_count(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        segments = next(
            m for m in metrics if m.metric_name == "audience_segments_count"
        )
        assert segments.metric_value == 3.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_daily_budget_total(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        budget = next(m for m in metrics if m.metric_name == "daily_budget_total")
        assert budget.metric_value == 250.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_ab_test_variants(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        variants = next(
            m for m in metrics if m.metric_name == "ab_test_variants_planned"
        )
        assert variants.metric_value == 6.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_estimated_reach(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        reach = next(m for m in metrics if m.metric_name == "estimated_reach")
        assert reach.metric_value == 450000.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_confidence_score(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        conf = next(
            m for m in metrics if m.metric_name == "campaign_architecture_confidence"
        )
        # 0.87 * 100 = 87.0
        assert conf.metric_value == 87.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_execution_time(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        et = next(
            m
            for m in metrics
            if m.metric_name == "campaign_architecture_execution_time"
        )
        assert et.metric_value == 3800.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_full_result(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_caa_result())
        metrics = self.extractor.extract(job)

        metric_names = [m.metric_name for m in metrics]
        assert "campaign_funnel_stages_count" in metric_names
        assert "budget_tofu_pct" in metric_names
        assert "budget_mofu_pct" in metric_names
        assert "budget_bofu_pct" in metric_names
        assert "budget_retention_pct" in metric_names
        assert "audience_segments_count" in metric_names
        assert "daily_budget_total" in metric_names
        assert "ab_test_variants_planned" in metric_names
        assert "estimated_reach" in metric_names
        assert "campaign_architecture_confidence" in metric_names
        assert "campaign_architecture_execution_time" in metric_names
        # 1 funnel count + 4 budget stages + 1 segments + 1 daily budget
        # + 1 variants + 1 reach + 1 confidence + 1 execution time = 11
        assert len(metrics) == 11
