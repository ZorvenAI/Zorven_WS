"""SKL-APA-09: Persona Synthesizer — Synthesize and differentiate personas."""

import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert persona synthesis analyst. Synthesize and differentiate \
buyer personas from demographic, psychographic, and behavioral data.

Rules:
- NEVER use fictional human names. Use descriptive segment labels only \
(e.g., "Enterprise Decision Maker", "Growth-Stage Startup Founder").
- When CRM data has sufficient customers (has_sufficient_data=true), use \
CRM-grounded naming based on actual customer segments.
- Each persona must be clearly differentiated from others.
- Maximum {max_personas} personas.

For each persona, produce:
- "slug": URL-safe identifier (e.g., "enterprise-decision-maker")
- "segment_label": descriptive name (no fictional names)
- "priority_score": float 0.0-1.0 (market opportunity × accessibility)
- "data_source": "crm_grounded" (if CRM data) or "research_based"
- "demographics": full demographic object from SKL-APA-07
- "psychographics": full psychographic object from SKL-APA-08
- "pain_points": list of strings
- "motivations": list of strings
- "objections": list of strings
- "preferred_channels": list of strings
- "narrative": 2-3 paragraph description
- "confidence_score": float 0.0-1.0
- "citations": list of source references

Also produce:
- "segment_matrix": object mapping dimensions to persona scores
- "differentiation_notes": how each persona differs

Respond with JSON: {{"personas": [...], "segment_matrix": {{}}, \
"differentiation_notes": str}}

Only output valid JSON, no other text."""


class PersonaSynthesizer(BaseSkill):
    """Synthesize and differentiate buyer personas using Claude."""

    meta = SkillMeta(
        skill_id="SKL-APA-09",
        name="persona_synthesizer",
        description=(
            "Synthesize and differentiate buyer personas from demographic, "
            "psychographic, and behavioral data. CRM-first naming when "
            "sufficient customer data is available."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=90000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
        max_tokens: int = 16384,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Synthesize personas from all research and analysis data.

        input_data keys:
          - prompt (str): Original query
          - research_results (dict): All results from Phase 1 + Phase 2
          - mra_context (dict): Market research context
          - cia_context (dict): Competitor intelligence context
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        research_results = input_data.get("research_results", {})
        mra_context = input_data.get("mra_context", {})
        cia_context = input_data.get("cia_context", {})

        if not research_results:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "personas": [],
                    "segment_matrix": {},
                    "message": "No data for persona synthesis",
                },
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "personas": [],
                    "segment_matrix": {},
                    "message": "LLM not available — persona synthesis skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            max_personas = min(settings.MAX_PERSONAS, settings.MAX_PERSONAS_LIMIT)
            system = _SYSTEM_PROMPT.format(max_personas=max_personas)
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            user_message = f"Analysis query: {prompt}\n\n"

            # Determine CRM data status
            crm_data = research_results.get("SKL-APA-05c", {})
            has_crm = crm_data.get("has_sufficient_data", False)
            if has_crm:
                user_message += (
                    "CRM STATUS: has_sufficient_data=true. "
                    "Use CRM-grounded naming.\n"
                    f"CRM segments:\n{json.dumps(crm_data.get('segments', []))[:3000]}\n\n"
                )
            else:
                user_message += "CRM STATUS: research_based (no CRM data).\n\n"

            # Include demographic profiles
            demo_data = research_results.get("SKL-APA-07", {})
            if demo_data:
                user_message += (
                    f"Demographics:\n"
                    f"{json.dumps(demo_data.get('demographic_profiles', []))[:5000]}\n\n"
                )

            # Include psychographic profiles
            psych_data = research_results.get("SKL-APA-08", {})
            if psych_data:
                user_message += (
                    f"Psychographics:\n"
                    f"{json.dumps(psych_data.get('psychographic_profiles', []))[:5000]}\n\n"
                )
                patterns = psych_data.get("behavioral_patterns", [])
                if patterns:
                    user_message += (
                        f"Behavioral patterns:\n" f"{json.dumps(patterns)[:2000]}\n\n"
                    )

            # Include market context
            if mra_context:
                overview = mra_context.get("market_overview", "")
                if overview:
                    user_message += f"Market context:\n{overview[:800]}\n\n"

            # Include competitor context
            if cia_context:
                competitors = cia_context.get("competitors", [])
                if competitors:
                    user_message += (
                        f"Competitors:\n" f"{json.dumps(competitors[:3])[:1500]}\n\n"
                    )

            # Include research data
            for skill_id, data in sorted(research_results.items()):
                if skill_id in {"SKL-APA-07", "SKL-APA-08", "SKL-APA-05c"}:
                    continue
                ctx = data.get("context", "")
                if ctx:
                    user_message += f"Research ({skill_id}):\n{ctx[:2000]}\n\n"

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user_message[:35000]}],
            )

            tokens_used = _count_tokens(message)
            content = _parse_json_response(message.content[0].text)

            personas = content.get("personas", [])
            # Enforce max_personas cap
            personas = personas[:max_personas]

            # Set data_source if not already set
            for persona in personas:
                if "data_source" not in persona:
                    persona["data_source"] = (
                        "crm_grounded" if has_crm else "research_based"
                    )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "personas": personas,
                    "segment_matrix": content.get("segment_matrix", {}),
                    "differentiation_notes": content.get("differentiation_notes", ""),
                },
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("Persona synthesis failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks and truncation."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt to repair truncated JSON by closing open structures
        return _repair_truncated_json(text)


def _repair_truncated_json(text: str) -> dict:
    """Attempt to repair truncated JSON from LLM output.

    Tries progressively shorter substrings and closes open brackets/braces.
    """
    # Try to find the last valid array element boundary
    for cutoff in ('"}\n', '"},', '"}]', '"}'):
        idx = text.rfind(cutoff)
        if idx > 0:
            candidate = text[: idx + len(cutoff)]
            # Close any open structures
            open_braces = candidate.count("{") - candidate.count("}")
            open_brackets = candidate.count("[") - candidate.count("]")
            candidate += "]" * max(open_brackets, 0)
            candidate += "}" * max(open_braces, 0)
            try:
                result = json.loads(candidate)
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
