"""
AEO Formatter — generates FAQ items and JSON-LD structured data.

In AI mode (Gemini available), uses LLM to generate natural FAQ questions.
In stub mode, generates template-based FAQ from keywords.
"""

import asyncio
import logging
import re
from typing import Any

from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)


class AEOFormatter:
    """Generates Answer Engine Optimization data for blog content."""

    def __init__(self, gemini_model: Any = None) -> None:
        self._model = gemini_model

    async def format(
        self,
        topic: str,
        blog_content: str,
        keywords: list[str],
    ) -> dict[str, Any]:
        """
        Generate AEO data: FAQ items and JSON-LD structured data.

        Returns: {faq_items, structured_data}
        """
        if self._model is not None:
            return await self._ai_format(topic, blog_content, keywords)
        return self._stub_format(topic, keywords)

    async def _ai_format(
        self,
        topic: str,
        blog_content: str,
        keywords: list[str],
    ) -> dict[str, Any]:
        """Use Gemini to generate FAQ items from blog content."""
        safe_topic = sanitize_ai_prompt(topic)
        safe_content = sanitize_ai_prompt(blog_content[:3000])

        prompt = (
            "You are an AEO (Answer Engine Optimization) expert. "
            "Based on the following blog content, generate 3-5 FAQ items "
            "that users would naturally ask about this topic.\n\n"
            "Return ONLY valid JSON with this structure:\n"
            '{"faq_items": [{"question": "...", "answer": "..."}]}\n\n'
            f"Topic: {safe_topic}\n"
            f"Keywords: {', '.join(keywords[:5])}\n"
            f"Blog content (first 3000 chars):\n{safe_content}\n"
        )

        try:
            response = await asyncio.to_thread(
                self._model.generate_content, prompt
            )
            text = response.text.strip()

            # Extract JSON from potential markdown code blocks
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if json_match:
                text = json_match.group(1)

            import json

            data = json.loads(text)
            faq_items = data.get("faq_items", [])[:5]

            structured_data = self._build_jsonld(faq_items)
            return {
                "faq_items": faq_items,
                "structured_data": structured_data,
            }
        except Exception as exc:
            logger.warning("Gemini AEO formatting failed: %s. Using stub.", exc)
            return self._stub_format(topic, keywords)

    def _stub_format(self, topic: str, keywords: list[str]) -> dict[str, Any]:
        """Generate template FAQ from topic and keywords."""
        faq_items = [
            {
                "question": f"What are the key aspects of {topic}?",
                "answer": (
                    f"The key aspects of {topic} include strategic analysis, "
                    "market positioning, and data-driven insights."
                ),
            },
            {
                "question": f"Why is {topic} important for businesses?",
                "answer": (
                    f"Understanding {topic} helps businesses make informed "
                    "decisions and stay competitive in their market."
                ),
            },
            {
                "question": f"How can companies improve their approach to {topic}?",
                "answer": (
                    f"Companies can improve their approach to {topic} by "
                    "leveraging data analytics, industry benchmarks, and "
                    "expert recommendations."
                ),
            },
        ]

        if keywords:
            faq_items.append(
                {
                    "question": (
                        f"What role does {keywords[0]} play in {topic}?"
                    ),
                    "answer": (
                        f"{keywords[0].capitalize()} is a critical component "
                        f"of {topic}, influencing strategy and outcomes."
                    ),
                }
            )

        structured_data = self._build_jsonld(faq_items)
        return {
            "faq_items": faq_items,
            "structured_data": structured_data,
        }

    @staticmethod
    def _build_jsonld(faq_items: list[dict[str, str]]) -> dict[str, Any]:
        """Build JSON-LD structured data for FAQPage schema."""
        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item.get("question", ""),
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": item.get("answer", ""),
                    },
                }
                for item in faq_items
            ],
        }
