"""SKL-APA-07: Demographic Profile Builder — Claude analysis of demographics."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a demographic research analyst. Build structured demographic profiles \
from the provided research data.

For each identified audience segment, produce:
- "segment_label": descriptive label (NEVER fictional human names)
- "age_range": e.g., "25-45"
- "gender_distribution": e.g., {"male": 55, "female": 40, "non_binary": 5}
- "income_range": e.g., "$75,000-$150,000"
- "education_level": e.g., "Bachelor's degree or higher"
- "job_titles": list of common titles
- "company_size": e.g., "50-500 employees"
- "industry_verticals": list of industries
- "geographic_distribution": e.g., {"North America": 60, "Europe": 25}
- "confidence_score": float 0.0-1.0

Every claim MUST cite evidence from the research data. Do not speculate without data.

Respond with JSON: {"demographic_profiles": [...], "confidence_score": 0.8}

Only output valid JSON, no other text."""


class DemographicProfileBuilder(BaseSkill):
    """Build demographic profiles from research data using Claude."""

    meta = SkillMeta(
        skill_id="SKL-APA-07",
        name="demographic_profile_builder",
        description=(
            "Build structured demographic profiles (age, gender, income, "
            "education, location, job titles, company size) from research data "
            "using Claude Sonnet 4."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-5",
        max_tokens: int = 32768,
        prompt_loader: Any = None,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.max_tokens = max_tokens
        self._prompt_loader = prompt_loader

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Build demographic profiles.

        input_data keys:
          - prompt (str): Original query
          - research_results (dict): Results from Phase 1 research skills
          - mra_context (dict): MRA market context for enrichment
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        research_results = input_data.get("research_results", {})
        mra_context = input_data.get("mra_context", {})

        if not research_results:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "demographic_profiles": [],
                    "message": "No research data for demographic profiling",
                },
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "demographic_profiles": [],
                    "message": "LLM not available — demographic profiling skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_DEMOGRAPHIC

                system = await self._prompt_loader.load(
                    "zorven-wf1-apa-demographic",
                    tenant_id=context.tenant_id or None,
                    fallback=FALLBACK_DEMOGRAPHIC,
                )
            else:
                system = _SYSTEM_PROMPT
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            # Compile research data
            user_message = f"Analysis query: {prompt}\n\n"
            if mra_context:
                overview = mra_context.get("market_overview", "")
                if overview:
                    user_message += f"Market context:\n{overview[:800]}\n\n"

            # Include CRM segments if available
            crm_data = research_results.get("SKL-APA-05c", {})
            if crm_data and crm_data.get("has_sufficient_data"):
                user_message += (
                    f"CRM Customer Data:\n"
                    f"{json.dumps(crm_data.get('segments', []))[:3000]}\n\n"
                )

            # Include research context
            for skill_id, data in sorted(research_results.items()):
                ctx = data.get("context", "")
                if ctx:
                    user_message += f"Research ({skill_id}):\n{ctx[:3000]}\n\n"

            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": user_message[:30000]}],
            ) as _stream:
                message = await _stream.get_final_message()

            tokens_used = _count_tokens(message)
            content = _parse_json_response(next(b.text for b in message.content if b.type == "text"))

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "demographic_profiles": content.get("demographic_profiles", []),
                    "confidence_score": content.get("confidence_score", 0.0),
                },
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("Demographic profiling failed: %s", exc)
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
