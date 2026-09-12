"""PG-08 — Sensitive media restriction.

Design §5.2 · implemented by story H-03, fixed by M-01.

IDENTITY or FINANCIAL captures whose text could not be fully redacted
are excluded from RAG ingestion. The guardrail sets ``rag_excluded=True``
on the skill result so the skill can propagate it to Django.
"""

from __future__ import annotations

import logging
from typing import Any

from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext

logger = logging.getLogger(__name__)


def pg08_sensitive_media(payload: Any, context: SkillContext) -> Verdict:
    """PG-08 rule body, registered on ``Layer.PROCESS``.

    Checks ``sensitivity_class`` in the payload. For IDENTITY/FINANCIAL,
    if redaction was not applied (``redaction_applied`` is False), sets
    ``rag_excluded=True``.
    """
    if not isinstance(payload, dict):
        return Verdict(rule_id="PG-08", action=Action.PASS, payload=payload)

    sensitivity = payload.get("sensitivity_class", "GENERAL")
    redaction_applied = payload.get("redaction_applied", False)

    if sensitivity in ("IDENTITY", "FINANCIAL") and not redaction_applied:
        payload["rag_excluded"] = True
        logger.info(
            "pg08_rag_excluded",
            extra={
                "sensitivity_class": sensitivity,
                "reason": "unredactable sensitive content",
            },
        )
        return Verdict(
            rule_id="PG-08",
            action=Action.DROP,
            detail=f"unredactable {sensitivity} content excluded from RAG",
            payload=payload,
        )
    return Verdict(rule_id="PG-08", action=Action.PASS, payload=payload)
