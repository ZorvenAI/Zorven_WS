"""Tests for CharacterBriefSynthesizer logic module."""

import pytest

from app.logic.character_brief_synthesizer import CharacterBriefSynthesizer


@pytest.fixture
def synthesizer():
    return CharacterBriefSynthesizer()


class TestCharacterBriefSynthesizer:

    async def test_validate_extracts_persona_card(self, synthesizer):
        brief = {
            "persona_card": {
                "name": "Dr. Volt",
                "age": "45",
                "personality": "Knowledgeable",
            },
            "executive_summary": "A competent brand",
            "positioning_alignment_score": 85.0,
        }
        result = await synthesizer.validate(brief)
        assert result["persona_card"]["name"] == "Dr. Volt"
        assert result["executive_summary"] == "A competent brand"
        assert result["positioning_alignment_score"] == 85.0

    async def test_validate_clamps_alignment_score(self, synthesizer):
        brief = {"positioning_alignment_score": 150.0}
        result = await synthesizer.validate(brief)
        assert result["positioning_alignment_score"] == 100.0

    async def test_validate_clamps_negative_score(self, synthesizer):
        brief = {"positioning_alignment_score": -10.0}
        result = await synthesizer.validate(brief)
        assert result["positioning_alignment_score"] == 0.0

    async def test_validate_empty(self, synthesizer):
        result = await synthesizer.validate({})
        assert result["persona_card"] == {}
        assert result["executive_summary"] == ""
        assert result["positioning_alignment_score"] == 0.0
