"""Whether a draft record is fit to be issued.

Issuing freezes the content for good, so everything that would make a record
wrong or unusable is checked first and reported together — an operator fixing
one problem at a time, issue attempt by issue attempt, is the worse design.

Each item has a ``code`` the interface can act on. A ``blocking`` item stops
the issue; a warning is shown and does not.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from apps.onboarding import contract_fields
from apps.onboarding.records.pdf import unsupported_characters
from apps.onboarding.records.snapshot import all_text
from apps.onboarding.services.contract_details import unreviewed_contract_fields

#: How each required detail is named to an operator.
LABELS = {
    "legal_name": "legal name",
    "registered_address": "registered address",
    "signatory_name": "authorised signatory",
    "signatory_title": "signatory title",
    "signatory_email": "signatory email",
}


@dataclass(frozen=True)
class ReadinessItem:
    code: str
    ok: bool
    blocking: bool
    message: str
    fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fields": list(self.fields)}


def _names(fields: tuple[str, ...]) -> str:
    return ", ".join(LABELS.get(name, name.replace("_", " ")) for name in fields)


def check_readiness(
    record, snapshot: dict[str, Any], *, acknowledge_incomplete: bool = False
) -> list[ReadinessItem]:
    """Every check, passed or not, in the order an operator would fix them."""
    items: list[ReadinessItem] = []
    company = record.session.company

    # 1 · There is something to record.
    has_content = bool(
        snapshot["transcript"]
        or snapshot["description"]
        or snapshot["agreements"]["items"]
    )
    items.append(
        ReadinessItem(
            code="content",
            ok=has_content,
            blocking=True,
            message=(
                "The meeting has a description or transcript."
                if has_content
                else "This meeting has no description or transcript yet. "
                "Process the recording first."
            ),
        )
    )

    # 2 · Both parties are named.
    agency_named = bool(snapshot["parties"]["agency"]["name"].strip())
    items.append(
        ReadinessItem(
            code="agency",
            ok=agency_named,
            blocking=True,
            message=(
                "The agency is named."
                if agency_named
                else "The agency has no name to print on the record."
            ),
        )
    )

    # A record is between two parties. A workspace named after its client
    # would otherwise print the client's name on both sides.
    client = snapshot["parties"]["client"]
    agency_name = snapshot["parties"]["agency"]["name"].strip().casefold()
    client_names = {
        str(client.get(key) or "").strip().casefold() for key in ("name", "legal_name")
    } - {""}
    distinct = not agency_named or agency_name not in client_names
    items.append(
        ReadinessItem(
            code="parties_distinct",
            ok=distinct,
            blocking=True,
            message=(
                "The agency and the client are different parties."
                if distinct
                else "The agency and the client have the same name "
                f"({snapshot['parties']['agency']['name']}). The workspace "
                "name is printed as the agency, so it must be the agency's "
                "name, not the client's."
            ),
        )
    )

    required = contract_fields.required_to_issue()
    missing = tuple(
        name
        for name in required
        if not contract_fields.is_answered(getattr(company, name, None))
    )
    items.append(
        ReadinessItem(
            code="party_details",
            ok=not missing,
            blocking=True,
            fields=missing,
            message=(
                "The client's contract details are complete."
                if not missing
                else f"Missing client contract details: {_names(missing)}."
            ),
        )
    )

    # 3 · Nothing on the record is an unconfirmed guess.
    pending = unreviewed_contract_fields(company)
    unreviewed = tuple(name for name in required if name in pending)
    items.append(
        ReadinessItem(
            code="unreviewed_details",
            ok=not unreviewed,
            blocking=True,
            fields=unreviewed,
            message=(
                "The client's contract details have been reviewed."
                if not unreviewed
                else "These details were picked up from the meeting and have "
                f"not been confirmed: {_names(unreviewed)}. Confirm them in "
                "Review first."
            ),
        )
    )

    # 3b · Someone signs for each party.
    parties = {s["party"] for s in snapshot.get("signatories", []) if s.get("required")}
    lacking = tuple(
        label
        for party, label in (("AGENCY", "the agency"), ("CLIENT", "the client"))
        if party not in parties
    )
    items.append(
        ReadinessItem(
            code="signatories",
            ok=not lacking,
            blocking=True,
            message=(
                "Each party has a signatory."
                if not lacking
                else "Add a required signatory for " + " and ".join(lacking) + "."
            ),
        )
    )

    # 4 · A gap in the transcript is issued knowingly, not by accident.
    state = (snapshot.get("completeness") or {}).get("state")
    complete = state == "complete"
    items.append(
        ReadinessItem(
            code="completeness",
            ok=complete or acknowledge_incomplete,
            blocking=True,
            message=(
                "The transcript covers the whole meeting."
                if complete
                else (
                    "The transcript does not cover the whole meeting, or its "
                    "coverage is unknown. The record will say so. Acknowledge "
                    "this to issue."
                )
            ),
        )
    )

    # 5 · The PDF can reproduce every character.
    unsupported = unsupported_characters(all_text(snapshot))
    items.append(
        ReadinessItem(
            code="unsupported_characters",
            ok=not unsupported,
            blocking=True,
            message=(
                "Every character can be reproduced in the PDF."
                if not unsupported
                else "The record contains characters the PDF cannot reproduce "
                "faithfully: " + " ".join(unsupported[:20]) + "."
            ),
        )
    )

    # 6 · Worth knowing, not worth stopping for.
    count = len(snapshot["agreements"]["items"])
    items.append(
        ReadinessItem(
            code="agreements",
            ok=count > 0,
            blocking=False,
            message=(
                f"{count} agreement(s) recorded."
                if count
                else "No agreements were found in this meeting's description. "
                "The record will state that none were recorded."
            ),
        )
    )
    has_consent = snapshot.get("consent") is not None
    items.append(
        ReadinessItem(
            code="consent",
            ok=has_consent,
            blocking=False,
            message=(
                "Recording consent is on file."
                if has_consent
                else "No recording consent is on file for this session. The "
                "record will say so."
            ),
        )
    )
    return items


def blocking_failures(items: list[ReadinessItem]) -> list[ReadinessItem]:
    return [item for item in items if item.blocking and not item.ok]
