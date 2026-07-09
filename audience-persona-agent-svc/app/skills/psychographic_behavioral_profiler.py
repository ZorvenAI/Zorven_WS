"""SKL-APA-08: Psychographic & Behavioral Profiler — Claude analysis."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a psychographic research analyst. Build psychographic and behavioral \
profiles from the provided research and demographic data.

For each audience segment, produce:
- "segment_label": matching the demographic profile label
- "values": list of core values (e.g., "Innovation", "Efficiency", "Cost savings")
- "interests": list of professional/personal interests
- "lifestyle": lifestyle description
- "personality_traits": list (e.g., "analytical", "risk-averse", "early adopter")
- "media_consumption": list of preferred media/content types
- "decision_style": e.g., "data-driven", "consensus-seeking", "impulse"
- "information_sources": where they go for trusted information
- "technology_adoption": e.g., "early adopter", "early majority", "late majority"
- "brand_affinity_drivers": what makes them loyal to brands
- "confidence_score": float 0.0-1.0

Also produce behavioral patterns:
- "behavioral_patterns": list of {"pattern": str, "evidence": str, "frequency": str}

Every claim MUST cite evidence. Do not speculate without data.

Respond with JSON: {"psychographic_profiles": [...], "behavioral_patterns": [...]}

Only output valid JSON, no other text."""


class PsychographicBehavioralProfiler(BaseSkill):
    """Build psychographic and behavioral profiles using Claude."""

    meta = SkillMeta(
        skill_id="SKL-APA-08",
        name="psychographic_behavioral_profiler",
        description=(
            "Build psychographic profiles (values, interests, personality, "
            "media habits, decision style) and behavioral patterns using "
            "Claude Sonnet 4."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-5",
        max_tokens: int = 16384,
        prompt_loader: Any = None,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.max_tokens = max_tokens
        self._prompt_loader = prompt_loader

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Build psychographic and behavioral profiles.

        input_data keys:
          - prompt (str): Original query
          - research_results (dict): Results from Phase 1 + SKL-APA-07
          - cia_context (dict): Competitor intelligence for comparison
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        research_results = input_data.get("research_results", {})
        cia_context = input_data.get("cia_context", {})

        if not research_results:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "psychographic_profiles": [],
                    "behavioral_patterns": [],
                    "message": "No research data for psychographic profiling",
                },
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "psychographic_profiles": [],
                    "behavioral_patterns": [],
                    "message": "LLM not available — psychographic profiling skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_PSYCHOGRAPHIC

                system = await self._prompt_loader.load(
                    "zorven-wf1-apa-psychographic",
                    tenant_id=context.tenant_id or None,
                    fallback=FALLBACK_PSYCHOGRAPHIC,
                )
            else:
                system = _SYSTEM_PROMPT
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            user_message = f"Analysis query: {prompt}\n\n"

            # Include demographic profiles from SKL-APA-07
            demo_data = research_results.get("SKL-APA-07", {})
            if demo_data:
                profiles = demo_data.get("demographic_profiles", [])
                if profiles:
                    user_message += (
                        f"Demographic profiles:\n" f"{json.dumps(profiles)[:5000]}\n\n"
                    )

            # Include competitor data for audience comparison
            if cia_context:
                competitors = cia_context.get("competitors", [])
                if competitors:
                    user_message += (
                        f"Competitor context:\n"
                        f"{json.dumps(competitors[:3])[:2000]}\n\n"
                    )

            # Include research context
            for skill_id, data in sorted(research_results.items()):
                if skill_id == "SKL-APA-07":
                    continue  # Already included above
                ctx = data.get("context", "")
                if ctx:
                    user_message += f"Research ({skill_id}):\n{ctx[:2500]}\n\n"

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": user_message[:30000]}],
            )

            tokens_used = _count_tokens(message)
            content = _parse_json_response(next(b.text for b in message.content if b.type == "text"))

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "psychographic_profiles": content.get("psychographic_profiles", []),
                    "behavioral_patterns": content.get("behavioral_patterns", []),
                },
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("Psychographic profiling failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return _repair_truncated_json(text)


def _repair_truncated_json(text: str) -> dict:
    """Attempt to repair truncated JSON from LLM output."""
    for cutoff in ('"}\n', '"},', '"}]', '"}'):
        idx = text.rfind(cutoff)
        if idx > 0:
            candidate = text[: idx + len(cutoff)]
            open_braces = candidate.count("{") - candidate.count("}")
            open_brackets = candidate.count("[") - candidate.count("]")
            candidate += "]" * max(open_brackets, 0)
            candidate += "}" * max(open_braces, 0)
            try:
                result = json.loads(candidate, strict=False)
                if isinstance(result, dict):
                    logger.warning(
                        "Repaired truncated JSON (%d chars trimmed)",
                        len(text) - len(candidate),
                    )
                    return result
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("Could not repair truncated JSON", text, 0)


def _count_tokens(message: Any) -> int:
    """Extract token count from Anthropic message."""
    usage = getattr(message, "usage", None)
    if usage:
        return getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
    return 0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
