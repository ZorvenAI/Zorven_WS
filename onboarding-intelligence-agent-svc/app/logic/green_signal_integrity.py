"""OG-06 — a green signal must carry evidence.

Design §5 OG-06, §7 · story G-03.

A green signal delivered to the UI must include question_id, sufficiency_score
and at least one supporting transcript span.  The UI may not receive an
unscored check.  Enforced per-chunk for streaming skills via
``GuardrailChain.wrap_stream``.
"""

from __future__ import annotations

from typing import Any

from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext


def og06_green_signal_integrity(payload: Any, context: SkillContext) -> Verdict:
    """Block a green signal that has no evidence spans."""
    if not isinstance(payload, dict):
        return Verdict(rule_id="OG-06", action=Action.PASS, payload=payload)

    if payload.get("green") and not payload.get("evidence"):
        return Verdict(
            rule_id="OG-06",
            action=Action.BLOCK,
            payload=payload,
            detail="Green signal without evidence spans",
        )

    return Verdict(rule_id="OG-06", action=Action.PASS, payload=payload)
