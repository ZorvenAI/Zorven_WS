"""Confidence scoring + contradiction detection for ILA learnings."""

from typing import Any

from app.api.schemas import LearningOut

# Brand profile fields that, if non-empty, are considered established strategy
# and may contradict an ILA-proposed re-positioning.
_BRAND_STRATEGY_FIELDS = (
    "positioning_statement",
    "value_proposition",
    "vision_statement",
    "mission_statement",
    "brand_voice",
)


def adjust_confidence(
    learning: LearningOut, context: dict[str, Any]
) -> LearningOut:
    """Boost/reduce confidence based on context signals.

    Heuristics (Phase 3, intentionally simple):
    - +10 if there are >= 5 recent recommendations (rich evidence)
    - -5 if the campaign is not currently ``active`` or ``completed``
      (e.g. ``paused`` / ``draft``) — treated as a stale-context penalty
    - cap at [0, 100]
    """
    delta = 0
    recs = context.get("recommendations") or []
    if len(recs) >= 5:
        delta += 10
    campaign = context.get("campaign") or {}
    if campaign.get("status") not in {"active", "completed"}:
        delta -= 5

    new_conf = max(0, min(100, learning.confidence + delta))
    if new_conf == learning.confidence:
        return learning
    return learning.model_copy(update={"confidence": new_conf})


def detect_contradictions(
    learnings: list[LearningOut], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Flag learnings that conflict with established brand strategy.

    A WF2-targeted learning is flagged as a contradiction when the
    company's corresponding strategy field is already populated. This
    is what forces WF2 re-runs through human approval.
    """
    company = context.get("company") or {}
    has_strategy = any(
        bool(company.get(field)) for field in _BRAND_STRATEGY_FIELDS
    )
    contradictions: list[dict[str, Any]] = []
    if not has_strategy:
        return contradictions
    for learning in learnings:
        if learning.target_workflow == "WF2":
            contradictions.append(
                {
                    "learning_id": learning.learning_id,
                    "category": learning.category,
                    "reason": (
                        "WF2-targeted learning conflicts with established "
                        "brand strategy fields; requires human approval."
                    ),
                }
            )
    return contradictions
