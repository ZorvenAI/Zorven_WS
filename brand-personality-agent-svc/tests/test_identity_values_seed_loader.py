"""Tests for IdentityValuesSeedLoader logic module."""

import pytest

from app.logic.identity_values_seed_loader import (
    BRAND_VOICE_AAKER_MAP,
    IdentityValuesSeedLoader,
)


@pytest.fixture
def loader():
    return IdentityValuesSeedLoader()


class TestIdentityValuesSeedLoader:

    async def test_load_maps_professional_voice(self, loader):
        result = await loader.load(
            {"brand_voice": "professional"},
            {"recommended_positioning": {}},
        )
        assert result["brand_voice_mapped"] is True
        assert result["aaker_seed_weights"]["competence"] == 85
        assert result["aaker_seed_weights"]["sincerity"] == 60
        assert "Sage" in result["suggested_archetypes"]

    async def test_load_maps_bold_voice(self, loader):
        result = await loader.load(
            {"brand_voice": "bold"},
            {},
        )
        assert result["brand_voice_mapped"] is True
        assert result["aaker_seed_weights"]["excitement"] == 90
        assert result["aaker_seed_weights"]["ruggedness"] == 75
        assert "Hero" in result["suggested_archetypes"]

    async def test_load_unknown_voice(self, loader):
        result = await loader.load(
            {"brand_voice": "unknown_style"},
            {},
        )
        assert result["brand_voice_mapped"] is False
        assert result["aaker_seed_weights"] == {}
        assert result["suggested_archetypes"] == []

    async def test_load_empty_voice(self, loader):
        result = await loader.load({}, {})
        assert result["brand_voice"] == ""
        assert result["brand_voice_mapped"] is False

    async def test_load_includes_positioning(self, loader):
        result = await loader.load(
            {"brand_voice": "innovative"},
            {
                "recommended_positioning": {"statement": "test"},
                "differentiation": {"pods": [{"attribute": "speed"}]},
            },
        )
        assert result["positioning"]["statement"] == "test"
        assert result["differentiation"]["pods"][0]["attribute"] == "speed"

    async def test_load_includes_architecture_context(self, loader):
        result = await loader.load(
            {"brand_voice": "friendly"},
            {},
            baa_data={
                "recommendation": {"recommended_model": "branded_house"},
                "hierarchy": {"total_depth": 3},
            },
        )
        assert result["architecture"]["model"] == "branded_house"
        assert result["architecture"]["hierarchy_depth"] == 3

    async def test_all_eight_voice_mappings_exist(self):
        expected_voices = [
            "professional", "friendly", "authoritative", "casual",
            "luxury", "bold", "empathetic", "innovative",
        ]
        for voice in expected_voices:
            assert voice in BRAND_VOICE_AAKER_MAP, f"Missing voice mapping: {voice}"
            mapping = BRAND_VOICE_AAKER_MAP[voice]
            assert "sincerity" in mapping
            assert "excitement" in mapping
            assert "competence" in mapping
            assert "sophistication" in mapping
            assert "ruggedness" in mapping
            assert "archetypes" in mapping
