"""Tests for BrandNamingExtractor."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from analytics.extractors.brand_naming import BrandNamingExtractor


def _mock_job(result_data, tenant=None, manifest=None):
    """Build a mock AnalysisJob with result_data."""
    job = MagicMock()
    job.result_data = result_data
    job.tenant = tenant
    job.manifest = manifest
    job.input_context = {"pipeline_id": "brand-strategy-naming"}
    job.completed_at = None
    job.updated_at = None
    return job


def _full_nta_result():
    """Return a realistic NTA result nested under node_results."""
    return {
        "node_results": {
            "brand_naming": {
                "name_candidates": [
                    {
                        "name": "Voltara",
                        "scores": {
                            "linguistic": 82,
                            "memorability": 88,
                            "availability": 90,
                            "strategy_alignment": 85,
                            "overall": 86,
                        },
                    },
                    {
                        "name": "ChargeLine",
                        "scores": {
                            "linguistic": 70,
                            "memorability": 65,
                            "availability": 60,
                            "strategy_alignment": 80,
                            "overall": 69,
                        },
                    },
                ],
                "availability_results": {
                    "Voltara": {
                        "domain": {".com": True, ".io": True},
                        "social": {"twitter": True},
                        "trademark": {"clear": True, "conflicts": []},
                    },
                    "ChargeLine": {
                        "domain": {".com": False, ".io": True},
                        "social": {"twitter": False},
                        "trademark": {
                            "clear": False,
                            "conflicts": [{"title": "Existing"}],
                        },
                    },
                },
                "taglines": [
                    {"tagline": "Power Every Journey", "name": "Voltara"},
                    {"tagline": "Charge Ahead", "name": "ChargeLine"},
                ],
                "confidence_score": 0.82,
                "execution_time_ms": 4500,
            },
        },
    }


class TestBrandNamingExtractor:
    """Test NTA metric extraction."""

    def setup_method(self):
        self.extractor = BrandNamingExtractor()

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extracts_all_metrics(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_nta_result())
        metrics = self.extractor.extract(job)

        metric_names = [m.metric_name for m in metrics]
        assert "naming_candidates_count" in metric_names
        assert "naming_top_score" in metric_names
        assert "naming_linguistic_avg" in metric_names
        assert "naming_memorability_avg" in metric_names
        assert "naming_availability_avg" in metric_names
        assert "naming_strategy_alignment_avg" in metric_names
        assert "naming_domain_available_pct" in metric_names
        assert "naming_trademark_clear_pct" in metric_names
        assert "naming_taglines_count" in metric_names
        assert "naming_confidence" in metric_names
        assert "naming_execution_time" in metric_names

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_candidates_count(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_nta_result())
        metrics = self.extractor.extract(job)

        count_metric = next(
            m for m in metrics if m.metric_name == "naming_candidates_count"
        )
        assert count_metric.metric_value == 2.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_top_score(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_nta_result())
        metrics = self.extractor.extract(job)

        top = next(m for m in metrics if m.metric_name == "naming_top_score")
        assert top.metric_value == 86.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_domain_available_pct(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_nta_result())
        metrics = self.extractor.extract(job)

        pct = next(m for m in metrics if m.metric_name == "naming_domain_available_pct")
        # 1 out of 2 have .com available → 50%
        assert pct.metric_value == 50.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_trademark_clear_pct(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_nta_result())
        metrics = self.extractor.extract(job)

        pct = next(m for m in metrics if m.metric_name == "naming_trademark_clear_pct")
        # 1 out of 2 are clear → 50%
        assert pct.metric_value == 50.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_confidence_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_nta_result())
        metrics = self.extractor.extract(job)

        conf = next(m for m in metrics if m.metric_name == "naming_confidence")
        # 0.82 * 100 = 82.0
        assert conf.metric_value == 82.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_empty_result_returns_minimal(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job({"node_results": {"brand_naming": {}}})
        metrics = self.extractor.extract(job)

        # Should still get taglines_count (0)
        names = [m.metric_name for m in metrics]
        assert "naming_taglines_count" in names

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_fallback_to_direct_result(self, MockSnapshot):
        """When data is not under node_results, fall back to result_data."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(
            {
                "name_candidates": [
                    {"name": "Test", "scores": {"overall": 75}},
                ],
                "taglines": [],
                "confidence_score": 0.7,
                "execution_time_ms": 2000,
            }
        )
        metrics = self.extractor.extract(job)
        names = [m.metric_name for m in metrics]
        assert "naming_candidates_count" in names
        assert "naming_confidence" in names
