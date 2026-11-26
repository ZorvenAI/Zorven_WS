"""Render a meeting record, or a session's binder of them, as a PDF.

Pure functions of their inputs: no database, no storage, no clock. Everything
printed comes from the snapshot and the ``RecordView`` passed in, which is
what makes the output testable and reproducible.

**Characters are never substituted.** The existing onboarding PDF replaces
anything outside Latin-1 with ``?``; on a signed record that would silently
change a name or a figure. So this uses a bundled Unicode font, and
``unsupported_characters`` reports anything the font still cannot draw so a
record containing it is not issued in a misleading form.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont
from fpdf import FPDF

# Embedding a font subset makes fontTools narrate every table it prunes at
# INFO — about a hundred lines per PDF. Nothing in it is about the record.
logging.getLogger("fontTools").setLevel(logging.WARNING)

FONT_DIR = Path(__file__).parent / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_ITALIC = FONT_DIR / "DejaVuSans-Oblique.ttf"
FAMILY = "DejaVu"

WATERMARK_DRAFT = "DRAFT — NOT ISSUED"
WATERMARK_UNSIGNED = "NOT FULLY SIGNED"
WATERMARK_VOID = "VOID"

#: ``**bold**`` and ``*italic*`` runs. The italic form must hug its text on
#: both sides, so a bare asterisk in a sum such as ``5 * 3 * 2`` is printed as
#: an asterisk and not consumed as markup.
_EMPHASIS = re.compile(r"(\*\*.+?\*\*|\*(?=\S)[^*\n]*?(?<=\S)\*)")
_WATERMARKS = {
    "DRAFT": WATERMARK_DRAFT,
    "ISSUED": WATERMARK_UNSIGNED,
    "PARTIALLY_SIGNED": WATERMARK_UNSIGNED,
    "VOIDED": WATERMARK_VOID,
    "DECLINED": WATERMARK_VOID,
    "EXPIRED": WATERMARK_VOID,
}


@dataclass(frozen=True)
class SignatureBlock:
    party: str
    name: str = ""
    title: str = ""
    email: str = ""
    signed_at: str = ""
    typed_name: str = ""
    method: str = ""
    ip_address: str = ""
    remarks: str = ""
    declined: bool = False
    declined_at: str = ""
    decline_reason: str = ""
    #: When this signer accepted remarks made after they signed.
    acknowledged_at: str = ""
    required: bool = True


@dataclass(frozen=True)
class AuditEntry:
    occurred_at: str
    event: str
    actor: str = ""


@dataclass(frozen=True)
class RecordView:
    """One record as the PDF needs it: frozen content plus its current state."""

    snapshot: dict[str, Any]
    status: str
    content_hash: str = ""
    issued_at: str = ""
    signatures: tuple[SignatureBlock, ...] = field(default_factory=tuple)
    audit: tuple[AuditEntry, ...] = field(default_factory=tuple)

    @property
    def number(self) -> str:
        return self.snapshot["record"]["number"]

    @property
    def watermark(self) -> str:
        return _WATERMARKS.get(self.status, "")


# ── Characters the font cannot draw ──────────────────────────────────


@lru_cache(maxsize=1)
def _supported_codepoints() -> frozenset[int]:
    """Code points every face can draw: any text may be bold or italic."""
    faces = []
    for path in (FONT_REGULAR, FONT_BOLD, FONT_ITALIC):
        font = TTFont(str(path), lazy=True)
        faces.append(set(font.getBestCmap()))
        font.close()
    return frozenset(set.intersection(*faces))


def unsupported_characters(text: str) -> list[str]:
    """Characters in ``text`` the PDF could not reproduce, in first-seen order.

    Whitespace and control characters used for layout are not characters to
    draw and are ignored.
    """
    supported = _supported_codepoints()
    seen: dict[str, None] = {}
    for char in text:
        if char in "\n\r\t" or char in seen:
            continue
        if ord(char) not in supported:
            seen[char] = None
    return list(seen)


# ── Formatting ───────────────────────────────────────────────────────


def format_time(iso: str | None) -> str:
    """An ISO timestamp as an unambiguous UTC time, e.g. ``23 Nov 2026, 19:31 UTC``.

    UTC on purpose: a record read in two time zones must show one time.
    """
    if not iso:
        return "—"
    moment = datetime.fromisoformat(iso)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return f"{moment.day} {moment.strftime('%b %Y, %H:%M')} UTC"


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


# ── The document ─────────────────────────────────────────────────────


class _RecordPDF(FPDF):
    def __init__(self, *, title: str, created: datetime) -> None:
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 20, 18)
        self.add_font(FAMILY, "", str(FONT_REGULAR))
        self.add_font(FAMILY, "B", str(FONT_BOLD))
        self.add_font(FAMILY, "I", str(FONT_ITALIC))
        self.set_title(title)
        self.set_creator("Zorven")
        self.set_producer("Zorven")
        # Fixed rather than "now", so the same record renders to the same
        # bytes however many times it is downloaded.
        self.set_creation_date(created)
        self.alias_nb_pages()
        self.running_title = title
        self.running_ref = ""
        self.watermark = ""

    # fpdf2 calls these on every page.
    def header(self) -> None:
        if self.watermark:
            self.set_font(FAMILY, "B", 44)
            self.set_text_color(228, 228, 228)
            with self.rotation(45, x=self.w / 2, y=self.h / 2):
                width = self.get_string_width(self.watermark)
                self.text((self.w - width) / 2, self.h / 2, self.watermark)
        self.set_text_color(110, 110, 110)
        self.set_font(FAMILY, "", 8)
        self.set_xy(self.l_margin, 9)
        self.cell(0, 5, self.running_title, align="L")
        self.set_xy(self.l_margin, 9)
        self.cell(0, 5, self.running_ref, align="R")
        self.set_text_color(0, 0, 0)
        self.set_xy(self.l_margin, self.t_margin)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_text_color(110, 110, 110)
        self.set_font(FAMILY, "", 8)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(0, 0, 0)

    # ── building blocks ──────────────────────────────────────────────

    def title_line(self, text: str, size: int = 20) -> None:
        self.set_font(FAMILY, "B", size)
        self.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def section(self, text: str) -> None:
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(4)
        self.set_font(FAMILY, "B", 13)
        self.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def paragraph(self, text: str, size: float = 10, color: int = 0) -> None:
        self.set_font(FAMILY, "", size)
        self.set_text_color(color, color, color)
        self.multi_cell(0, size * 0.52, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1.5)

    def pair(self, label: str, value: str) -> None:
        self.set_font(FAMILY, "B", 9.5)
        self.cell(48, 5.5, label)
        self.set_font(FAMILY, "", 9.5)
        self.multi_cell(0, 5.5, value or "—", new_x="LMARGIN", new_y="NEXT")

    def rich(self, text: str, size: float = 10, indent: float = 0) -> None:
        """Text with ``**bold**`` and ``*italic*`` runs. Nothing else is
        interpreted, so no other character in a legal text is treated as
        markup."""
        self.set_x(self.l_margin + indent)
        left = self.l_margin
        self.set_left_margin(left + indent)
        for part in _EMPHASIS.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                self.set_font(FAMILY, "B", size)
                self.write(size * 0.52, part[2:-2])
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                self.set_font(FAMILY, "I", size)
                self.write(size * 0.52, part[1:-1])
            else:
                self.set_font(FAMILY, "", size)
                self.write(size * 0.52, part)
        self.set_left_margin(left)
        self.ln(size * 0.52 + 1.5)

    def markdown(self, text: str) -> None:
        """The description's own light markdown: ``##`` headings, bullets,
        rules and bold. Anything else prints as written."""
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                self.ln(1.5)
            elif line.startswith("## "):
                self.ln(2)
                self.set_font(FAMILY, "B", 11)
                self.multi_cell(0, 6, line[3:].strip(), new_x="LMARGIN", new_y="NEXT")
                self.ln(1)
            elif line.strip() == "---":
                self.ln(1)
            elif re.match(r"^\s*[-*]\s+", line):
                body = re.sub(r"^\s*[-*]\s+", "", line)
                self.set_font(FAMILY, "", 10)
                self.set_x(self.l_margin + 2)
                self.write(5.2, "•")
                self.rich(body, indent=7)
            else:
                self.rich(line)


def _render_record(pdf: _RecordPDF, view: RecordView) -> None:
    snap = view.snapshot
    client = snap["parties"]["client"]
    agency = snap["parties"]["agency"]
    meeting = snap["meeting"]

    pdf.running_ref = view.number
    pdf.watermark = view.watermark
    pdf.add_page()

    # 1 · Cover
    pdf.title_line("Meeting Record")
    pdf.pair("Record number", view.number)
    if snap["record"].get("supersedes"):
        pdf.pair("Supersedes", snap["record"]["supersedes"])
    pdf.pair("Status", view.status.replace("_", " ").title())
    pdf.pair("Between", agency.get("name") or "—")
    pdf.pair(
        "And",
        client.get("legal_name") or client.get("name") or "—",
    )
    if client.get("legal_name") and client.get("name") != client.get("legal_name"):
        pdf.pair("Trading as", client.get("name", ""))
    pdf.pair("Registered address", client.get("registered_address", ""))
    if client.get("registration_number"):
        pdf.pair("Registration number", client["registration_number"])
    pdf.pair("Meeting started", format_time(meeting.get("started_at")))
    pdf.pair("Meeting ended", format_time(meeting.get("stopped_at")))
    pdf.pair("Duration", format_duration(meeting.get("duration_s")))
    pdf.pair("Issued", format_time(view.issued_at) if view.issued_at else "Not issued")
    pdf.pair("Content fingerprint", view.content_hash or "Not issued")

    # 2 · Legal status
    pdf.section("1. Status of this document")
    for block in snap["clause"]["text"].split("\n\n"):
        pdf.paragraph(block)
    pdf.paragraph(f"Clause version {snap['clause']['version']}.", size=8, color=110)

    # 3 · Attendance and consent
    pdf.section("2. Attendance and recording consent")
    if snap["attendees"]:
        for person in snap["attendees"]:
            role = {"operator": agency.get("name"), "participant": client.get("name")}
            party = role.get(person.get("role", ""), "") or person.get("role", "")
            pdf.paragraph(f"{person.get('name', '')} — {party}".rstrip(" —"))
    else:
        pdf.paragraph("No attendance roll call was recorded for this meeting.")
    consent = snap.get("consent")
    if consent:
        method = str(consent.get("method", "")).replace("_", " ").lower()
        line = (
            f"Consent to be recorded was given by {consent.get('subject_name', '')} "
            f"({method}) on {format_time(consent.get('granted_at'))}."
        )
        if consent.get("revoked_at"):
            line += f" It was revoked on {format_time(consent['revoked_at'])}."
        pdf.paragraph(line)
    else:
        pdf.paragraph("No recording consent is on file for this session.")

    # 4 · Agreements
    pdf.section("3. Agreements")
    agreements = snap["agreements"]
    if agreements.get("preamble"):
        pdf.paragraph(agreements["preamble"])
    if agreements["items"]:
        for item in agreements["items"]:
            pdf.set_font(FAMILY, "B", 10)
            pdf.cell(13, 5.2, item["number"])
            pdf.rich(item["text"], indent=13)
    else:
        pdf.paragraph("No agreements were recorded in this meeting.")

    # 5 · Description
    pdf.section("4. Description")
    pdf.paragraph(
        "Summary prepared with automated tools. See section 1.", size=8, color=110
    )
    if snap["description"]:
        pdf.markdown(snap["description"])
    else:
        pdf.paragraph("No description is available for this meeting.")

    # 6 · Completeness
    completeness = snap.get("completeness") or {}
    if completeness.get("state") and completeness["state"] != "complete":
        pdf.section("5. Completeness notice")
        note = completeness.get("note", "")
        missing = completeness.get("missing_s")
        if missing:
            note += f" Approximately {format_duration(missing)} is not covered."
        pdf.paragraph(note)

    # 7 · Signatures
    pdf.section("Signatures")
    if not view.signatures:
        pdf.paragraph("No signatories have been named for this record.")
    for block in view.signatures:
        if pdf.get_y() > pdf.h - 70:
            pdf.add_page()
        pdf.set_font(FAMILY, "B", 10)
        suffix = "" if block.required else " (optional)"
        pdf.multi_cell(
            0, 6, f"For {block.party}{suffix}", new_x="LMARGIN", new_y="NEXT"
        )
        pdf.pair("Name", block.name)
        pdf.pair("Title", block.title)
        pdf.pair("Email", block.email)
        if block.declined:
            pdf.pair("Declined", format_time(block.declined_at))
            pdf.pair("Reason given", block.decline_reason)
        elif block.signed_at:
            pdf.pair("Signed", format_time(block.signed_at))
            pdf.pair("Signature", block.typed_name)
            pdf.pair("Method", block.method)
            if block.ip_address:
                pdf.pair("From address", block.ip_address)
            if block.remarks:
                pdf.pair("Remarks", block.remarks)
            if block.acknowledged_at:
                pdf.pair("Acknowledged remarks", format_time(block.acknowledged_at))
        else:
            pdf.pair("Signed", "Not signed")
        pdf.ln(4)

    # 8 · Annex A — transcript
    pdf.add_page()
    pdf.section("Annex A — Clean transcript")
    pdf.paragraph(
        "Automated transcription with filler and repetition removed. Lines are "
        "numbered so they can be cited. See section 1.",
        size=8,
        color=110,
    )
    if snap["transcript"]:
        for number, line in enumerate(snap["transcript"], start=1):
            pdf.set_font(FAMILY, "", 8)
            pdf.set_text_color(130, 130, 130)
            pdf.cell(11, 4.9, str(number))
            pdf.set_text_color(0, 0, 0)
            pdf.rich(line, size=9.5, indent=11)
    else:
        pdf.paragraph("No clean transcript is available for this meeting.")

    # 9 · Certificate
    pdf.add_page()
    pdf.section("Certificate")
    pdf.pair("Record number", view.number)
    pdf.pair("Content fingerprint", view.content_hash or "Not issued")
    pdf.paragraph(
        "The fingerprint is the SHA-256 hash of this record's content as it "
        "was frozen at issue. Any change to the agreements, description or "
        "transcript would produce a different fingerprint.",
        size=8,
        color=110,
    )
    pdf.ln(2)
    pdf.set_font(FAMILY, "B", 10)
    pdf.multi_cell(0, 6, "Audit trail", new_x="LMARGIN", new_y="NEXT")
    if view.audit:
        for entry in view.audit:
            actor = f" — {entry.actor}" if entry.actor else ""
            pdf.paragraph(
                f"{format_time(entry.occurred_at)}   {entry.event}{actor}", size=9
            )
    else:
        pdf.paragraph("No events recorded.", size=9)


def _created(view: RecordView) -> datetime:
    """The PDF's creation date: when the record was issued, else its meeting."""
    iso = view.issued_at or view.snapshot["meeting"].get("started_at")
    if not iso:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)
    moment = datetime.fromisoformat(iso)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def build_record_pdf(view: RecordView) -> bytes:
    """One meeting record as PDF bytes."""
    pdf = _RecordPDF(title=f"Meeting Record {view.number}", created=_created(view))
    _render_record(pdf, view)
    return bytes(pdf.output())


def build_binder_pdf(
    views: list[RecordView], *, agency_name: str, client_name: str
) -> bytes:
    """Every record of a session, oldest meeting first, as one PDF.

    Each record keeps its own status, watermark, fingerprint and signature
    section. The binder adds only a cover, an index and a manifest — it never
    restates a record's content, so adding a meeting cannot alter an earlier
    one.
    """
    created = max(
        (_created(v) for v in views), default=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    pdf = _RecordPDF(title="Meeting Records — Session Binder", created=created)
    pdf.running_ref = "Session binder"
    pdf.add_page()

    pdf.title_line("Meeting Records")
    pdf.pair("Between", agency_name or "—")
    pdf.pair("And", client_name or "—")
    pdf.pair("Meetings", str(len(views)))
    pdf.ln(2)
    pdf.paragraph(
        "This binder compiles the record of each meeting in the session, in "
        "date order. Each record was issued and is signed separately; its "
        "status and fingerprint are its own."
    )

    pdf.section("Index")
    if not views:
        pdf.paragraph("No meeting records have been prepared for this session.")
    for index, view in enumerate(views, start=1):
        started = format_time(view.snapshot["meeting"].get("started_at"))
        status = view.status.replace("_", " ").title()
        pdf.paragraph(f"{index}.  {started}   {view.number}   {status}")

    for view in views:
        _render_record(pdf, view)

    pdf.running_ref = "Session binder"
    pdf.watermark = ""
    pdf.add_page()
    pdf.section("Manifest")
    pdf.paragraph(
        "The fingerprint of each record in this binder. A record that has not "
        "been issued has no fingerprint.",
        size=8,
        color=110,
    )
    for view in views:
        pdf.pair(view.number, view.content_hash or "Not issued")

    return bytes(pdf.output())
