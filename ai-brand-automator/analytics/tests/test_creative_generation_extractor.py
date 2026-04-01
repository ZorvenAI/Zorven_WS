"""Tests for CreativeGenerationExtractor."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from analytics.extractors.creative_generation import CreativeGenerationExtractor


def _mock_job(result_data, tenant=None, manifest=None):
    """Build a mock AnalysisJob with result_data."""
    job = MagicMock()
    job.result_data = result_data
    job.tenant = tenant
    job.manifest = manifest or MagicMock(pipeline_id="creative-generation")
    job.input_context = {
        "pipeline_id": "creative-generation",
        "brand_context_id": "ctx-123",
        "brand_scope": "test-brand",
    }
    job.id = "job-cga-001"
    job.created_at = "2026-03-31T00:00:00Z"
    job.completed_at = None
    job.updated_at = None
    return job


def _full_cga_result():
    """Return a realistic CGA result nested under node_results."""
    return {
        "node_results": {
            "creative_generation": {
                "creative_package": {
                    "total_images_generated": 12,
                    "image_gen_cost_usd": 4.80,
                    "creative_quality_score": 0.78,
                    "compliance_pass_rate": 0.95,
                    "ad_set_packages": [
                        {"name": "TOFU - Awareness"},
                        {"name": "MOFU - Consideration"},
                        {"name": "BOFU - Conversion"},
                    ],
                },
                "ad_units": [
                    {"headline": "Variant A", "body": "..."},
                    {"headline": "Variant B", "body": "..."},
                    {"headline": "Variant C", "body": "..."},
                    {"headline": "Variant D", "body": "..."},
                ],
                "confidence_score": 0.85,
                "execution_time_ms": 5200,
            },
        },
    }


class TestCreativeGenerationExtractor:
    """Test CGA metric extraction."""

    def setup_method(self):
        self.extractor = CreativeGenerationExtractor()

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_all_metrics(self, MockSnapshot):
        """Full result_data with all fields populated yields 8 metrics."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_cga_result())
        metrics = self.extractor.extract(job)

        metric_names = [m.metric_name for m in metrics]
        assert "images_generated_count" in metric_names
        assert "image_generation_cost_usd" in metric_names
        assert "creative_quality_score" in metric_names
        assert "compliance_pass_rate" in metric_names
        assert "creative_packages_produced" in metric_names
        assert "copy_variants_generated" in metric_names
        assert "creative_confidence" in metric_names
        assert "creative_generation_execution_time" in metric_names
        assert len(metrics) == 8

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_empty_result(self, MockSnapshot):
        """Empty result_data returns no metrics."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job({"node_results": {"creative_generation": {}}})
        metrics = self.extractor.extract(job)
        assert metrics == []

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_no_creative_generation_key(self, MockSnapshot):
        """Missing node_results returns no metrics."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job({})
        metrics = self.extractor.extract(job)
        assert metrics == []

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extract_partial_data(self, MockSnapshot):
        """Only some fields present yields only those metrics."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(
            {
                "node_results": {
                    "creative_generation": {
                        "creative_package": {
                            "total_images_generated": 6,
                        },
                        "confidence_score": 0.90,
                    },
                },
            }
        )
        metrics = self.extractor.extract(job)
        metric_names = [m.metric_name for m in metrics]
        assert "images_generated_count" in metric_names
        assert "creative_confidence" in metric_names
        # Should not include metrics for missing fields
        assert "image_generation_cost_usd" not in metric_names
        assert "compliance_pass_rate" not in metric_names
        assert "copy_variants_generated" not in metric_names
        assert len(metrics) == 2

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_confidence_normalized(self, MockSnapshot):
        """confidence_score=0.85 should be normalized to 85.0."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_cga_result())
        metrics = self.extractor.extract(job)

        conf = next(m for m in metrics if m.metric_name == "creative_confidence")
        assert conf.metric_value == 85.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_compliance_rate_normalized(self, MockSnapshot):
        """compliance_pass_rate=0.95 should be normalized to 95.0."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_cga_result())
        metrics = self.extractor.extract(job)

        compliance = next(m for m in metrics if m.metric_name == "compliance_pass_rate")
        assert compliance.metric_value == 95.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_creative_quality_normalized(self, MockSnapshot):
        """creative_quality_score=0.78 should be normalized to 78.0."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_cga_result())
        metrics = self.extractor.extract(job)

        quality = next(m for m in metrics if m.metric_name == "creative_quality_score")
        assert quality.metric_value == 78.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_fallback_to_direct_result_data(self, MockSnapshot):
        """When node_results is empty but top-level has creative_package."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(
            {
                "node_results": {},
                "creative_package": {
                    "total_images_generated": 8,
                    "image_gen_cost_usd": 3.20,
                    "creative_quality_score": 0.82,
                    "compliance_pass_rate": 0.91,
                    "ad_set_packages": [
                        {"name": "Package A"},
                        {"name": "Package B"},
                    ],
                },
                "ad_units": [
                    {"headline": "V1"},
                    {"headline": "V2"},
                ],
                "confidence_score": 0.88,
                "execution_time_ms": 4100,
            }
        )
        metrics = self.extractor.extract(job)
        metric_names = [m.metric_name for m in metrics]

        assert "images_generated_count" in metric_names
        assert "image_generation_cost_usd" in metric_names
        assert "creative_quality_score" in metric_names
        assert "compliance_pass_rate" in metric_names
        assert "creative_packages_produced" in metric_names
        assert "copy_variants_generated" in metric_names
        assert "creative_confidence" in metric_names
        assert "creative_generation_execution_time" in metric_names
        assert len(metrics) == 8

        images = next(m for m in metrics if m.metric_name == "images_generated_count")
        assert images.metric_value == 8.0

        conf = next(m for m in metrics if m.metric_name == "creative_confidence")
        assert conf.metric_value == 88.0
