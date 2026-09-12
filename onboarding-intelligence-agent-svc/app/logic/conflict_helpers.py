"""Shared conflict helpers used by both ProcessExecutor and SKL-OIA-14.

Extracted to avoid duplicated logic with divergent error handling (J-05
review finding).
"""

from __future__ import annotations

from typing import Any

from app.messaging.schemas import ConflictCandidate


def format_evidence_ref(span: dict[str, Any]) -> str:
    """Format an evidence span as a reference pointer, never including text."""
    rec_id = span.get("recording_id")
    med_id = span.get("media_id")
    if rec_id:
        t_start = span.get("t_start", "")
        t_end = span.get("t_end", "")
        return f"recording:{rec_id}:{t_start}-{t_end}"
    if med_id:
        return f"media:{med_id}"
    return "unknown"


def build_candidates(conflict: dict[str, Any]) -> list[ConflictCandidate]:
    """Build ConflictCandidate list from an enriched conflict dict."""
    candidates: list[ConflictCandidate] = []

    existing_span = conflict.get("existing_source_span")
    field_name = conflict.get("field_name", "unknown")
    if existing_span:
        ref = format_evidence_ref(existing_span)
    else:
        ref = f"provenance:{field_name}"
    candidates.append(
        ConflictCandidate(
            source="existing",
            evidence_ref=ref,
            confidence=conflict.get("existing_confidence"),
        )
    )

    new_evidence = conflict.get("new_evidence", [])
    new_ref = (
        format_evidence_ref(new_evidence[0])
        if new_evidence
        else f"extraction:{field_name}"
    )
    candidates.append(
        ConflictCandidate(
            source="new",
            evidence_ref=new_ref,
            confidence=conflict.get("new_confidence"),
            classification=conflict.get("new_classification"),
        )
    )

    return candidates
