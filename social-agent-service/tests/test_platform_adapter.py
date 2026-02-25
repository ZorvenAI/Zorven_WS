"""Tests for platform content adaptation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.logic.platform_adapter import (
    FACEBOOK_MAX_CHARS,
    LINKEDIN_MAX_CHARS,
    TWITTER_MAX_CHARS,
    PlatformAdapter,
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
            ["linkedin", "twitter", "facebook"],
        )
        assert len(posts) == 3
        platforms = {p.platform for p in posts}
        assert platforms == {"linkedin", "twitter", "facebook"}


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
