"""SKL-APA-10: Buying Journey Mapper — Per-persona buying journey stages."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a buying journey analysis expert. Map the buying journey for each \
persona through 6 stages.

Default stages: Awareness → Consideration → Evaluation → Decision → \
Onboarding → Advocacy

For each persona's journey map, produce:
- "persona_slug": matching the persona slug
- "persona_label": matching the segment label
- "total_estimated_cycle_days": integer
- "stages": list of stage objects

Each stage object:
- "name": stage name (e.g., "Awareness")
- "description": what happens in this stage
- "touchpoints": list of channels/interactions
- "info_needs": what information they seek
- "emotional_state": e.g., "curious", "anxious", "excited"
- "decision_criteria": what they evaluate
- "objections": common blockers at this stage
- "content_recommendations": list of content types that help
- "estimated_days": integer for this stage
- "key_actions": list of actions the brand should take

Also produce:
- "total_estimated_cycle_days": overall journey duration estimate

Every claim should be grounded in research data. Do not speculate without evidence.

Respond with JSON: {{"journey_maps": [...], "total_estimated_cycle_days": int}}

Only output valid JSON, no other text."""


class BuyingJourneyMapper(BaseSkill):
    """Map buying journey per persona using Claude."""

    meta = SkillMeta(
        skill_id="SKL-APA-10",
        name="buying_journey_mapper",
        description=(
            "Map 6-stage buying journey per persona: Awareness, Consideration, "
            "Evaluation, Decision, Onboarding, Advocacy. Includes touchpoints, "
            "emotional states, and content recommendations."
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
        Map buying journey for each persona.

        input_data keys:
          - prompt (str): Original query
          - research_results (dict): All results including personas from SKL-APA-09
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        research_results = input_data.get("research_results", {})

        # Get personas from SKL-APA-09
        synthesizer_data = research_results.get("SKL-APA-09", {})
        personas = synthesizer_data.get("personas", [])

        if not personas:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "journey_maps": [],
                    "total_estimated_cycle_days": 0,
                    "message": "No personas for journey mapping",
                },
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "journey_maps": [],
                    "total_estimated_cycle_days": 0,
                    "message": "LLM not available — journey mapping skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_JOURNEY

                system = await self._prompt_loader.load(
                    "zorven-wf1-apa-journey",
                    tenant_id=context.tenant_id or None,
                    fallback=FALLBACK_JOURNEY,
                )
            else:
                system = _SYSTEM_PROMPT
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            user_message = f"Analysis query: {prompt}\n\n"

            # Include persona data
            user_message += f"Personas to map:\n{json.dumps(personas)[:10000]}\n\n"

            # Include buyer role data
            buyer_data = research_results.get("SKL-APA-04", {})
            if buyer_data:
                roles = buyer_data.get("buyer_roles", [])
                if roles:
                    user_message += f"Buyer roles:\n{json.dumps(roles)[:2000]}\n\n"

            # Include review/needs data
            review_data = research_results.get("SKL-APA-05", {})
            if review_data:
                needs = review_data.get("needs", [])
                objections = review_data.get("objections", [])
                if needs:
                    user_message += f"Customer needs:\n{json.dumps(needs)[:1500]}\n\n"
                if objections:
                    user_message += f"Objections:\n{json.dumps(objections)[:1500]}\n\n"

            # Include social listening data
            social_data = research_results.get("SKL-APA-03", {})
            if social_data:
                behaviors = social_data.get("platform_behaviors", [])
                if behaviors:
                    user_message += (
                        f"Platform behaviors:\n{json.dumps(behaviors)[:1500]}\n\n"
                    )

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
                    "journey_maps": content.get("journey_maps", []),
                    "total_estimated_cycle_days": content.get(
                        "total_estimated_cycle_days", 0
                    ),
                },
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("Journey mapping failed: %s", exc)
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
        return json.loads(text)
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
