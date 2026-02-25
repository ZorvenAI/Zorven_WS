"""Tests for TitleGenerator."""

from unittest.mock import MagicMock, patch

from app.logic.title_generator import TitleGenerator


class TestTitleGenerator:
    """Tests for the TitleGenerator class."""

    async def test_stub_mode_returns_truncated_words(self):
        """No API key → first 5 words of the message."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")
        title = await generator.generate(
            "Analyze NVIDIA brand positioning in the GPU market"
        )
        assert title == "Analyze NVIDIA brand positioning in"

    async def test_stub_mode_short_message(self):
        """Short message returns all words."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")
        title = await generator.generate("Hello world")
        assert title == "Hello world"

    async def test_generates_title_with_gemini(self):
        """Mocked Gemini returns clean title."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")

        # Inject a mock model directly
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "NVIDIA Brand Positioning Analysis"
        mock_model.generate_content.return_value = mock_response
        generator._model = mock_model

        title = await generator.generate("Analyze NVIDIA brand positioning")
        assert title == "NVIDIA Brand Positioning Analysis"
        mock_model.generate_content.assert_called_once()

    async def test_strips_quotes_from_title(self):
        """Removes surrounding quotes from Gemini output."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '"NVIDIA Brand Analysis"'
        mock_model.generate_content.return_value = mock_response
        generator._model = mock_model

        title = await generator.generate("Analyze NVIDIA brand")
        assert title == "NVIDIA Brand Analysis"

    async def test_strips_trailing_punctuation(self):
        """Removes trailing punctuation from Gemini output."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "NVIDIA Brand Analysis."
        mock_model.generate_content.return_value = mock_response
        generator._model = mock_model

        title = await generator.generate("Analyze NVIDIA brand")
        assert title == "NVIDIA Brand Analysis"

    async def test_error_fallback(self):
        """Gemini error → word truncation fallback."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API error")
        generator._model = mock_model

        title = await generator.generate(
            "Analyze NVIDIA brand positioning in the GPU market"
        )
        assert title == "Analyze NVIDIA brand positioning in"

    async def test_fallback_title_truncates_to_255(self):
        """Fallback title is truncated to 255 characters."""
        long_message = "word " * 200
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")
        title = await generator.generate(long_message)
        assert len(title) <= 255

    async def test_empty_gemini_response_falls_back(self):
        """Empty Gemini response triggers fallback."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "   "
        mock_model.generate_content.return_value = mock_response
        generator._model = mock_model

        title = await generator.generate("Analyze NVIDIA brand positioning")
        assert title == "Analyze NVIDIA brand positioning"

    def test_clean_title_removes_backtick_quotes(self):
        """Clean title handles backtick quotes."""
        assert TitleGenerator._clean_title("`Test Title`") == "Test Title"

    def test_clean_title_collapses_whitespace(self):
        """Clean title collapses internal whitespace."""
        assert (
            TitleGenerator._clean_title("  Too   Many  Spaces  ") == "Too Many Spaces"
        )

    async def test_generate_with_first_response(self):
        """First response context is included in prompt."""
        generator = TitleGenerator(api_key="", model_name="gemini-2.0-flash")

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "NVIDIA Market Analysis"
        mock_model.generate_content.return_value = mock_response
        generator._model = mock_model

        title = await generator.generate(
            "Analyze NVIDIA", first_response="Here is the analysis..."
        )
        assert title == "NVIDIA Market Analysis"

        # Verify the prompt includes the response context
        call_args = mock_model.generate_content.call_args
        prompt = call_args[0][0]
        assert "Assistant response context:" in prompt

    def test_sanitize_input_strips_control_chars(self):
        """Control characters are removed from input."""
        result = TitleGenerator._sanitize_input("Hello\x00World\x1f!")
        assert result == "HelloWorld!"
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_sanitize_input_collapses_whitespace(self):
        """Excessive whitespace is collapsed."""
        result = TitleGenerator._sanitize_input("  Too   many   spaces  ")
        assert result == "Too many spaces"
