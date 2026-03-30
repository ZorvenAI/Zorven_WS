"""Tests for BrandStoryExtractor."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from analytics.extractors.brand_story import BrandStoryExtractor


def _mock_job(result_data, tenant=None, manifest=None):
    """Build a mock AnalysisJob with result_data."""
    job = MagicMock()
    job.result_data = result_data
    job.tenant = tenant
    job.manifest = manifest
    job.input_context = {"pipeline_id": "brand-strategy-story"}
    job.completed_at = None
    job.updated_at = None
    return job


def _full_bsa_result():
    """Return a realistic BSA result nested under node_results."""
    return {
        "node_results": {
            "brand_story": {
                "origin_story": {
                    "archetype_used": "Hero",
                    "emotional_arc": "tension-transformation-resolution",
                    "versions": [
                        {
                            "version_label": "short",
                            "word_count": 480,
                            "content": "A short origin story...",
                            "archetype_arc_alignment": 0.85,
                            "emotional_resonance_score": 0.80,
                            "voice_consistency_score": 0.78,
                        },
                        {
                            "version_label": "medium",
                            "word_count": 810,
                            "content": "A medium origin story...",
                            "archetype_arc_alignment": 0.88,
                            "emotional_resonance_score": 0.84,
                            "voice_consistency_score": 0.82,
                        },
                        {
                            "version_label": "long",
                            "word_count": 1480,
                            "content": "A long origin story...",
                            "archetype_arc_alignment": 0.90,
                            "emotional_resonance_score": 0.86,
                            "voice_consistency_score": 0.85,
                        },
                    ],
                },
                "mission_vision": {
                    "mission_scores": {
                        "clarity": 0.88,
                        "positioning_alignment": 0.82,
                    },
                    "vision_scores": {
                        "inspiration": 0.85,
                    },
                },
                "pitches": {
                    "pitch_30s": {
                        "content": "30s pitch content",
                        "word_count": 75,
                        "memorability_score": 0.82,
                    },
                },
                "channel_narratives": {
                    "website_about": {"content": "About us page"},
                    "channel_consistency_score": 0.85,
                },
                "narrative_package": {
                    "overall_confidence": 0.81,
                    "positioning_narrative_alignment": 0.79,
                    "summary": "Brand narrative summary",
                },
                "confidence_score": 0.81,
                "execution_time_ms": 4200,
            },
        },
    }


class TestBrandStoryExtractor:
    """Test BSA metric extraction."""

    def setup_method(self):
        self.extractor = BrandStoryExtractor()

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_extracts_all_metrics(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        metric_names = [m.metric_name for m in metrics]
        # Uses medium version (index 1) for origin story scores
        assert "story_archetype_arc_alignment" in metric_names
        assert "story_emotional_resonance" in metric_names
        assert "story_voice_consistency" in metric_names
        assert "mission_clarity" in metric_names
        assert "mission_positioning_alignment" in metric_names
        assert "vision_inspiration" in metric_names
        assert "pitch_30s_memorability" in metric_names
        assert "channel_narrative_consistency" in metric_names
        assert "narrative_overall_confidence" in metric_names
        assert "narrative_positioning_alignment" in metric_names
        assert "story_confidence" in metric_names
        assert "story_execution_time" in metric_names

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_archetype_alignment_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        arc = next(
            m for m in metrics if m.metric_name == "story_archetype_arc_alignment"
        )
        # Medium version (index 1): 0.88 * 100 = 88.0
        assert arc.metric_value == 88.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_emotional_resonance_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        res = next(m for m in metrics if m.metric_name == "story_emotional_resonance")
        # Medium version (index 1): 0.84 * 100 = 84.0
        assert res.metric_value == 84.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_mission_clarity_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        clarity = next(m for m in metrics if m.metric_name == "mission_clarity")
        # 0.88 * 100 = 88.0
        assert clarity.metric_value == 88.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_pitch_memorability_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        mem = next(m for m in metrics if m.metric_name == "pitch_30s_memorability")
        # 0.82 * 100 = 82.0
        assert mem.metric_value == 82.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_channel_consistency_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        cc = next(
            m for m in metrics if m.metric_name == "channel_narrative_consistency"
        )
        # 0.85 * 100 = 85.0
        assert cc.metric_value == 85.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_confidence_normalized(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        conf = next(m for m in metrics if m.metric_name == "story_confidence")
        # 0.81 * 100 = 81.0
        assert conf.metric_value == 81.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_execution_time_in_ms(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        et = next(m for m in metrics if m.metric_name == "story_execution_time")
        assert et.metric_value == 4200.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_empty_result_returns_empty(self, MockSnapshot):
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job({"node_results": {"brand_story": {}}})
        metrics = self.extractor.extract(job)
        assert metrics == []

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_fallback_to_direct_result(self, MockSnapshot):
        """When data is not under node_results, fall back to result_data."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(
            {
                "origin_story": {
                    "versions": [
                        {
                            "version_label": "short",
                            "archetype_arc_alignment": 0.75,
                            "emotional_resonance_score": 0.70,
                            "voice_consistency_score": 0.68,
                        },
                    ],
                },
                "confidence_score": 0.72,
                "execution_time_ms": 3000,
            }
        )
        metrics = self.extractor.extract(job)
        names = [m.metric_name for m in metrics]
        assert "story_archetype_arc_alignment" in names
        assert "story_confidence" in names
        assert "story_execution_time" in names

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_uses_medium_version_when_available(self, MockSnapshot):
        """Extractor should prefer medium version (index 1)."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        job = _mock_job(_full_bsa_result())
        metrics = self.extractor.extract(job)

        arc = next(
            m for m in metrics if m.metric_name == "story_archetype_arc_alignment"
        )
        # Medium version has 0.88, short has 0.85
        assert arc.metric_value == 88.0

    @patch("analytics.extractors.base.MetricSnapshot")
    def test_uses_first_version_when_only_one(self, MockSnapshot):
        """When only one version exists, use it."""
        MockSnapshot.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)
        result = _full_bsa_result()
        # Keep only the first version
        result["node_results"]["brand_story"]["origin_story"]["versions"] = [
            result["node_results"]["brand_story"]["origin_story"]["versions"][0]
        ]
        job = _mock_job(result)
        metrics = self.extractor.extract(job)

        arc = next(
            m for m in metrics if m.metric_name == "story_archetype_arc_alignment"
        )
        # Short version: 0.85 * 100 = 85.0
        assert arc.metric_value == 85.0
