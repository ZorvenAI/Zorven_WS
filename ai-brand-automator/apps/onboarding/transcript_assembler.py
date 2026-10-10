"""Legal transcript header assembly (O-06).

Assembles a structured header from automatically captured metadata —
attendees (O-05), consent (ConsentRecord), date/time (recording.started_at) —
and resolves speaker indices to names in transcript segments.

Every field is auto-populated; AC-5 requires no manual entry.
"""

from __future__ import annotations

from typing import Any


def build_speaker_map(attendees: list[dict[str, Any]]) -> dict[int, str]:
    """Map stream_index → speaker name from attendee records."""
    return {a["stream_index"]: a["name"] for a in attendees if a.get("name")}


def resolve_speaker_name(
    speaker: int,
    speaker_map: dict[int, str],
) -> str | None:
    return speaker_map.get(speaker)


def assemble_header(
    *,
    recording: Any,
    attendees: list[dict[str, Any]],
    consent: dict[str, Any] | None,
    session_company: str | None = None,
) -> dict[str, Any]:
    """Build the legal transcript header dict (AC-1 through AC-5).

    Returns a dict suitable for JSON storage and plain-text rendering.
    """
    started = recording.started_at
    stopped = getattr(recording, "stopped_at", None)

    header: dict[str, Any] = {
        "date": started.strftime("%Y-%m-%d") if started else None,
        "time_utc": started.strftime("%H:%M UTC") if started else None,
        "started_at_iso": started.isoformat() if started else None,
        "stopped_at_iso": stopped.isoformat() if stopped else None,
        "session_id": str(recording.session_id),
        "session_company": session_company,
        "attendees": [
            {
                "name": a.get("name", ""),
                "role": a.get("role", ""),
                "mic_label": a.get("mic_label", ""),
                "stream_index": a.get("stream_index"),
                "checked_in_at": a.get("checked_in_at"),
            }
            for a in attendees
        ],
    }

    if consent:
        header["consent"] = {
            "subject_name": consent.get("subject_name", ""),
            "method": consent.get("method", ""),
            "granted_at": consent.get("granted_at"),
            "scope": consent.get("scope", {}),
        }
    else:
        header["consent"] = None

    header["transcript_completeness"] = _completeness(recording)

    return header


def _completeness(recording: Any) -> dict[str, Any]:
    """State whether the transcript covers the whole recording (#662).

    A legal header that says nothing about coverage is read as a claim of
    completeness, which is how #662 came about: a socket drop truncated the
    transcript and the recording still finalised SUMMARIZED with
    ``has_transcript: true``.

    Three states, not two. ``unknown`` is for rows finalised before this was
    detectable — asserting those are complete would invent a fact about
    recordings nobody measured, and asserting they are partial would smear
    every honest one.
    """
    complete = getattr(recording, "transcript_complete", None)
    missing = getattr(recording, "transcript_missing_s", None)

    if complete is None:
        return {
            "state": "unknown",
            "missing_s": None,
            "note": (
                "Transcript coverage was not assessed for this recording. It "
                "may be complete or may be missing audio that was not "
                "transcribed."
            ),
        }
    if complete:
        return {"state": "complete", "missing_s": 0, "note": ""}
    return {
        "state": "partial",
        "missing_s": missing,
        "note": (
            "Live transcription stopped before the recording ended, so this "
            "transcript does not cover the whole meeting. The audio itself is "
            "intact and can be re-transcribed."
        ),
    }


def enrich_segments(
    segments: list[dict[str, Any]],
    speaker_map: dict[int, str],
) -> list[dict[str, Any]]:
    """Add speaker_name to each transcript segment (AC-4).

    The name stored on the segment wins over the live attendee row (O-08).
    ``speaker_map`` is rebuilt from ``MeetingAttendee`` on every read, so
    preferring it meant editing an attendee after the meeting retroactively
    changed what the legal transcript said had been spoken — and left the
    persisted name, which O-08 exists to capture, used only when the attendee
    row had been deleted.

    This is the same rule O-07 applies to ``stream_assets``: what the archive
    claims about who was recorded must be what was true when the recording
    stopped. The map remains the fallback, which is what keeps pre-O-08
    recordings — persisted with no name at all — rendering correctly.
    """
    enriched = []
    for seg in segments:
        entry = dict(seg)
        stored = entry.get("speaker_name")
        if isinstance(stored, str) and stored.strip():
            enriched.append(entry)
            continue
        speaker = seg.get("speaker")
        if speaker is not None and speaker in speaker_map:
            entry["speaker_name"] = speaker_map[speaker]
        else:
            entry["speaker_name"] = None
        enriched.append(entry)
    return enriched


def render_plain_text(
    header: dict[str, Any],
    segments: list[dict[str, Any]],
) -> str:
    """Render the full legal transcript as plain text."""
    lines: list[str] = []

    lines.append("MEETING TRANSCRIPT")
    lines.append("─" * 18)

    if header.get("date"):
        lines.append(f"Date:       {header['date']}")
    if header.get("time_utc"):
        lines.append(f"Time:       {header['time_utc']}")
    company = header.get("session_company") or ""
    session_id = header.get("session_id", "")
    if company:
        lines.append(f"Session:    #{session_id} — {company}")
    else:
        lines.append(f"Session:    #{session_id}")

    attendees = header.get("attendees", [])
    if attendees:
        lines.append("")
        lines.append("ATTENDEES")
        lines.append("─" * 9)
        for i, a in enumerate(attendees, 1):
            role = f" ({a['role'].title()})" if a.get("role") else ""
            mic = f" — Mic: {a['mic_label']}" if a.get("mic_label") else ""
            lines.append(f"{i}. {a.get('name', 'Unknown')}{role}{mic}")
            if a.get("checked_in_at"):
                lines.append(f"   Checked in: {a['checked_in_at']}")

    consent = header.get("consent")
    if consent:
        lines.append("")
        lines.append("CONSENT")
        lines.append("─" * 7)
        if consent.get("subject_name"):
            lines.append(f"Subject: {consent['subject_name']}")
        if consent.get("method"):
            method_display = consent["method"].replace("_", " ").title()
            lines.append(f"Method:  {method_display}")
        if consent.get("granted_at"):
            lines.append(f"Granted: {consent['granted_at']}")
        scope = consent.get("scope", {})
        if scope:
            scope_items = ", ".join(
                k.replace("_", " ").title() for k, v in scope.items() if v
            )
            if scope_items:
                lines.append(f"Scope:   {scope_items}")

    if segments:
        lines.append("")
        lines.append("TRANSCRIPT")
        lines.append("─" * 10)
        for seg in segments:
            t = seg.get("t_start", 0)
            minutes = int(t // 60)
            seconds = int(t % 60)
            timestamp = f"{minutes:02d}:{seconds:02d}"
            name = seg.get("speaker_name") or f"Speaker {seg.get('speaker', 0) + 1}"
            text = seg.get("text", "")
            lines.append(f"[{timestamp}] {name}: {text}")

    return "\n".join(lines)
