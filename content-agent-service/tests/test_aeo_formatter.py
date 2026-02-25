"""Tests for AEOFormatter — FAQ generation and JSON-LD structured data."""

from unittest.mock import MagicMock

from app.logic.aeo_formatter import AEOFormatter


class TestStubMode:
    """Stub mode (no Gemini) tests."""

    async def test_stub_mode_generates_template_faq(self) -> None:
        formatter = AEOFormatter(gemini_model=None)
        result = await formatter.format(
            "Tesla sustainability",
            "# Blog content\n\nSome content here.",
            ["tesla", "sustainability"],
        )
        assert isinstance(result["faq_items"], list)
        assert len(result["faq_items"]) > 0
        for item in result["faq_items"]:
            assert "question" in item
            assert "answer" in item

    async def test_structured_data_is_valid_jsonld(self) -> None:
        formatter = AEOFormatter(gemini_model=None)
        result = await formatter.format("Topic", "Content", ["keyword"])
        sd = result["structured_data"]
        assert sd["@context"] == "https://schema.org"
        assert sd["@type"] == "FAQPage"
        assert isinstance(sd["mainEntity"], list)
        for entity in sd["mainEntity"]:
            assert entity["@type"] == "Question"
            assert "name" in entity
            assert entity["acceptedAnswer"]["@type"] == "Answer"

    async def test_max_5_faq_items(self) -> None:
        formatter = AEOFormatter(gemini_model=None)
        result = await formatter.format(
            "Topic", "Content", ["a", "b", "c", "d", "e", "f"]
        )
        assert len(result["faq_items"]) <= 5


class TestAIMode:
    """AI mode (mocked Gemini) tests."""

    async def test_generates_faq_items(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            return_value=MagicMock(
                text='{"faq_items": ['
                '{"question": "What is Tesla?", "answer": "An EV company."},'
                '{"question": "Why sustainability?", "answer": "For the planet."}'
                "]}"
            )
        )
        formatter = AEOFormatter(gemini_model=mock_model)
        result = await formatter.format("Tesla", "Content", ["tesla"])
        assert len(result["faq_items"]) == 2
        assert result["faq_items"][0]["question"] == "What is Tesla?"

    async def test_ai_fallback_on_error(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            side_effect=RuntimeError("API error")
        )
        formatter = AEOFormatter(gemini_model=mock_model)
        result = await formatter.format("Topic", "Content", ["kw"])
        assert isinstance(result["faq_items"], list)
        assert len(result["faq_items"]) > 0
