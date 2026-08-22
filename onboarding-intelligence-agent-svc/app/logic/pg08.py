"""PG-08 — Sensitive media restriction.

Design §5.2 · implemented by story H-03.

IDENTITY or FINANCIAL captures whose text could not be fully redacted
are excluded from RAG ingestion. The guardrail sets ``rag_excluded=True``
on the skill result so the skill can propagate it to Django.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def pg08_sensitive_media(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    """PG-08 rule body, registered on ``Layer.PROCESS``.

    Checks ``sensitivity_class`` in the payload. For IDENTITY/FINANCIAL,
    if redaction was not applied (``redaction_applied`` is False), sets
    ``rag_excluded=True``.
    """
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
    return payload
