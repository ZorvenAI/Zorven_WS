"""The legal status clause printed on every meeting record.

Versioned, and the version is stored on each record together with the text
itself inside the frozen snapshot. Changing the wording here therefore never
changes a record that has already been issued: it carries the words it was
issued with.

**This wording is a draft and has not had legal review.** It states what the
record is and is not, and the order of precedence between the audio and the
texts derived from it. A lawyer must review it before signing is enabled in
production; when they do, add a new version rather than editing this one.
"""

from __future__ import annotations

CLAUSE_VERSION = "2026-11-draft-1"

_CLAUSES: dict[str, str] = {
    "2026-11-draft-1": (
        "This document records a meeting between the parties named above. By "
        "signing, each party confirms that the numbered Agreements accurately "
        "state what the parties agreed in this meeting.\n\n"
        "The Description is a summary prepared with automated tools, and the "
        "Transcript is an automated transcription of the recording. They are "
        "included as a supporting record and may contain errors. If they "
        "differ, the audio recording prevails, then the raw transcript, then "
        "the clean transcript, then the Description.\n\n"
        "This document does not replace any signed services agreement between "
        "the parties. Where this document and a signed services agreement "
        "conflict, the signed services agreement prevails."
    ),
}


def clause_text(version: str = CLAUSE_VERSION) -> str:
    """The clause for a version. Raises ``KeyError`` for an unknown one —
    a record must never be issued with wording nobody wrote."""
    return _CLAUSES[version]
