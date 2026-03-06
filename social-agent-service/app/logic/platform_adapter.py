"""Platform-specific content adaptation via Gemini (or stub)."""

from __future__ import annotations

import asyncio
import logging
import re
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
        skill_context: str = "",
    ) -> list[SocialPost]:
        """Adapt blog content for each target platform."""
        posts: list[SocialPost] = []

        for platform in platforms:
            try:
                if self._model is not None:
                    post = await self._ai_adapt(
                        blog_content, seo_meta, brand_persona, platform,
                        skill_context=skill_context,
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
        skill_context: str = "",
    ) -> SocialPost:
        """Use Gemini to generate a platform-specific post."""
        brand_name = sanitize_ai_prompt(str(brand_persona.get("name", "the brand")))
        brand_voice = sanitize_ai_prompt(
            str(brand_persona.get("brand_voice", "professional"))
        )
        keywords = [sanitize_ai_prompt(str(kw)) for kw in seo_meta.get("keywords", [])]

        sanitized_content = sanitize_ai_prompt(blog_content[:3000])

        prompt = self._build_prompt(
            platform, sanitized_content, brand_name, brand_voice, keywords,
            skill_context=skill_context,
        )

        response = await asyncio.wait_for(
            asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config={
                    "temperature": 0.4,
                    "max_output_tokens": 1024,
                },
            ),
            timeout=60,
        )

        content = _clean_ai_output(response.text.strip())
        hashtags = [f"#{kw.replace(' ', '')}" for kw in keywords[:5]]

        return self._build_post(platform, content, hashtags)

    def _build_prompt(
        self,
        platform: str,
        content: str,
        brand_name: str,
        brand_voice: str,
        keywords: list[str],
        skill_context: str = "",
    ) -> str:
        """Build a platform-specific prompt for Gemini."""
        keyword_str = ", ".join(keywords[:5]) if keywords else "industry-relevant"

        # Common instruction to prevent multiple options / alternatives
        no_options = (
            "IMPORTANT: Output ONLY the final post text — nothing else. "
            "Do NOT provide multiple options, alternatives, or variations. "
            "Do NOT include labels like 'Option 1' or 'Here is a post'. "
            "Just write the post itself, ready to publish."
        )

        # Detect whether content is structured analysis data (brand equity
        # metrics, BSI scores) versus blog/article content, and tailor the
        # prompt accordingly so Gemini produces contextually accurate posts.
        is_analysis = _is_analysis_content(content)

        if is_analysis:
            return self._build_analysis_prompt(
                platform,
                content,
                brand_name,
                brand_voice,
                keyword_str,
                no_options,
                skill_context=skill_context,
            )

        prompts = {
            "linkedin": (
                f"Write exactly ONE LinkedIn post for {brand_name} based on "
                f"the blog content below. Use a {brand_voice} tone. "
                "Structure the post as: a compelling hook line, then the key "
                "value or insight from the blog, then a call to action. "
                f"Stay under {LINKEDIN_MAX_CHARS} characters. "
                f"End with 3-5 hashtags related to: {keyword_str}.\n\n"
                f"{no_options}\n\n"
                f"Blog content:\n{content}"
            ),
            "twitter": (
                f"Write exactly ONE tweet for {brand_name} based on "
                f"the blog content below. Use a {brand_voice} tone. "
                f"The tweet must be under {TWITTER_MAX_CHARS} characters. "
                "Summarize the key insight in a concise, engaging way. "
                f"Include 1-2 hashtags related to: {keyword_str}.\n\n"
                f"{no_options}\n\n"
                f"Blog content:\n{content}"
            ),
            "facebook": (
                f"Write exactly ONE Facebook post for {brand_name} based on "
                f"the blog content below. Use a conversational, {brand_voice} "
                "tone. Include a question to drive engagement. "
                f"Stay under {FACEBOOK_MAX_CHARS} characters.\n\n"
                f"{no_options}\n\n"
                f"Blog content:\n{content}"
            ),
            "instagram": (
                f"Write exactly ONE Instagram caption for {brand_name} based on "
                f"the blog content below. Use a {brand_voice} tone that is "
                "visual and engaging. Start with a strong hook line. Use short "
                "paragraphs and line breaks for readability. End with a clear "
                "CTA. Include 10-15 relevant hashtags related to: "
                f"{keyword_str}. Stay under {INSTAGRAM_MAX_CHARS} characters.\n\n"
                f"{no_options}\n\n"
                f"Blog content:\n{content}"
            ),
        }

        base_prompt = prompts.get(platform, prompts["linkedin"])
        if skill_context:
            base_prompt += f"\n\n{skill_context}"
        return base_prompt

    def _build_analysis_prompt(
        self,
        platform: str,
        content: str,
        brand_name: str,
        brand_voice: str,
        keyword_str: str,
        no_options: str,
        skill_context: str = "",
    ) -> str:
        """Build prompts tailored for brand equity / analysis data."""
        limits = {
            "linkedin": LINKEDIN_MAX_CHARS,
            "twitter": TWITTER_MAX_CHARS,
            "facebook": FACEBOOK_MAX_CHARS,
            "instagram": INSTAGRAM_MAX_CHARS,
        }
        char_limit = limits.get(platform, LINKEDIN_MAX_CHARS)

        base_instruction = (
            f"You are writing a social media post for {brand_name}. "
            f"Use a {brand_voice} tone.\n\n"
            "The data below contains brand valuation and strength metrics "
            "from an ISO 10668 brand equity analysis. Transform these results "
            "into an engaging social media post that highlights the key "
            "achievements and business value.\n\n"
            "Guidelines:\n"
            "- Lead with a compelling insight or headline number\n"
            "- Translate financial metrics into business impact language\n"
            "- Include specific numbers (valuation, BSI score) naturally\n"
            "- End with a forward-looking call to action\n"
        )

        platform_specifics = {
            "linkedin": (
                f"Write exactly ONE LinkedIn post. "
                "Structure as: attention-grabbing headline metric, "
                "then 2-3 sentences explaining what the numbers mean "
                "for the business, then a call to action. "
                f"Stay under {char_limit} characters. "
                f"End with 3-5 hashtags related to: {keyword_str}."
            ),
            "twitter": (
                f"Write exactly ONE tweet under {char_limit} characters. "
                "Highlight the single most impressive metric with context. "
                f"Include 1-2 hashtags related to: {keyword_str}."
            ),
            "facebook": (
                f"Write exactly ONE Facebook post under {char_limit} characters. "
                "Make it conversational — share the results as an exciting "
                "milestone. Include a question to drive engagement."
            ),
            "instagram": (
                f"Write exactly ONE Instagram caption under {char_limit} "
                "characters. Start with a strong hook. Use short paragraphs "
                "and line breaks. End with a CTA. Include 10-15 hashtags "
                f"related to: {keyword_str}."
            ),
        }

        specifics = platform_specifics.get(platform, platform_specifics["linkedin"])

        prompt = (
            f"{base_instruction}\n"
            f"{specifics}\n\n"
            f"{no_options}\n\n"
            f"Brand analysis results:\n{content}"
        )
        if skill_context:
            prompt += f"\n\n{skill_context}"
        return prompt

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


# ── Content-type detection ───────────────────────────────────────────

# Phrases that signal structured brand-equity / analysis output
_ANALYSIS_MARKERS = (
    "brand valuation:",
    "brand strength index",
    "royalty rate:",
    "forecast horizon:",
    "key findings:",
    "bsi:",
    "(iso 10668",
)


def _is_analysis_content(content: str) -> bool:
    """Return True when *content* looks like structured analysis metrics."""
    lower = content[:500].lower()
    return sum(1 for m in _ANALYSIS_MARKERS if m in lower) >= 2


# ── Post-processing helpers ──────────────────────────────────────────

# Patterns that indicate Gemini returned multiple options instead of one post
_OPTION_HEADER_RE = re.compile(
    r"^(?:option\s*\d+|version\s*\d+|alternative\s*\d+|variant\s*\d+)\s*[:\-—]",
    re.IGNORECASE | re.MULTILINE,
)
_INTRO_PREAMBLE_RE = re.compile(
    r"^("
    r"(?:here (?:is|are)|below (?:is|are)|sure[,!]|certainly[,!]|"
    r"i'?d suggest|let me|this is a|the following)"
    r"[^\n]{0,80}?"
    r"(?:post|caption|tweet|thread|social(?: media)? (?:post|content))\s*[:\-—]"
    r"|"
    r"(?:post|caption|tweet|thread)\s*[:\-—]"
    r")\s*\n+",
    re.IGNORECASE,
)


def _clean_ai_output(text: str) -> str:
    """Strip preamble and pick the first option if Gemini returned multiples."""
    # Remove conversational preamble ("Here is a post for you:\n...")
    text = _INTRO_PREAMBLE_RE.sub("", text).strip()

    # If the response contains option headers, keep only the first option body
    if _OPTION_HEADER_RE.search(text):
        blocks = _OPTION_HEADER_RE.split(text)
        # blocks[0] is text before first header (usually empty), blocks[1] is first option
        if len(blocks) >= 2:
            first_option = blocks[1].strip()
            if first_option:
                text = first_option

    # Remove wrapping quotes if the entire text is quoted
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()

    return text
