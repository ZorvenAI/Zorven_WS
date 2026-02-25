"""Tests for SEOOptimizer — keyword extraction, meta tags, and slug generation."""

from unittest.mock import AsyncMock, MagicMock

from app.logic.seo_optimizer import SEOOptimizer


def _brand_persona() -> dict:
    return {
        "name": "Tesla",
        "industry": "Electric Vehicles",
        "brand_voice": "innovative",
        "target_audience": "professionals",
    }


class TestStubMode:
    """Stub mode (no Gemini) tests."""

    async def test_stub_mode_extracts_keywords(self) -> None:
        optimizer = SEOOptimizer(gemini_model=None)
        result = await optimizer.optimize(
            "Tesla sustainability strategy 2024",
            "Some research context about Tesla.",
            _brand_persona(),
        )
        assert isinstance(result["keywords"], list)
        assert len(result["keywords"]) > 0

    async def test_meta_title_under_60_chars(self) -> None:
        optimizer = SEOOptimizer(gemini_model=None)
        result = await optimizer.optimize(
            "A very long topic about Tesla sustainability and environmental impact strategy",
            "",
            _brand_persona(),
        )
        assert len(result["meta_title"]) <= 60

    async def test_meta_description_under_160_chars(self) -> None:
        optimizer = SEOOptimizer(gemini_model=None)
        result = await optimizer.optimize(
            "Tesla sustainability",
            "",
            _brand_persona(),
        )
        assert len(result["meta_description"]) <= 160

    async def test_generates_slug_from_topic(self) -> None:
        optimizer = SEOOptimizer(gemini_model=None)
        result = await optimizer.optimize(
            "Tesla's 2024 Sustainability Strategy",
            "",
            _brand_persona(),
        )
        slug = result["slug"]
        assert " " not in slug
        assert slug.islower() or "-" in slug

    async def test_returns_headers(self) -> None:
        optimizer = SEOOptimizer(gemini_model=None)
        result = await optimizer.optimize("Topic", "", _brand_persona())
        assert isinstance(result["headers"], list)
        assert len(result["headers"]) > 0


class TestAIMode:
    """AI mode (mocked Gemini) tests."""

    async def test_ai_mode_calls_gemini(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(
                text='{"keywords": ["tesla", "sustainability"], '
                '"meta_title": "Tesla Sustainability", '
                '"meta_description": "Learn about Tesla sustainability.", '
                '"headers": ["Overview", "Impact"], '
                '"slug": "tesla-sustainability"}'
            )
        )
        optimizer = SEOOptimizer(gemini_model=mock_model)
        result = await optimizer.optimize(
            "Tesla sustainability", "context", _brand_persona()
        )
        assert result["keywords"] == ["tesla", "sustainability"]
        assert result["slug"] == "tesla-sustainability"
        mock_model.generate_content.assert_called_once()

    async def test_ai_mode_falls_back_on_error(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(side_effect=RuntimeError("API error"))
        optimizer = SEOOptimizer(gemini_model=mock_model)
        result = await optimizer.optimize("Topic", "", _brand_persona())
        # Falls back to stub mode
        assert isinstance(result["keywords"], list)
        assert result["slug"]
