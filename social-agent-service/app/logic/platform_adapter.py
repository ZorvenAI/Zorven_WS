"""Platform-specific content adaptation via Gemini (or stub)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.api.schemas import SocialPost
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)

# Platform character limits
LINKEDIN_MAX_CHARS = 3000
TWITTER_MAX_CHARS = 280
FACEBOOK_MAX_CHARS = 500
INSTAGRAM_MAX_CHARS = 2200


class PlatformAdapter:
    """Adapts blog content into platform-specific social posts."""

    def __init__(self, gemini_model: Any = None) -> None:
        self._model = gemini_model

    async def adapt(
        self,
        blog_content: str,
        seo_meta: dict[str, Any],
        brand_persona: dict[str, Any],
        platforms: list[str],
    ) -> list[SocialPost]:
        """Adapt blog content for each target platform."""
        posts: list[SocialPost] = []

        for platform in platforms:
            try:
                if self._model is not None:
                    post = await self._ai_adapt(
                        blog_content, seo_meta, brand_persona, platform
                    )
                else:
                    post = self._stub_adapt(
                        blog_content, seo_meta, brand_persona, platform
                    )
                posts.append(post)
            except Exception as exc:
                logger.warning(
                    "AI adaptation failed for %s, falling back to stub: %s",
                    platform,
                    exc,
                )
                post = self._stub_adapt(blog_content, seo_meta, brand_persona, platform)
                posts.append(post)

        return posts

    async def _ai_adapt(
        self,
        blog_content: str,
        seo_meta: dict[str, Any],
        brand_persona: dict[str, Any],
        platform: str,
    ) -> SocialPost:
        """Use Gemini to generate a platform-specific post."""
        brand_name = sanitize_ai_prompt(str(brand_persona.get("name", "the brand")))
        brand_voice = sanitize_ai_prompt(
            str(brand_persona.get("brand_voice", "professional"))
        )
        keywords = [sanitize_ai_prompt(str(kw)) for kw in seo_meta.get("keywords", [])]

        sanitized_content = sanitize_ai_prompt(blog_content[:3000])

        prompt = self._build_prompt(
            platform, sanitized_content, brand_name, brand_voice, keywords
        )

        response = await asyncio.to_thread(
            self._model.generate_content,
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 1024,
            },
        )

        content = response.text.strip()
        hashtags = [f"#{kw.replace(' ', '')}" for kw in keywords[:5]]

        return self._build_post(platform, content, hashtags)

    def _build_prompt(
        self,
        platform: str,
        content: str,
        brand_name: str,
        brand_voice: str,
        keywords: list[str],
    ) -> str:
        """Build a platform-specific prompt for Gemini."""
        keyword_str = ", ".join(keywords[:5]) if keywords else "industry-relevant"

        prompts = {
            "linkedin": (
                f"Adapt this blog into a LinkedIn post for {brand_name}. "
                f"Use a {brand_voice} tone. "
                "Structure: 3 paragraphs — hook, value proposition, CTA. "
                f"Max {LINKEDIN_MAX_CHARS} characters. "
                f"Include 3-5 industry hashtags related to: {keyword_str}.\n\n"
                f"Blog content:\n{content}"
            ),
            "twitter": (
                f"Adapt this blog into a Twitter thread of 3-5 tweets for {brand_name}. "
                f"Use a {brand_voice} tone. "
                f"Each tweet max {TWITTER_MAX_CHARS} characters. "
                "First tweet is a hook. Last tweet links back. "
                "Use data points from the blog. Separate tweets with blank lines.\n\n"
                f"Blog content:\n{content}"
            ),
            "facebook": (
                f"Adapt this blog into a Facebook post for {brand_name}. "
                f"Use a conversational, {brand_voice} tone. "
                "Include a question to drive engagement. "
                f"Max {FACEBOOK_MAX_CHARS} characters for optimal reach.\n\n"
                f"Blog content:\n{content}"
            ),
            "instagram": (
                f"Adapt this blog into an Instagram caption for {brand_name}. "
                f"Use a {brand_voice} tone that is visual and engaging. "
                "Start with a strong hook line. Use short paragraphs and "
                "line breaks for readability. End with a clear CTA. "
                f"Include 10-15 relevant hashtags related to: {keyword_str}. "
                f"Max {INSTAGRAM_MAX_CHARS} characters.\n\n"
                f"Blog content:\n{content}"
            ),
        }

        return prompts.get(platform, prompts["linkedin"])

    def _stub_adapt(
        self,
        blog_content: str,
        seo_meta: dict[str, Any],
        brand_persona: dict[str, Any],
        platform: str,
    ) -> SocialPost:
        """Template-based fallback when Gemini is not available."""
        title = seo_meta.get("title", "")
        keywords = seo_meta.get("keywords", [])
        hashtags = [f"#{kw.replace(' ', '')}" for kw in keywords[:5]]

        if platform == "linkedin":
            content = blog_content[:500]
            if len(blog_content) > 500:
                content += "\n\nRead more..."
            if title:
                content = f"{title}\n\n{content}"
            return self._build_post(platform, content, hashtags, "article_share")

        if platform == "twitter":
            prefix = f"{title}\n\n" if title else ""
            content = prefix + blog_content[:200]
            if len(content) > TWITTER_MAX_CHARS:
                content = content[: TWITTER_MAX_CHARS - 3] + "..."
            return self._build_post(platform, content, hashtags[:3], "thread")

        if platform == "instagram":
            prefix = f"{title}\n\n" if title else ""
            content = prefix + blog_content[:800]
            if len(blog_content) > 800:
                content += "\n\n..."
            return self._build_post(platform, content, hashtags[:15], "caption")

        # facebook or default
        prefix = f"{title}\n\n" if title else ""
        content = prefix + blog_content[:400]
        return self._build_post(platform, content, [], "status")

    def _build_post(
        self,
        platform: str,
        content: str,
        hashtags: list[str],
        post_type: str = "",
    ) -> SocialPost:
        """Construct a SocialPost with character count."""
        if not post_type:
            post_type = {
                "linkedin": "article_share",
                "twitter": "thread",
                "facebook": "status",
                "instagram": "caption",
            }.get(platform, "status")

        return SocialPost(
            platform=platform,
            content=content,
            hashtags=hashtags,
            char_count=len(content),
            post_type=post_type,
        )
