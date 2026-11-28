"""Signed meeting records · step 2 — the PDF.

Read back with pypdf: the record PDFs embed a Unicode font, so their text is
stored as glyph ids and the stream-inflating helper used for the older
onboarding PDF would find nothing.

No database. ``build_record_pdf`` is a pure function of the view it is given,
which is what these tests rely on.
"""

from __future__ import annotations

import copy
import io

import pytest
from pypdf import PdfReader

from apps.onboarding.records.pdf import (
    WATERMARK_DRAFT,
    WATERMARK_UNSIGNED,
    WATERMARK_VOID,
    AuditEntry,
    RecordView,
    SignatureBlock,
    build_binder_pdf,
    build_record_pdf,
    format_duration,
    format_time,
    unsupported_characters,
)

HASH = "9f2c" * 16

SNAPSHOT = {
    "schema": 1,
    "record": {"number": "MR-000085-v1", "version": 1, "supersedes": None},
    "clause": {
        "version": "2026-11-draft-1",
        "text": "This document records a meeting.\n\nThe audio recording prevails.",
    },
    "parties": {
        "agency": {"name": "Zorven Agency"},
        "client": {
            "name": "Pomodoro",
            "legal_name": "Pomodoro Trattoria LLC",
            "registered_address": "14 Main Street, Austin",
            "signatory_name": "Maria Rossi",
            "signatory_title": "Owner",
            "signatory_email": "maria@example.com",
            "registration_number": "",
        },
    },
    "meeting": {
        "session_id": 6,
        "recording_id": 85,
        "started_at": "2026-11-23T19:31:00+00:00",
        "stopped_at": "2026-11-23T20:01:10+00:00",
        "duration_s": 1810,
        "modality": "IN_PERSON",
    },
    "attendees": [
        {"name": "Naveen", "role": "operator"},
        {"name": "Maria Rossi", "role": "participant"},
    ],
    "consent": {
        "subject_name": "Maria Rossi",
        "method": "VERBAL_RECORDED",
        "granted_at": "2026-11-23T19:30:00+00:00",
        "revoked_at": None,
    },
    "completeness": {"state": "complete", "missing_s": 0, "note": ""},
    "agreements": {
        "preamble": "",
        "items": [
            {"number": "A-1", "text": "**Budget split** evenly — ₹50,000 each."},
            {"number": "A-2", "text": "Contract review before launch."},
        ],
    },
    "description": (
        "## Business Identity\nPomodoro is a **family** restaurant.\n- Dine-in"
    ),
    "transcript": ["Naveen: Shall we split the budget?", "Maria Rossi: Yes, agreed."],
}


def view(status="ISSUED", **overrides) -> RecordView:
    values = {
        "snapshot": copy.deepcopy(SNAPSHOT),
        "status": status,
        "content_hash": HASH if status != "DRAFT" else "",
        "issued_at": "2026-11-25T10:00:00+00:00" if status != "DRAFT" else "",
        "signatures": (
            SignatureBlock("Zorven Agency", "Naveen", "", "naveen@example.com"),
            SignatureBlock(
                "Pomodoro Trattoria LLC", "Maria Rossi", "Owner", "maria@example.com"
            ),
        ),
        "audit": (
            AuditEntry("2026-11-25T09:00:00+00:00", "Draft prepared", "Naveen"),
            AuditEntry("2026-11-25T10:00:00+00:00", "Issued", "Naveen"),
        ),
    }
    values.update(overrides)
    return RecordView(**values)


def text_of(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() for page in reader.pages)
    # A text extraction that finds nothing is a broken test, not a clean
    # result: every "must not appear" assertion would pass against it.
    assert "Meeting Record" in text, "no text was extracted from the PDF"
    return text


def pages_of(data: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]


# ── What a record prints ─────────────────────────────────────────────


@pytest.mark.unit
def test_it_is_a_pdf():
    assert build_record_pdf(view()).startswith(b"%PDF-")


@pytest.mark.unit
def test_the_cover_names_both_parties_the_meeting_and_the_fingerprint():
    text = text_of(build_record_pdf(view()))

    assert "MR-000085-v1" in text
    assert "Zorven Agency" in text
    assert "Pomodoro Trattoria LLC" in text
    assert "14 Main Street, Austin" in text
    assert "23 Nov 2026, 19:31 UTC" in text
    assert "23 Nov 2026, 20:01 UTC" in text
    assert "30m 10s" in text
    assert HASH in text.replace("\n", "")


@pytest.mark.unit
def test_every_agreement_is_printed_with_its_number():
    text = text_of(build_record_pdf(view()))

    assert "A-1" in text and "A-2" in text
    assert "Budget split evenly — ₹50,000 each." in text
    assert "Contract review before launch." in text


@pytest.mark.unit
def test_bold_markers_are_rendered_not_printed():
    text = text_of(build_record_pdf(view()))

    assert "**" not in text
    assert "Pomodoro is a family restaurant." in text


@pytest.mark.unit
def test_italic_markers_are_rendered_not_printed():
    """The description marks its source notes in italics, on nearly every
    line. Printed raw, a record is littered with asterisks."""
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["description"] = "- **Industry**: Dining *(Client, approx. mid-call)*"

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert "Industry: Dining (Client, approx. mid-call)" in text
    assert "*" not in text[text.index("4. Description") : text.index("Signatures")]


@pytest.mark.unit
@pytest.mark.parametrize(
    "line",
    ["Budget is 5 * 3 * 2 thousand.", "Rated 4* by guests and 5* by critics."],
)
def test_an_asterisk_that_is_not_markup_is_printed_as_written(line):
    """Never drop a character from a signed text because it looked like
    formatting."""
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["transcript"] = [f"Maria Rossi: {line}"]

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert f"Maria Rossi: {line}" in text


@pytest.mark.unit
def test_a_meeting_with_no_agreements_says_so():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["agreements"]["items"] = []

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert "No agreements were recorded in this meeting." in text
    assert "A-1" not in text


@pytest.mark.unit
def test_the_legal_status_clause_is_printed_with_its_version():
    text = text_of(build_record_pdf(view()))

    assert "This document records a meeting." in text
    assert "The audio recording prevails." in text
    assert "Clause version 2026-11-draft-1." in text


@pytest.mark.unit
def test_attendance_and_consent_are_printed():
    text = text_of(build_record_pdf(view()))

    assert "Naveen — Zorven Agency" in text
    assert "Maria Rossi — Pomodoro" in text
    assert "Consent to be recorded was given by Maria Rossi" in text
    assert "23 Nov 2026, 19:30 UTC" in text


@pytest.mark.unit
def test_missing_consent_is_stated_rather_than_left_out():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["consent"] = None

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert "No recording consent is on file for this session." in text


@pytest.mark.unit
def test_transcript_lines_are_numbered_in_order():
    text = text_of(build_record_pdf(view()))
    annex = text[text.index("Annex A") :]

    first = annex.index("Naveen: Shall we split the budget?")
    second = annex.index("Maria Rossi: Yes, agreed.")
    assert first < second
    assert annex.index("1\n") < first or "1 Naveen" in annex.replace("\n", " ")


@pytest.mark.unit
def test_each_party_has_a_signature_block():
    text = text_of(build_record_pdf(view()))

    assert "For Zorven Agency" in text
    assert "For Pomodoro Trattoria LLC" in text
    assert "maria@example.com" in text
    assert text.count("Not signed") == 2


@pytest.mark.unit
def test_the_certificate_lists_the_audit_trail():
    text = text_of(build_record_pdf(view()))
    certificate = text[text.rindex("Certificate") :]

    assert "25 Nov 2026, 09:00 UTC" in certificate
    assert "Draft prepared — Naveen" in certificate
    assert "Issued — Naveen" in certificate


# ── Completeness ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_a_complete_transcript_carries_no_completeness_notice():
    assert "Completeness notice" not in text_of(build_record_pdf(view()))


@pytest.mark.unit
def test_a_gap_in_the_transcript_is_stated_with_its_length():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["completeness"] = {
        "state": "partial",
        "missing_s": 267,
        "note": "Live transcription stopped before the recording ended.",
    }

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert "Completeness notice" in text
    assert "Live transcription stopped before the recording ended." in text
    assert "Approximately 4m 27s is not covered." in text


# ── Watermarks ───────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "status, watermark",
    [
        ("DRAFT", WATERMARK_DRAFT),
        ("ISSUED", WATERMARK_UNSIGNED),
        ("PARTIALLY_SIGNED", WATERMARK_UNSIGNED),
        ("VOIDED", WATERMARK_VOID),
    ],
)
def test_an_unfinished_record_is_watermarked_on_every_page(status, watermark):
    """A copy that leaves the building must not pass for a signed record."""
    pages = pages_of(build_record_pdf(view(status=status)))

    assert len(pages) >= 3
    assert all(watermark in page for page in pages)


@pytest.mark.unit
def test_a_completed_record_carries_no_watermark():
    text = text_of(build_record_pdf(view(status="COMPLETED")))

    assert WATERMARK_UNSIGNED not in text
    assert WATERMARK_DRAFT not in text


@pytest.mark.unit
def test_a_draft_says_it_has_not_been_issued():
    text = text_of(build_record_pdf(view(status="DRAFT")))

    assert "Not issued" in text
    assert HASH not in text.replace("\n", "")


# ── Reproducibility ──────────────────────────────────────────────────


@pytest.mark.unit
def test_the_same_record_renders_to_the_same_bytes():
    """So a downloaded copy can be compared with one downloaded later."""
    assert build_record_pdf(view()) == build_record_pdf(view())


@pytest.mark.unit
def test_a_different_transcript_renders_to_different_bytes():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["transcript"][1] = "Maria Rossi: No, not agreed."

    assert build_record_pdf(view(snapshot=snapshot)) != build_record_pdf(view())


@pytest.mark.unit
def test_a_long_transcript_spans_pages_and_keeps_every_line():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["transcript"] = [
        f"Speaker {i % 2}: statement number {i} in a long meeting." for i in range(300)
    ]

    data = build_record_pdf(view(snapshot=snapshot))
    text = text_of(data)

    assert len(pages_of(data)) > 5
    assert "statement number 0 in a long meeting." in text
    assert "statement number 299 in a long meeting." in text


@pytest.mark.unit
def test_an_unbroken_run_of_characters_does_not_break_the_layout():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["transcript"] = ["Maria Rossi: " + "x" * 400]

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert text.replace("\n", "").count("x" * 100) >= 1


# ── Characters ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_everyday_punctuation_and_currency_are_supported():
    assert unsupported_characters("Hello — “quoted” ₹50,000 €600 £5 café naïve") == []


@pytest.mark.unit
def test_scripts_the_font_cannot_draw_are_reported_once_each_in_order():
    assert unsupported_characters("ಕನ್ನಡ and 日本 and 日本") == [
        "ಕ",
        "ನ",
        "್",
        "ಡ",
        "日",
        "本",
    ]


@pytest.mark.unit
def test_layout_whitespace_is_not_reported():
    assert unsupported_characters("line one\n\tline two\r\n") == []


@pytest.mark.unit
def test_non_latin_text_the_font_supports_reaches_the_pdf_unchanged():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["transcript"] = ["Maria Rossi: Договорились — ₹50,000, Ελλάδα"]

    text = text_of(build_record_pdf(view(snapshot=snapshot)))

    assert "Договорились — ₹50,000, Ελλάδα" in text
    assert "?" not in text[text.index("Annex A") :].split("Certificate")[0]


# ── Formatting ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_times_are_always_shown_in_utc():
    """One record read in two time zones must show one time."""
    assert format_time("2026-11-23T14:31:00-05:00") == "23 Nov 2026, 19:31 UTC"
    assert format_time("2026-11-23T19:31:00") == "23 Nov 2026, 19:31 UTC"
    assert format_time(None) == "—"


@pytest.mark.unit
@pytest.mark.parametrize(
    "seconds, shown",
    [(None, "—"), (0, "—"), (59, "0m 59s"), (1810, "30m 10s"), (3725, "1h 02m")],
)
def test_durations(seconds, shown):
    assert format_duration(seconds) == shown


# ── The binder ───────────────────────────────────────────────────────


def second_meeting(status="DRAFT") -> RecordView:
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["record"]["number"] = "MR-000091-v1"
    snapshot["meeting"]["started_at"] = "2026-12-02T15:00:00+00:00"
    snapshot["agreements"]["items"] = [
        {"number": "A-1", "text": "Photo shoot booked for January."}
    ]
    snapshot["transcript"] = ["Naveen: Second meeting line."]
    return view(status=status, snapshot=snapshot)


@pytest.mark.unit
def test_the_binder_indexes_every_meeting_with_its_status():
    text = text_of(
        build_binder_pdf(
            [view(), second_meeting()],
            agency_name="Zorven Agency",
            client_name="Pomodoro",
        )
    )
    index = text[text.index("Index") : text.index("Record number")]

    assert "MR-000085-v1" in index and "Issued" in index
    assert "MR-000091-v1" in index and "Draft" in index
    assert index.index("MR-000085-v1") < index.index("MR-000091-v1")


@pytest.mark.unit
def test_the_binder_carries_each_meetings_own_content_and_signatures():
    text = text_of(
        build_binder_pdf(
            [view(), second_meeting()],
            agency_name="Zorven Agency",
            client_name="Pomodoro",
        )
    )

    assert "Budget split evenly — ₹50,000 each." in text
    assert "Photo shoot booked for January." in text
    assert "Naveen: Second meeting line." in text
    assert text.count("For Pomodoro Trattoria LLC") == 2


@pytest.mark.unit
def test_each_record_in_a_binder_keeps_its_own_watermark():
    pages = pages_of(
        build_binder_pdf(
            [view(), second_meeting()],
            agency_name="Zorven Agency",
            client_name="Pomodoro",
        )
    )

    assert WATERMARK_UNSIGNED not in pages[0] and WATERMARK_DRAFT not in pages[0]
    assert any(WATERMARK_UNSIGNED in page for page in pages)
    assert any(WATERMARK_DRAFT in page for page in pages)
    # No page claims both states.
    assert not any(WATERMARK_UNSIGNED in p and WATERMARK_DRAFT in p for p in pages)


@pytest.mark.unit
def test_the_manifest_lists_each_fingerprint_and_marks_the_unissued():
    text = text_of(
        build_binder_pdf(
            [view(), second_meeting()],
            agency_name="Zorven Agency",
            client_name="Pomodoro",
        )
    )
    manifest = text[text.rindex("Manifest") :].replace("\n", "")

    assert HASH in manifest
    assert "MR-000091-v1Notissued" in manifest.replace(" ", "")


@pytest.mark.unit
def test_adding_a_meeting_does_not_change_an_earlier_records_pages():
    """The request was one document that grows. What must not happen is the
    growth altering what was already there."""
    alone = pages_of(
        build_binder_pdf([view()], agency_name="Zorven Agency", client_name="Pomodoro")
    )
    grown = pages_of(
        build_binder_pdf(
            [view(), second_meeting()],
            agency_name="Zorven Agency",
            client_name="Pomodoro",
        )
    )

    def record_pages(pages):
        # The first record's own pages: from its cover to its certificate.
        start = next(i for i, p in enumerate(pages) if "Record number" in p)
        end = next(i for i, p in enumerate(pages) if "Audit trail" in p)
        return [
            # Page numbers legitimately change when a binder grows.
            "\n".join(line for line in p.splitlines() if not line.startswith("Page "))
            for p in pages[start : end + 1]
        ]

    assert record_pages(grown) == record_pages(alone)


@pytest.mark.unit
def test_an_empty_binder_says_there_is_nothing_in_it():
    text = text_of(
        build_binder_pdf([], agency_name="Zorven Agency", client_name="Pomodoro")
    )

    assert "No meeting records have been prepared for this session." in text
