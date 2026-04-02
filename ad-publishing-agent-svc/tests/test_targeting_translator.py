"""Tests for the targeting translator."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.targeting_translator import TargetingTranslator


class TestTargetingTranslatorFallback:
    """Test rule-based fallback when LLM is unavailable."""

    def setup_method(self):
        self.translator = TargetingTranslator(llm_client=None)

    async def test_basic_persona_translation(self):
        persona = {
            "name": "Tech Enthusiast",
            "demographics": {
                "age_min": 25,
                "age_max": 45,
                "genders": ["male", "female"],
                "countries": ["US"],
            },
            "interests": ["technology", "software"],
        }
        result = await self.translator.translate(persona)

        spec = result["targeting_spec"]
        assert spec["geo_locations"]["countries"] == ["US"]
        assert spec["age_min"] == 25
        assert spec["age_max"] == 45
        assert len(spec["interests"]) == 2
        assert result["persona_name"] == "Tech Enthusiast"

    async def test_special_ad_category_removes_demographics(self):
        persona = {
            "name": "Homebuyer",
            "demographics": {
                "age_min": 25,
                "age_max": 55,
                "genders": ["female"],
                "countries": ["US"],
            },
            "interests": ["real estate"],
        }
        result = await self.translator.translate(
            persona,
            special_ad_categories=["HOUSING"],
        )

        spec = result["targeting_spec"]
        assert "age_min" not in spec
        assert "age_max" not in spec
        assert "genders" not in spec
        assert spec["geo_locations"]["countries"] == ["US"]

    async def test_placement_mapping(self):
        persona = {
            "name": "Test",
            "demographics": {"countries": ["US"]},
            "interests": [],
        }
        result = await self.translator.translate(
            persona,
            placements=["FACEBOOK_FEED", "INSTAGRAM_STORIES"],
        )

        spec = result["targeting_spec"]
        assert "facebook" in spec.get("publisher_platforms", [])
        assert "instagram" in spec.get("publisher_platforms", [])

    async def test_translate_all(self):
        personas = [
            {"name": "A", "demographics": {"countries": ["US"]}, "interests": []},
            {"name": "B", "demographics": {"countries": ["UK"]}, "interests": []},
        ]
        results = await self.translator.translate_all(personas)
        assert len(results) == 2
        assert results[0]["persona_name"] == "A"
        assert results[1]["persona_name"] == "B"

    async def test_empty_geo_warning(self):
        persona = {
            "name": "No Geo",
            "demographics": {},
            "interests": [],
        }
        result = await self.translator.translate(persona)
        warnings = result["warnings"]
        assert any("interest" in w.lower() for w in warnings)


class TestTargetingTranslatorWithLLM:
    """Test LLM-powered translation."""

    async def test_llm_translation(self, mock_anthropic):
        from app.services.anthropic_client import AnthropicClient

        llm = AnthropicClient(mock_anthropic)
        translator = TargetingTranslator(llm_client=llm)

        persona = {
            "name": "Tech Pro",
            "demographics": {"age_min": 25, "age_max": 54, "countries": ["US"]},
            "interests": ["technology"],
        }
        result = await translator.translate(persona, industry="Technology")

        spec = result["targeting_spec"]
        assert spec["geo_locations"]["countries"] == ["US"]
        assert spec["age_min"] == 25
        assert "interests" in spec

    async def test_llm_failure_falls_back(self):
        """If LLM call fails, fallback to rule-based translation."""
        broken_llm = AsyncMock()
        broken_llm.generate_json = AsyncMock(side_effect=Exception("LLM down"))

        translator = TargetingTranslator(llm_client=broken_llm)

        persona = {
            "name": "Fallback Test",
            "demographics": {"countries": ["US"]},
            "interests": ["hiking"],
        }
        result = await translator.translate(persona)

        # Should succeed with fallback
        assert result["targeting_spec"]["geo_locations"]["countries"] == ["US"]
        assert len(result["targeting_spec"]["interests"]) == 1
