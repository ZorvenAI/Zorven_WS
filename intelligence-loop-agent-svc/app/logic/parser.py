"""Parse Claude JSON responses into LearningOut[] with strict validation."""

import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.api.schemas import LearningOut

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"audience", "messaging", "creative", "funnel", "competitive"}
VALID_WORKFLOWS = {"WF1", "WF2", "WF3"}
VALID_IMPACTS = {"LOW", "MEDIUM", "HIGH"}


def parse_claude_response(
    raw: dict[str, Any],
) -> tuple[str, list[LearningOut]]:
    """Return (summary, learnings) from a parsed Claude JSON dict."""
    if not isinstance(raw, dict):
        return "", []

    summary = str(raw.get("summary") or "")
    learnings: list[LearningOut] = []
    for entry in raw.get("learnings", []) or []:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category", "")).lower()
        if category not in VALID_CATEGORIES:
            continue
        impact = str(entry.get("impact", "MEDIUM")).upper()
        if impact not in VALID_IMPACTS:
            impact = "MEDIUM"
        target_workflow = str(entry.get("target_workflow", "WF3")).upper()
        if target_workflow not in VALID_WORKFLOWS:
            target_workflow = "WF3"
        try:
            confidence = int(entry.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        confidence = max(0, min(100, confidence))
        try:
            learnings.append(
                LearningOut(
                    learning_id=str(uuid.uuid4()),
                    category=category,  # type: ignore[arg-type]
                    headline=str(entry.get("headline") or "")[:500],
                    detail=entry.get("detail") or {},
                    confidence=confidence,
                    impact=impact,  # type: ignore[arg-type]
                    target_workflow=target_workflow,  # type: ignore[arg-type]
                    target_agent=str(entry.get("target_agent") or "CGA")[:16],
                )
            )
        except ValidationError as exc:
            logger.warning("Skipping invalid learning: %s", exc)
    return summary, learnings
