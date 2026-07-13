"""
SEO Optimizer — generates keywords, meta tags, header structure, and URL slugs.

In AI mode (Gemini available), uses LLM to generate optimized SEO data.
In stub mode, uses word frequency analysis and templates.
"""

import asyncio
import logging
import re
from collections import Counter
from typing import Any, Optional

from app.prompts.fallbacks import FALLBACK_SEO_OPTIMIZER
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)


class SEOOptimizer:
    """Generates SEO metadata for blog content."""

    def __init__(
        self,
        gemini_model: Any = None,
        prompt_loader: Optional[Any] = None,
    ) -> None:
        self._model = gemini_model
        self._prompt_loader = prompt_loader

    async def optimize(
        self,
        topic: str,
        research_context: str,
        brand_persona: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate SEO optimization data for a blog topic.

        Returns: {keywords, meta_title, meta_description, headers, slug}
        """
        if self._model is not None:
            return await self._ai_optimize(topic, research_context, brand_persona)
        return self._stub_optimize(topic, brand_persona)

    async def _ai_optimize(
        self,
        topic: str,
        research_context: str,
        brand_persona: dict[str, Any],
    ) -> dict[str, Any]:
        """Use Gemini to generate SEO data."""
        safe_topic = sanitize_ai_prompt(topic)
        safe_context = sanitize_ai_prompt(research_context[:2000])

        # Load system prompt from prompt-optimization-svc (or fallback)
        system_prompt = FALLBACK_SEO_OPTIMIZER
        if self._prompt_loader:
            system_prompt = await self._prompt_loader.load(
                "zorven-content-seo",
                fallback=FALLBACK_SEO_OPTIMIZER,
            )

        prompt = (
            f"{system_prompt}\n"
            f"Topic: {safe_topic}\n"
            f"Industry: {brand_persona.get('industry', 'General')}\n"
            f"Target Audience: {brand_persona.get('target_audience', '')}\n"
            f"Research Context (first 2000 chars): "
            f"{safe_context}\n"
        )

        try:
            response = await asyncio.to_thread(self._model.generate_content, prompt)
            text = response.text.strip()

            # Extract JSON from potential markdown code blocks
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if json_match:
                text = json_match.group(1)

            import json

            data = json.loads(text, strict=False)

            # Enforce constraints
            meta_title = str(data.get("meta_title", topic))[:60]
            meta_desc = str(data.get("meta_description", ""))[:160]

            return {
                "keywords": data.get("keywords", [])[:8],
                "meta_title": meta_title,
                "meta_description": meta_desc,
                "headers": data.get("headers", []),
                "slug": data.get("slug", self._generate_slug(topic)),
            }
        except Exception as exc:
            logger.warning("Gemini SEO optimization failed: %s. Using stub.", exc)
            return self._stub_optimize(topic, brand_persona)

    def _stub_optimize(
        self, topic: str, brand_persona: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate SEO data via word frequency analysis."""
        words = re.findall(r"\b[a-zA-Z]{3,}\b", topic.lower())
        stop_words = {
            "the",
            "and",
            "for",
            "that",
            "this",
            "with",
            "from",
            "are",
            "was",
            "were",
            "been",
            "have",
            "has",
            "our",
            "about",
            "can",
            "will",
            "how",
            "what",
            "why",
            "who",
            "when",
            "where",
        }
        filtered = [w for w in words if w not in stop_words]
        freq = Counter(filtered)
        keywords = [word for word, _ in freq.most_common(6)]

        industry = brand_persona.get("industry", "")
        if industry and industry.lower() not in keywords:
            keywords.append(industry.lower())

        slug = self._generate_slug(topic)
        meta_title = topic[:57] + "..." if len(topic) > 60 else topic
        meta_desc = (
            f"Discover insights about {topic[:80]}. "
            f"Expert analysis for {brand_persona.get('target_audience', 'professionals')}."
        )[:160]

        return {
            "keywords": keywords[:8],
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "headers": [
                "Introduction",
                "Key Insights",
                "Analysis",
                "Recommendations",
                "Conclusion",
            ],
            "slug": slug,
        }

    @staticmethod
    def _generate_slug(topic: str) -> str:
        """Generate a URL-friendly slug from a topic."""
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", topic.lower())
        slug = re.sub(r"[\s]+", "-", slug.strip())
        slug = re.sub(r"-+", "-", slug)
        return slug[:80]
