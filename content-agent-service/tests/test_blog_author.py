"""Tests for BlogAuthor — Markdown blog generation."""

from unittest.mock import MagicMock

from app.api.schemas import Citation
from app.logic.blog_author import BlogAuthor


def _brand_persona() -> dict:
    return {
        "name": "Tesla",
        "industry": "Electric Vehicles",
        "brand_voice": "innovative and data-driven",
        "target_audience": "professionals",
        "values": ["sustainability", "innovation"],
    }


def _seo_data() -> dict:
    return {
        "keywords": ["tesla", "sustainability", "ev"],
        "meta_title": "Tesla Sustainability",
        "meta_description": "Learn about Tesla sustainability.",
        "headers": ["Introduction", "Key Insights", "Conclusion"],
        "slug": "tesla-sustainability",
    }


def _citations() -> list[Citation]:
    return [
        Citation(
            claim="Tesla reduced emissions by 20%",
            source_title="Tesla Impact Report",
            source_url="https://example.com/tesla",
        ),
    ]


class TestStubMode:
    """Stub mode (no Gemini) tests."""

    async def test_stub_mode_returns_markdown(self) -> None:
        author = BlogAuthor(gemini_model=None)
        result = await author.author(
            "Tesla sustainability",
            "Research context here.",
            _brand_persona(),
            _seo_data(),
            _citations(),
        )
        assert isinstance(result, str)
        assert result.startswith("#")

    async def test_output_is_valid_markdown(self) -> None:
        author = BlogAuthor(gemini_model=None)
        result = await author.author(
            "Tesla sustainability",
            "",
            _brand_persona(),
            _seo_data(),
            [],
        )
        assert result.startswith("# ")
        assert "## " in result  # Has H2 sections

    async def test_includes_brand_name(self) -> None:
        author = BlogAuthor(gemini_model=None)
        result = await author.author(
            "Tesla sustainability",
            "",
            _brand_persona(),
            _seo_data(),
            [],
        )
        assert "Tesla" in result

    async def test_includes_citations_section(self) -> None:
        author = BlogAuthor(gemini_model=None)
        result = await author.author(
            "Tesla sustainability",
            "",
            _brand_persona(),
            _seo_data(),
            _citations(),
        )
        assert "Sources" in result or "Tesla Impact Report" in result


class TestAIMode:
    """AI mode (mocked Gemini) tests."""

    async def test_ai_mode_generates_markdown(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(
                text=(
                    "# Tesla Sustainability\n\n"
                    "## Introduction\n\n"
                    "Tesla leads in sustainability.\n\n"
                    "## Key Insights\n\n"
                    "- Reduced emissions by 20%\n\n"
                    "## Conclusion\n\n"
                    "Tesla continues to innovate."
                )
            )
        )
        author = BlogAuthor(gemini_model=mock_model)
        result = await author.author(
            "Tesla sustainability",
            "Research context.",
            _brand_persona(),
            _seo_data(),
            _citations(),
        )
        assert result.startswith("# ")
        assert "## Introduction" in result
        mock_model.generate_content.assert_called_once()

    async def test_includes_seo_keywords_in_prompt(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(text="# Blog\n\nContent.")
        )
        author = BlogAuthor(gemini_model=mock_model)
        await author.author(
            "Topic", "Context", _brand_persona(), _seo_data(), []
        )
        call_args = mock_model.generate_content.call_args
        prompt = call_args[0][0]
        assert "tesla" in prompt.lower()
        assert "sustainability" in prompt.lower()

    async def test_includes_citations_in_prompt(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(text="# Blog\n\nContent.")
        )
        author = BlogAuthor(gemini_model=mock_model)
        await author.author(
            "Topic", "Context", _brand_persona(), _seo_data(), _citations()
        )
        call_args = mock_model.generate_content.call_args
        prompt = call_args[0][0]
        assert "Tesla Impact Report" in prompt

    async def test_includes_brand_voice_in_prompt(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(text="# Blog\n\nContent.")
        )
        author = BlogAuthor(gemini_model=mock_model)
        await author.author(
            "Topic", "Context", _brand_persona(), _seo_data(), []
        )
        call_args = mock_model.generate_content.call_args
        prompt = call_args[0][0]
        assert "innovative and data-driven" in prompt

    async def test_ai_fallback_on_error(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            side_effect=RuntimeError("API error")
        )
        author = BlogAuthor(gemini_model=mock_model)
        result = await author.author(
            "Topic", "", _brand_persona(), _seo_data(), []
        )
        # Falls back to stub
        assert result.startswith("#")
