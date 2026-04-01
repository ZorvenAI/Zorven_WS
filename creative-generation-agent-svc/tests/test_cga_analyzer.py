"""Tests for CGAAnalyzer — context unwrapping, learnings, output shape."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.logic.creative_context_loader import CreativeContextLoader
from app.logic.creative_learnings_loader import CreativeLearningsLoader
from app.logic.guardrails import InputGuardrails


class TestCAContextUnwrapping:
    """Verify CAA context is unwrapped correctly for both shapes."""

    def test_creative_briefs_from_blueprint_ad_sets(self):
        """ad_sets nested under blueprint should be extracted."""
        loader = CreativeContextLoader()
        caa = {
            "blueprint": {
                "ad_sets": [
                    {
                        "name": "fleet-tofu",
                        "funnel_stage": "tofu",
                        "persona": "Fleet Manager",
                        "variant_count": 3,
                    },
                ],
            },
        }
        ctx = loader.build_context(
            caa_context=caa,
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            nta_context=None,
            bsa_context=None,
            company_context=None,
        )
        assert len(ctx["creative_briefs"]) == 1
        assert ctx["creative_briefs"][0]["ad_set_name"] == "fleet-tofu"

    def test_creative_briefs_from_top_level_ad_sets(self):
        """Top-level ad_sets (no blueprint wrapper) should also work."""
        loader = CreativeContextLoader()
        caa = {
            "ad_sets": [
                {"name": "retail-bofu", "funnel_stage": "bofu"},
            ],
        }
        ctx = loader.build_context(
            caa_context=caa,
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            nta_context=None,
            bsa_context=None,
            company_context=None,
        )
        assert len(ctx["creative_briefs"]) == 1

    def test_creative_briefs_prefer_explicit_creative_briefs(self):
        """Explicit creative_briefs key should take precedence."""
        loader = CreativeContextLoader()
        caa = {
            "creative_briefs": [
                {"name": "explicit-brief", "funnel_stage": "mofu"},
            ],
            "blueprint": {
                "ad_sets": [{"name": "should-be-ignored"}],
            },
        }
        ctx = loader.build_context(
            caa_context=caa,
            wf1_context=None,
            bpa_context=None,
            bpv_context=None,
            nta_context=None,
            bsa_context=None,
            company_context=None,
        )
        assert len(ctx["creative_briefs"]) == 1
        assert ctx["creative_briefs"][0]["ad_set_name"] == "explicit-brief"

    def test_archetype_dict_normalized_to_string(self):
        """BPV archetype dict should be normalized to string."""
        loader = CreativeContextLoader()
        bpv = {
            "archetype": {
                "primary": {"name": "Hero", "score": 0.85},
                "secondary": {"name": "Explorer"},
            },
        }
        ctx = loader.build_context(
            caa_context=None,
            wf1_context=None,
            bpa_context=None,
            bpv_context=bpv,
            nta_context=None,
            bsa_context=None,
            company_context=None,
        )
        # archetype should be a string, not a dict
        assert isinstance(ctx["brand_visual"]["archetype"], str)
        assert ctx["brand_visual"]["archetype"] == "Hero"


class TestLearningsIntegration:
    """Verify learnings loader API is used correctly."""

    def test_load_returns_available_flag(self):
        """Learnings loader uses 'available' not 'has_learnings'."""
        loader = CreativeLearningsLoader()
        result = loader.load(None)
        assert "available" in result
        assert result["available"] is False

    def test_load_with_empty_outputs(self):
        """Empty outputs should return empty learnings."""
        loader = CreativeLearningsLoader()
        result = loader.load({})
        assert result["available"] is False
        assert result["image_style_winners"] == []


class TestInputGuardrailsBlueprint:
    """Verify IG-08 unwraps blueprint correctly."""

    def test_ig08_detects_ad_sets_under_blueprint(self):
        """ad_sets under blueprint key should pass IG-08."""
        guard = InputGuardrails()
        caa = {
            "blueprint": {
                "ad_sets": [{"name": "test"}],
            },
        }
        issues = guard.check(caa, {"name": "TestCo"})
        assert not any("IG-08" in i for i in issues)

    def test_ig08_flags_empty_blueprint(self):
        """Empty blueprint with no ad_sets should flag IG-08."""
        guard = InputGuardrails()
        caa = {"blueprint": {"ad_sets": []}}
        issues = guard.check(caa, {"name": "TestCo"})
        assert any("IG-08" in i for i in issues)

    def test_ig08_accepts_top_level_ad_sets(self):
        """Top-level ad_sets (no blueprint wrapper) should pass."""
        guard = InputGuardrails()
        caa = {"ad_sets": [{"name": "test"}]}
        issues = guard.check(caa, {"name": "TestCo"})
        assert not any("IG-08" in i for i in issues)


class TestOutputShapeValidation:
    """Verify output matches the public CGAResponse schema keys."""

    def test_stub_response_has_required_keys(self):
        """Stub response from routes should contain all schema keys."""
        from app.api.routes import _stub_response

        result = _stub_response("test prompt")
        required_keys = {
            "query",
            "creative_package",
            "ad_set_packages",
            "ad_units",
            "generated_images",
            "hooks",
            "copy_variants",
            "ctas",
            "compliance_results",
            "creative_profiles",
            "total_images_generated",
            "image_gen_cost_usd",
            "compliance_pass_rate",
            "creative_quality_score",
            "confidence_score",
            "findings",
            "recommendations",
            "execution_time_ms",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_stub_response_types(self):
        """Verify stub response value types."""
        from app.api.routes import _stub_response

        result = _stub_response("test")
        assert isinstance(result["creative_package"], dict)
        assert isinstance(result["ad_units"], list)
        assert isinstance(result["confidence_score"], (int, float))
        assert isinstance(result["findings"], list)
