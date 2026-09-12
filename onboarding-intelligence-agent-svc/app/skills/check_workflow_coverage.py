"""SKL-OIA-09 — Report WF1, WF2 and WF3 coverage as fractions.

Design §8.1 · implemented by story G-06.

Coverage is pure arithmetic: group questions by workflow_target, count GREEN
vs total. The shared ``compute_coverage`` function does the work; the skill
wraps it in the standard SkillResult envelope so the registry, guardrails,
and RBAC all apply when invoked through the PROCESS path (J-01).

The LIVE path bypasses the skill and calls ``compute_coverage`` directly —
coverage does not depend on the LLM, so the ``circuit_breaker_dependency:
llm`` declared in skills.yaml should not prevent coverage from updating when
the LLM breaker opens.
"""

from __future__ import annotations

from app.logic.coverage import compute_coverage
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

SKILL_ID = "SKL-OIA-09"


class CheckWorkflowCoverage(BaseSkill):
    """Report WF1, WF2 and WF3 coverage as fractions."""

    async def run(self, context: SkillContext) -> SkillResult:
        question_states = context.input_context.get("question_states", [])
        threshold = context.config.get("coverage_threshold", 0.7)
        result = compute_coverage(question_states, threshold)
        return SkillResult(
            skill_id=SKILL_ID,
            output={
                "coverage": {
                    "WF1": {
                        "covered": result.wf1.covered,
                        "missing": result.wf1.missing,
                        "pct": result.wf1.pct,
                    },
                    "WF2": {
                        "covered": result.wf2.covered,
                        "missing": result.wf2.missing,
                        "pct": result.wf2.pct,
                    },
                    "WF3": {
                        "covered": result.wf3.covered,
                        "missing": result.wf3.missing,
                        "pct": result.wf3.pct,
                    },
                },
                "satisfied": result.satisfied,
                "blocking_gaps": result.blocking_gaps,
            },
        )
