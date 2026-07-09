"""SKL-TCIA-05: Slang & Language Tracker.

Monitors emerging slang, fading terms, and language evolution.
Hybrid sensitivity scoring: keyword filter first, LLM judge if needed.
"""

import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SENSITIVE_KEYWORDS = {
    "slur",
    "offensive",
    "derogatory",
    "racial",
    "hate",
    "discriminatory",
    "vulgar",
    "profanity",
    "explicit",
    "nsfw",
}

_FADING_MARKERS = [
    "no longer used",
    "outdated",
    "fading",
    "dying out",
    "out of fashion",
    "passé",
    "cringe",
    "old-fashioned",
    "overused",
    "dead slang",
    "stopped using",
    "fell out of use",
]


class SlangLanguageTracker(BaseSkill):
    """Track emerging slang, language evolution, and sensitivity."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-05",
        name="slang_language_tracker",
        description="Track emerging slang and language evolution with sensitivity scoring",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=30000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(
        self,
        tavily_client: Any,
        scraper_client: Any,
        anthropic_client: Any = None,
        cb_tavily: Any = None,
        cb_httpx: Any = None,
        cb_llm: Any = None,
    ) -> None:
        self._tavily = tavily_client
        self._scraper = scraper_client
        self._anthropic = anthropic_client
        self._cb_tavily = cb_tavily
        self._cb_httpx = cb_httpx
        self._cb_llm = cb_llm

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()
        industry = input_data.get("industry", "")
        target_demographics = input_data.get("target_demographics", [])
        platforms = input_data.get("platforms", ["tiktok", "twitter", "reddit"])

        query = f"emerging slang terms {industry} social media language trends 2025 2026"
        try:
            if self._cb_tavily:
                results = await self._cb_tavily.call(
                    self._tavily.search, query, max_results=10
                )
            else:
                results = await self._tavily.search(query, max_results=10)
        except Exception as exc:
            logger.warning("Slang search failed: %s", exc)
            results = []

        # Collect raw search content for LLM extraction
        raw_content_parts: list[str] = []
        raw_urls: list[tuple[str, str]] = []  # (url, content)
        for r in results:
            content = r.get("content", "")
            url = r.get("url", "")
            if content:
                raw_content_parts.append(content[:500])
                raw_urls.append((url, content))

        # Use LLM to extract actual slang terms from search results
        emerging_terms: list[dict[str, Any]] = []
        if self._anthropic and raw_content_parts:
            try:
                emerging_terms = await self._llm_extract_terms(
                    industry, raw_content_parts, raw_urls
                )
            except Exception as exc:
                logger.warning("LLM term extraction failed: %s", exc)

        # Fallback: heuristic extraction if LLM unavailable or failed
        if not emerging_terms:
            for r in results:
                content = r.get("content", "")
                title = r.get("title", "")
                url = r.get("url", "")

                origin_platform = self._detect_origin_platform(url, content)
                adoption_stage = self._detect_adoption_stage(content)
                keyword_score = self._keyword_sensitivity_score(content)
                sensitivity_flag = keyword_score >= 2

                term_data = {
                    "term": title[:100],
                    "definition": content[:300],
                    "origin_platform": origin_platform,
                    "adoption_stage": adoption_stage,
                    "sensitivity_flag": sensitivity_flag,
                }
                emerging_terms.append(term_data)

        # Search for fading terms and language shifts
        fading_terms: list[str] = []
        language_shifts: list[str] = []

        fading_query = (
            f"outdated slang terms no longer used {industry} "
            f"fading language trends 2025 2026"
        )
        try:
            if self._cb_tavily:
                fading_results = await self._cb_tavily.call(
                    self._tavily.search, fading_query, max_results=5
                )
            else:
                fading_results = await self._tavily.search(
                    fading_query, max_results=5
                )
            for r in fading_results:
                content = r.get("content", "").lower()
                for marker in _FADING_MARKERS:
                    idx = content.find(marker)
                    if idx != -1:
                        # Extract the term/phrase near the fading marker
                        snippet = content[max(0, idx - 30) : idx + len(marker) + 50]
                        snippet = snippet.strip()[:80]
                        if snippet and snippet not in fading_terms:
                            fading_terms.append(snippet)
        except Exception as exc:
            logger.warning("Fading terms search failed: %s", exc)

        shifts_query = (
            f"language evolution shifts communication style changes "
            f"{industry} {' '.join(platforms[:2])} 2025 2026"
        )
        try:
            if self._cb_tavily:
                shift_results = await self._cb_tavily.call(
                    self._tavily.search, shifts_query, max_results=5
                )
            else:
                shift_results = await self._tavily.search(
                    shifts_query, max_results=5
                )
            for r in shift_results:
                content = r.get("content", "")[:300]
                if content:
                    language_shifts.append(content[:200])
        except Exception as exc:
            logger.warning("Language shifts search failed: %s", exc)

        language_trends = {
            "emerging_terms": emerging_terms[:15],
            "fading_terms": fading_terms[:10],
            "language_shifts": language_shifts[:10],
        }

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"language_trends": language_trends},
            duration_ms=elapsed,
        )

    @staticmethod
    def _keyword_sensitivity_score(text: str) -> int:
        """Fast keyword-based sensitivity score (~50ms). Returns count of matches."""
        text_lower = text.lower()
        return sum(1 for kw in _SENSITIVE_KEYWORDS if kw in text_lower)

    @staticmethod
    def _keyword_sensitivity_check(text: str) -> bool:
        """Fast keyword-based sensitivity check (~50ms)."""
        text_lower = text.lower()
        score = sum(1 for kw in _SENSITIVE_KEYWORDS if kw in text_lower)
        return score >= 2

    @staticmethod
    def _detect_origin_platform(url: str, content: str) -> str:
        """Detect origin platform from URL or content mentions."""
        combined = f"{url} {content}".lower()
        platform_signals = {
            "tiktok": ["tiktok.com", "tiktok"],
            "twitter": ["twitter.com", "x.com", "tweet", "twitter"],
            "reddit": ["reddit.com", "subreddit", "reddit"],
            "instagram": ["instagram.com", "instagram"],
            "youtube": ["youtube.com", "youtube"],
            "discord": ["discord.com", "discord"],
            "twitch": ["twitch.tv", "twitch"],
            "snapchat": ["snapchat.com", "snapchat"],
        }
        for platform, signals in platform_signals.items():
            if any(s in combined for s in signals):
                return platform
        return "unknown"

    @staticmethod
    def _detect_adoption_stage(content: str) -> str:
        """Detect adoption stage from content signals."""
        content_lower = content.lower()
        if any(
            w in content_lower
            for w in ["mainstream", "widely used", "common", "everyone"]
        ):
            return "mainstream"
        if any(
            w in content_lower
            for w in ["gaining traction", "growing", "rising", "spreading"]
        ):
            return "growing"
        if any(
            w in content_lower
            for w in ["niche", "subculture", "underground", "early adopter"]
        ):
            return "niche"
        if any(
            w in content_lower
            for w in ["fading", "outdated", "declining", "no longer"]
        ):
            return "fading"
        return "emerging"

    async def _llm_extract_terms(
        self,
        industry: str,
        content_parts: list[str],
        raw_urls: list[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        """Use LLM to extract actual slang/language terms from search content."""
        import json as _json

        combined = "\n---\n".join(content_parts[:8])
        prompt = (
            f"Extract emerging slang terms and language trends from the "
            f"following web search results about {industry or 'social media'}. "
            f"Return a JSON array of objects with these fields:\n"
            f'- "term": the slang term or phrase (2-5 words max)\n'
            f'- "definition": a clear 1-sentence definition\n'
            f'- "origin_platform": where it originated '
            f"(tiktok/twitter/reddit/instagram/unknown)\n"
            f'- "adoption_stage": one of emerging/growing/mainstream/niche/fading\n'
            f'- "sensitivity_flag": true if potentially offensive\n\n'
            f"Extract 5-10 distinct terms. Only include actual slang/language "
            f"trends, NOT article titles or generic phrases.\n\n"
            f"Search content:\n{combined}\n\n"
            f"Return ONLY the JSON array, no markdown fences."
        )
        call_kwargs = {
            "model": "claude-sonnet-5",
            "max_tokens": 2000,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._cb_llm:
            response = await self._cb_llm.call(
                lambda: self._anthropic.messages.create(**call_kwargs)
            )
        else:
            response = await self._anthropic.messages.create(**call_kwargs)

        text = next(b.text for b in response.content if b.type == "text").strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        terms = _json.loads(text)
        if not isinstance(terms, list):
            return []

        # Enrich with platform detection for any missing fields
        enriched = []
        for t in terms[:15]:
            if not isinstance(t, dict) or not t.get("term"):
                continue
            definition = t.get("definition", "")
            enriched.append({
                "term": str(t["term"])[:100],
                "definition": str(definition)[:300],
                "origin_platform": t.get("origin_platform", "unknown"),
                "adoption_stage": t.get("adoption_stage", "emerging"),
                "sensitivity_flag": bool(t.get("sensitivity_flag", False)),
            })
        return enriched

    async def _llm_sensitivity_judge(self, term: str, definition: str) -> bool:
        """LLM-based sensitivity evaluation (~400ms) for borderline terms."""
        prompt = (
            f"Evaluate whether the following slang term is culturally sensitive, "
            f"offensive, or inappropriate for brand marketing use. "
            f"Reply with ONLY 'SENSITIVE' or 'SAFE'.\n\n"
            f"Term: {term}\n"
            f"Definition: {definition}\n\n"
            f"Verdict:"
        )
        try:
            call_fn = self._anthropic.messages.create
            if self._cb_llm:
                call_fn_wrapped = lambda: self._anthropic.messages.create(
                    model="claude-sonnet-5",
                    max_tokens=10,
                    thinking={"type": "disabled"},
                    messages=[{"role": "user", "content": prompt}],
                )
                response = await self._cb_llm.call(call_fn_wrapped)
            else:
                response = await self._anthropic.messages.create(
                    model="claude-sonnet-5",
                    max_tokens=10,
                    thinking={"type": "disabled"},
                    messages=[{"role": "user", "content": prompt}],
                )
            text = next(b.text for b in response.content if b.type == "text").strip().upper()
            return "SENSITIVE" in text
        except Exception as exc:
            logger.warning("LLM sensitivity judge error: %s", exc)
            return False
