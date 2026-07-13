"""
Blog Author — generates full Markdown blog posts.

In AI mode (Gemini available), constructs a multi-part prompt including
brand persona, SEO instructions, GEO citations, and research context.
In stub mode, generates a template Markdown blog with placeholder content.
"""

import asyncio
import logging
import re
from typing import Any, Optional

from app.api.schemas import Citation
from app.prompts.fallbacks import FALLBACK_BLOG_AUTHOR
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)


class BlogAuthor:
    """Generates Markdown blog posts with brand voice and SEO optimization."""

    def __init__(
        self,
        gemini_model: Any = None,
        prompt_loader: Optional[Any] = None,
    ) -> None:
        self._model = gemini_model
        self._prompt_loader = prompt_loader

    async def author(
        self,
        topic: str,
        research_context: str,
        brand_persona: dict[str, Any],
        seo_data: dict[str, Any],
        citations: list[Citation],
        skill_context: str = "",
    ) -> str:
        """
        Generate a full Markdown blog post.

        Returns: Markdown string (800-1200 words target).
        """
        if self._model is not None:
            return await self._ai_author(
                topic,
                research_context,
                brand_persona,
                seo_data,
                citations,
                skill_context=skill_context,
            )
        return self._stub_author(topic, brand_persona, seo_data, citations)

    async def _ai_author(
        self,
        topic: str,
        research_context: str,
        brand_persona: dict[str, Any],
        seo_data: dict[str, Any],
        citations: list[Citation],
        skill_context: str = "",
    ) -> str:
        """Use Gemini to generate a blog post."""
        keywords = seo_data.get("keywords", [])
        headers = seo_data.get("headers", [])

        # Format citations for the prompt
        citation_text = "\n".join(
            f"- {c.claim} — [{c.source_title}]({c.source_url})"
            for c in citations
            if c.source_url
        )

        safe_topic = sanitize_ai_prompt(topic)
        safe_context = sanitize_ai_prompt(research_context[:4000])

        # Load system instructions from prompt-optimization-svc (or fallback)
        blog_variables = {
            "brand_name": brand_persona.get("name", "a brand"),
            "brand_voice": brand_persona.get("brand_voice", "professional"),
            "target_audience": brand_persona.get("target_audience", "professionals"),
            "industry": brand_persona.get("industry", "General"),
            "values": ", ".join(brand_persona.get("values", [])),
        }
        if self._prompt_loader:
            system_instructions = await self._prompt_loader.load(
                "zorven-content-blog",
                fallback=FALLBACK_BLOG_AUTHOR,
                variables=blog_variables,
            )
        else:
            system_instructions = FALLBACK_BLOG_AUTHOR.format(**blog_variables)

        prompt = (
            f"{system_instructions}\n"
            f"## SEO Instructions\n"
            f"Target keywords: {', '.join(keywords)}\n"
            f"Suggested sections: {', '.join(headers)}\n"
            f"Naturally incorporate keywords throughout the post. "
            f"Use H2 headers for main sections.\n\n"
            f"## GEO Instructions\n"
            f"Include data-backed claims. Cite sources using "
            f"[Source Title](URL) format.\n"
            f"Available citations:\n{citation_text or 'No citations available.'}\n\n"
            f"## Research Context\n"
            f"{safe_context}\n\n"
        )

        if skill_context:
            prompt += f"{skill_context}\n\n"

        prompt += (
            f"## Task\n"
            f'Write a 800-1200 word blog post about "{safe_topic}" in Markdown format.\n'
            f"Include:\n"
            f"- H1 title as the first line\n"
            f"- H2 sections for each major topic\n"
            f"- Bullet points where appropriate\n"
            f"- Data-backed claims with source citations\n"
            f"- A brief conclusion section\n"
            f"Output ONLY the Markdown blog post, nothing else.\n"
        )

        try:
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 4096,
                },
                request_options={"timeout": 120},
            )
            blog = response.text.strip()
            blog = self._post_process(blog)
            return blog
        except TimeoutError:
            logger.warning("Gemini blog authoring timed out (120s). Using stub.")
            return self._stub_author(topic, brand_persona, seo_data, citations)
        except Exception as exc:
            logger.warning("Gemini blog authoring failed: %s. Using stub.", exc)
            return self._stub_author(topic, brand_persona, seo_data, citations)

    def _stub_author(
        self,
        topic: str,
        brand_persona: dict[str, Any],
        seo_data: dict[str, Any],
        citations: list[Citation],
    ) -> str:
        """Generate a template Markdown blog."""
        name = brand_persona.get("name", "Our Brand")
        industry = brand_persona.get("industry", "the industry")
        audience = brand_persona.get("target_audience", "professionals")
        keywords = seo_data.get("keywords", [])
        keyword_str = ", ".join(keywords[:3]) if keywords else topic

        citation_section = ""
        if citations:
            citation_lines = []
            for c in citations[:5]:
                if c.source_url:
                    citation_lines.append(f"- [{c.source_title}]({c.source_url})")
                else:
                    citation_lines.append(f"- {c.source_title}")
            citation_section = "\n## Sources\n\n" + "\n".join(citation_lines) + "\n"

        return (
            f"# {topic}\n\n"
            f"## Introduction\n\n"
            f"In today's rapidly evolving landscape of {industry}, understanding "
            f"{topic.lower()} has become essential for {audience}. "
            f"At {name}, we believe in delivering data-driven insights "
            f"that empower strategic decision-making.\n\n"
            f"## Key Insights\n\n"
            f"When examining {keyword_str}, several critical factors emerge:\n\n"
            f"- **Market Dynamics**: The landscape continues to shift as "
            f"organizations adapt to new challenges and opportunities.\n"
            f"- **Strategic Positioning**: Companies that invest in understanding "
            f"{keyword_str} gain a competitive advantage.\n"
            f"- **Data-Driven Approach**: Leveraging analytics and research "
            f"provides actionable insights for growth.\n\n"
            f"## Analysis\n\n"
            f"Our research indicates that {topic.lower()} is a multifaceted "
            f"subject requiring careful consideration of market trends, "
            f"competitive dynamics, and audience needs. Organizations in "
            f"{industry} should prioritize:\n\n"
            f"1. Comprehensive market analysis\n"
            f"2. Audience-centric content strategy\n"
            f"3. Continuous performance measurement\n\n"
            f"## Recommendations\n\n"
            f"Based on our analysis, we recommend the following approach:\n\n"
            f"- Develop a structured content calendar aligned with {keyword_str}\n"
            f"- Invest in audience research to refine messaging\n"
            f"- Establish clear KPIs for measuring content effectiveness\n"
            f"- Foster cross-functional collaboration between marketing and "
            f"analytics teams\n\n"
            f"## Conclusion\n\n"
            f"As {industry} continues to evolve, staying ahead requires a "
            f"commitment to excellence in {topic.lower()}. By following these "
            f"recommendations and leveraging data-driven insights, "
            f"organizations can position themselves for sustained success.\n"
            f"{citation_section}"
        )

    @staticmethod
    def _post_process(blog: str) -> str:
        """Ensure proper Markdown formatting."""
        # Remove potential markdown code block wrapper
        if blog.startswith("```markdown"):
            blog = blog[len("```markdown") :].strip()
        if blog.startswith("```"):
            blog = blog[3:].strip()
        if blog.endswith("```"):
            blog = blog[:-3].strip()

        # Ensure starts with H1
        if not blog.startswith("#"):
            lines = blog.split("\n", 1)
            blog = f"# {lines[0]}\n{lines[1] if len(lines) > 1 else ''}"

        return blog
