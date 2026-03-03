"""Unit tests for automation.utils.strip_markdown."""

import pytest

from automation.utils import strip_markdown


@pytest.mark.unit
class TestStripMarkdown:
    """Tests for strip_markdown()."""

    def test_empty_and_none(self):
        assert strip_markdown("") == ""
        assert strip_markdown(None) is None

    def test_plain_text_unchanged(self):
        assert strip_markdown("Hello world") == "Hello world"

    def test_headers(self):
        assert strip_markdown("# Title") == "Title"
        assert strip_markdown("## Subtitle") == "Subtitle"
        assert strip_markdown("###### Deep") == "Deep"

    def test_bold(self):
        assert strip_markdown("This is **bold** text") == "This is bold text"
        assert strip_markdown("This is __bold__ text") == "This is bold text"

    def test_italic(self):
        assert strip_markdown("This is *italic* text") == "This is italic text"

    def test_bold_italic(self):
        assert strip_markdown("***both***") == "both"

    def test_strikethrough(self):
        assert strip_markdown("~~removed~~") == "removed"

    def test_links(self):
        assert strip_markdown("[Click](https://example.com)") == "Click"

    def test_link_with_parentheses_in_url(self):
        """Handles Wikipedia-style URLs with parentheses."""
        md = "[Function](https://en.wikipedia.org/wiki/Function_(mathematics))"
        result = strip_markdown(md)
        assert result == "Function"

    def test_images(self):
        assert strip_markdown("![Alt text](image.png)") == "Alt text"

    def test_inline_code(self):
        assert strip_markdown("Use `code` here") == "Use code here"

    def test_inline_code_protected_from_emphasis(self):
        """Inline code like `__init__` should not be mangled by underscore stripping."""
        result = strip_markdown("Call `__init__` method")
        assert "__init__" in result

    def test_fenced_code_block(self):
        md = "Before\n```python\nprint('hi')\n```\nAfter"
        result = strip_markdown(md)
        assert "print" not in result
        assert "Before" in result
        assert "After" in result

    def test_blockquotes(self):
        assert strip_markdown("> Quoted text") == "Quoted text"

    def test_horizontal_rules(self):
        assert strip_markdown("Above\n---\nBelow").strip() == "Above\n\nBelow"
        assert strip_markdown("Above\n***\nBelow").strip() == "Above\n\nBelow"

    def test_unordered_list(self):
        md = "- Item one\n- Item two"
        result = strip_markdown(md)
        assert result == "Item one\nItem two"

    def test_ordered_list(self):
        md = "1. First\n2. Second"
        result = strip_markdown(md)
        assert result == "First\nSecond"

    def test_html_tags(self):
        assert strip_markdown("Hello <b>world</b>") == "Hello world"

    def test_multiple_blank_lines_collapsed(self):
        md = "A\n\n\n\n\nB"
        result = strip_markdown(md)
        assert result == "A\n\nB"

    def test_full_blog_post(self):
        """Representative blog content from the content agent."""
        blog = (
            "# Building Your Brand\n\n"
            "**Brand identity** is crucial for [success](https://example.com).\n\n"
            "## Key Points\n\n"
            "- Be authentic\n"
            "- Be consistent\n"
            "- Use *visual storytelling*\n\n"
            "> Great brands tell stories.\n\n"
            "---\n\n"
            "Follow us for more tips!"
        )
        result = strip_markdown(blog)
        assert "# " not in result
        assert "**" not in result
        assert "[success]" not in result
        assert "- " not in result
        assert "> " not in result
        assert "---" not in result
        assert "Building Your Brand" in result
        assert "Brand identity" in result
        assert "Be authentic" in result
        assert "visual storytelling" in result
        assert "Follow us for more tips!" in result
