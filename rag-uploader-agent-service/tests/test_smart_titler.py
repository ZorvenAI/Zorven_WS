"""Tests for SmartTitler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.logic.smart_titler import SmartTitler


class TestGenericDetection:
    """Tests for generic filename pattern matching."""

    def _make_titler(self) -> SmartTitler:
        return SmartTitler(gemini_model=None)

    async def test_generic_upload(self):
        t = self._make_titler()
        assert SmartTitler._is_generic("upload.pdf")
        assert SmartTitler._is_generic("upload1.pdf")
        assert SmartTitler._is_generic("Upload.PDF")

    async def test_generic_document(self):
        assert SmartTitler._is_generic("document.pdf")
        assert SmartTitler._is_generic("document1.docx")

    async def test_generic_file(self):
        assert SmartTitler._is_generic("file.pdf")
        assert SmartTitler._is_generic("file123.txt")

    async def test_generic_img(self):
        assert SmartTitler._is_generic("IMG_20240101.jpg")
        assert SmartTitler._is_generic("IMG_1234.png")

    async def test_generic_screenshot(self):
        assert SmartTitler._is_generic("Screenshot_2024.png")
        assert SmartTitler._is_generic("Screenshot 123.jpg")

    async def test_generic_hex_hash(self):
        assert SmartTitler._is_generic("a1b2c3d4e5f6.pdf")

    async def test_non_generic_kept(self):
        assert not SmartTitler._is_generic("Q4_Financial_Report.pdf")
        assert not SmartTitler._is_generic("Tesla_Strategy_2024.pdf")
        assert not SmartTitler._is_generic("meeting_notes_jan.docx")


class TestStubMode:
    """Tests when Gemini is not available."""

    async def test_non_generic_returns_slugified(self):
        t = SmartTitler(gemini_model=None)
        result = await t.title("Q4 Financial Report.pdf")
        assert result == "Q4_Financial_Report.pdf"

    async def test_generic_returns_slugified_original(self):
        t = SmartTitler(gemini_model=None)
        # Without Gemini, falls back to original
        result = await t.title("upload.pdf")
        assert result == "upload.pdf"

    async def test_empty_filename(self):
        t = SmartTitler(gemini_model=None)
        result = await t.title("")
        assert result == "unnamed_document"


class TestAIMode:
    """Tests when Gemini is available (mocked)."""

    async def test_gemini_renames_generic(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Tesla Q4 Sustainability Report"
        mock_model.generate_content = MagicMock(return_value=mock_response)

        t = SmartTitler(gemini_model=mock_model)
        result = await t.title("upload.pdf")

        assert result == "Tesla_Q4_Sustainability_Report.pdf"
        mock_model.generate_content.assert_called_once()

    async def test_prompt_is_sanitized_before_gemini_call(self):
        """Verify sanitize_ai_prompt is applied to the LLM prompt."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Quarterly Report"
        mock_model.generate_content = MagicMock(return_value=mock_response)

        t = SmartTitler(gemini_model=mock_model)

        with patch("app.logic.smart_titler.sanitize_ai_prompt") as mock_sanitize:
            mock_sanitize.side_effect = lambda x: x  # pass-through
            await t.title("upload.pdf")
            mock_sanitize.assert_called_once()

    async def test_gemini_failure_falls_back(self):
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(side_effect=RuntimeError("API error"))

        t = SmartTitler(gemini_model=mock_model)
        result = await t.title("upload.pdf")
        # Falls back to original
        assert result == "upload.pdf"


class TestSlugify:
    """Tests for GCS-compatible slugification."""

    def test_spaces_to_underscores(self):
        assert SmartTitler._slugify("My Report", ".pdf") == "My_Report.pdf"

    def test_special_chars_removed(self):
        assert SmartTitler._slugify("Report (v2)!", ".pdf") == "Report_v2.pdf"

    def test_consecutive_underscores_collapsed(self):
        assert SmartTitler._slugify("a___b", ".pdf") == "a_b.pdf"

    def test_max_length_enforced(self):
        long_name = "a" * 300
        result = SmartTitler._slugify(long_name, ".pdf")
        assert len(result) <= 200
        assert result.endswith(".pdf")
