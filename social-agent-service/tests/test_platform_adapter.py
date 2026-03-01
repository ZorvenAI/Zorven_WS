"""Tests for platform content adaptation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.logic.platform_adapter import (
    FACEBOOK_MAX_CHARS,
    INSTAGRAM_MAX_CHARS,
    LINKEDIN_MAX_CHARS,
    TWITTER_MAX_CHARS,
    PlatformAdapter,
    _clean_ai_output,
)


class TestStubMode:
    """Tests when Gemini is not available (stub/template mode)."""

    def _make_adapter(self) -> PlatformAdapter:
        return PlatformAdapter(gemini_model=None)

    async def test_stub_linkedin_adaptation(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {
            "title": "Tesla Sustainability",
            "keywords": ["Tesla", "sustainability", "EV"],
        }
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["linkedin"]
        )
        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "linkedin"
        assert post.post_type == "article_share"
        assert len(post.content) > 0
        assert post.char_count == len(post.content)

    async def test_stub_twitter_adaptation(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {"title": "Tesla", "keywords": ["Tesla"]}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["twitter"]
        )
        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "twitter"
        assert post.char_count <= TWITTER_MAX_CHARS

    async def test_stub_facebook_adaptation(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {"title": "Tesla", "keywords": []}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["facebook"]
        )
        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "facebook"
        assert post.post_type == "status"

    async def test_includes_hashtags(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {"title": "Tesla", "keywords": ["Tesla", "EV"]}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["linkedin"]
        )
        assert len(posts[0].hashtags) > 0
        assert posts[0].hashtags[0].startswith("#")

    async def test_stub_instagram_adaptation(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {
            "title": "Tesla Sustainability",
            "keywords": ["Tesla", "sustainability", "EV", "green", "energy"],
        }
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["instagram"]
        )
        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "instagram"
        assert post.post_type == "caption"
        assert len(post.content) > 0
        assert post.char_count == len(post.content)
        assert len(post.hashtags) <= 15

    async def test_multiple_platforms(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {"title": "Tesla", "keywords": ["Tesla"]}
        posts = await adapter.adapt(
            sample_blog_content,
            seo_meta,
            sample_brand_persona,
            ["linkedin", "twitter", "facebook", "instagram"],
        )
        assert len(posts) == 4
        platforms = {p.platform for p in posts}
        assert platforms == {"linkedin", "twitter", "facebook", "instagram"}


class TestAIMode:
    """Tests when Gemini is available (mocked)."""

    def _make_adapter(self) -> PlatformAdapter:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            "Check out our latest insights on Tesla's sustainability! "
            "From EVs to solar energy, they're changing the game.\n\n"
            "#Tesla #Sustainability #EV"
        )
        mock_model.generate_content = MagicMock(return_value=mock_response)
        return PlatformAdapter(gemini_model=mock_model)

    async def test_ai_linkedin_generates_post(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {"title": "Tesla", "keywords": ["Tesla", "sustainability"]}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["linkedin"]
        )
        assert len(posts) == 1
        assert posts[0].platform == "linkedin"
        assert len(posts[0].content) > 0

    async def test_ai_twitter_generates_thread(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        adapter = self._make_adapter()
        seo_meta = {"title": "Tesla", "keywords": ["Tesla"]}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["twitter"]
        )
        assert len(posts) == 1
        assert posts[0].platform == "twitter"

    async def test_ai_instagram_generates_caption(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            "Driving the future, one charge at a time.\n\n"
            "Tesla is redefining what sustainability looks like.\n\n"
            "#Tesla #Sustainability #EV #GreenEnergy"
        )
        mock_model.generate_content = MagicMock(return_value=mock_response)
        adapter = PlatformAdapter(gemini_model=mock_model)

        seo_meta = {"title": "Tesla", "keywords": ["Tesla", "sustainability"]}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["instagram"]
        )
        assert len(posts) == 1
        assert posts[0].platform == "instagram"
        assert posts[0].post_type == "caption"
        assert len(posts[0].content) > 0

        # Verify Instagram-specific prompt was used
        call_args = mock_model.generate_content.call_args
        prompt = call_args[0][0]
        assert "Instagram caption" in prompt
        assert "hashtags" in prompt.lower()

    async def test_includes_brand_voice_in_prompt(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Test post content"
        mock_model.generate_content = MagicMock(return_value=mock_response)
        adapter = PlatformAdapter(gemini_model=mock_model)

        seo_meta = {"title": "Tesla", "keywords": []}
        await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["linkedin"]
        )

        call_args = mock_model.generate_content.call_args
        prompt = call_args[0][0]
        assert "professional" in prompt  # brand_voice
        assert "TestBrand" in prompt  # brand_name

    async def test_ai_fallback_on_error(
        self,
        sample_blog_content: str,
        sample_brand_persona: dict[str, Any],
    ):
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            side_effect=RuntimeError("API error")
        )
        adapter = PlatformAdapter(gemini_model=mock_model)

        seo_meta = {"title": "Tesla", "keywords": ["Tesla"]}
        posts = await adapter.adapt(
            sample_blog_content, seo_meta, sample_brand_persona, ["linkedin"]
        )
        # Should fall back to stub mode
        assert len(posts) == 1
        assert posts[0].platform == "linkedin"
        assert len(posts[0].content) > 0


class TestCleanAIOutput:
    """Tests for _clean_ai_output post-processing."""

    def test_clean_text_unchanged(self):
        text = "Great insights on sustainability! #Tesla #EV"
        assert _clean_ai_output(text) == text

    def test_strips_preamble_here_is(self):
        text = "Here is a LinkedIn post:\nGreat insights on sustainability!"
        assert _clean_ai_output(text) == "Great insights on sustainability!"

    def test_strips_preamble_sure(self):
        text = "Sure! Here's the post:\nGreat insights on sustainability!"
        assert _clean_ai_output(text) == "Great insights on sustainability!"

    def test_strips_preamble_certainly(self):
        text = "Certainly! Below is the caption:\nGreat insights!"
        assert _clean_ai_output(text) == "Great insights!"

    def test_preserves_legitimate_first_line(self):
        """Legitimate content starting with 'this is a' should NOT be stripped."""
        text = "This is a game changer for the industry!\nMore details inside."
        assert _clean_ai_output(text) == text

    def test_strips_bare_post_label(self):
        text = "Post:\nGreat insights on sustainability!"
        assert _clean_ai_output(text) == "Great insights on sustainability!"

    def test_picks_first_option(self):
        text = (
            "Option 1: Great insights on Tesla!\n\n"
            "Option 2: Tesla is leading the charge!\n\n"
            "Option 3: The future is electric with Tesla!"
        )
        result = _clean_ai_output(text)
        assert "Option 1" not in result
        assert "Option 2" not in result
        assert "Option 3" not in result
        assert "Great insights on Tesla!" in result

    def test_picks_first_version(self):
        text = (
            "Version 1: Great insights on Tesla!\n\n"
            "Version 2: Tesla is leading the charge!"
        )
        result = _clean_ai_output(text)
        assert "Version" not in result
        assert "Great insights on Tesla!" in result

    def test_picks_first_alternative(self):
        text = (
            "Alternative 1 - Great insights on Tesla!\n\n"
            "Alternative 2 - Tesla is leading the charge!"
        )
        result = _clean_ai_output(text)
        assert "Alternative" not in result
        assert "Great insights on Tesla!" in result

    def test_removes_wrapping_double_quotes(self):
        text = '"Great insights on sustainability! #Tesla #EV"'
        assert _clean_ai_output(text) == "Great insights on sustainability! #Tesla #EV"

    def test_removes_wrapping_single_quotes(self):
        text = "'Great insights on sustainability!'"
        assert _clean_ai_output(text) == "Great insights on sustainability!"

    def test_preserves_internal_quotes(self):
        text = 'Tesla says "the future is electric" and we agree!'
        assert _clean_ai_output(text) == text

    def test_combined_preamble_and_options(self):
        text = (
            "Here are some post options:\n"
            "Option 1: Great insights on Tesla!\n\n"
            "Option 2: Tesla is leading the charge!"
        )
        result = _clean_ai_output(text)
        assert "Option" not in result
        assert "Great insights on Tesla!" in result
