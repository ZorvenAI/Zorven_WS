"""The mandatory contract-detail questions, as data.

A signed meeting record names two parties. The details that identify the
client — its legal name, its registered address, who may sign for it — have to
be collected, and the first meeting is where that happens.

**Why a fixed list rather than something the question generator writes.** The
generator trims to the count the operator asked for and is free to reword. For
the details a signature depends on, "usually asked" is not good enough: the
list has to be the same for every client, in wording a lawyer can review once.
So these are merged into every questionnaire by Django, on top of whatever was
generated, and the generator is told which topics they cover so it does not
spend its own questions repeating them.

**How each item may be collected.** Speech-to-text is weakest on exactly these
values — names, addresses, email addresses — so:

- ``SPOKEN`` items are asked aloud and extracted like any other answer, then
  confirmed by the operator in review. The transcript is a first draft.
- ``WRITTEN`` items are never extracted from audio. An email address or a
  registration number that was misheard is worse than one that is missing,
  and an identifier said aloud sits in the recording and every transcript
  tier. The question still appears on the checklist so the operator asks the
  client to send it; the value is typed in.

Pure data with no Django imports, for the same reason as ``field_map.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

SPOKEN = "SPOKEN"
WRITTEN = "WRITTEN"


@dataclass(frozen=True)
class ContractField:
    """One mandatory question and the Company field its answer fills."""

    field: str
    question: str
    #: A short noun phrase for the generator's "already covered" list.
    topic: str
    #: Whether a meeting record can be issued without it.
    required_to_issue: bool
    collection: str


#: Ordered as they are asked. The order is part of the contract: the meeting
#: view shows them first, in this sequence.
CONTRACT_FIELDS: tuple[ContractField, ...] = (
    ContractField(
        field="legal_name",
        question="What is the registered legal name of the company?",
        topic="the company's registered legal name",
        required_to_issue=True,
        collection=SPOKEN,
    ),
    ContractField(
        field="registered_address",
        question="What is the company's registered business address?",
        topic="the company's registered business address",
        required_to_issue=True,
        collection=SPOKEN,
    ),
    ContractField(
        field="signatory_name",
        question=(
            "What is the full name of the person authorised to sign on the "
            "company's behalf?"
        ),
        topic="who is authorised to sign for the company",
        required_to_issue=True,
        collection=SPOKEN,
    ),
    ContractField(
        field="signatory_title",
        question="What is that person's title or role in the company?",
        topic="the authorised signatory's title or role",
        required_to_issue=True,
        collection=SPOKEN,
    ),
    ContractField(
        field="signatory_email",
        question=(
            "Which email address should signing requests be sent to? "
            "(Please send this in writing.)"
        ),
        topic="the signatory's email address",
        required_to_issue=True,
        collection=WRITTEN,
    ),
    ContractField(
        field="decision_maker",
        question="Who makes the final decisions on brand and campaign work?",
        topic="who makes brand and campaign decisions",
        required_to_issue=False,
        collection=SPOKEN,
    ),
    ContractField(
        field="billing_contact_email",
        question=(
            "Who should invoices and billing questions go to? "
            "(Please send the email address in writing.)"
        ),
        topic="the billing contact",
        required_to_issue=False,
        collection=WRITTEN,
    ),
    ContractField(
        field="registration_number",
        question=(
            "What is the company's registration number? "
            "(Please send this in writing rather than saying it aloud.)"
        ),
        topic="the company registration number",
        required_to_issue=False,
        collection=WRITTEN,
    ),
)

_BY_FIELD = {item.field: item for item in CONTRACT_FIELDS}


def contract_field_names() -> tuple[str, ...]:
    """Every field the mandatory questions cover, in asking order."""
    return tuple(item.field for item in CONTRACT_FIELDS)


def written_only_fields() -> frozenset[str]:
    """Fields that must never be filled from a recording."""
    return frozenset(
        item.field for item in CONTRACT_FIELDS if item.collection == WRITTEN
    )


def required_to_issue() -> tuple[str, ...]:
    """Fields a meeting record cannot be issued without."""
    return tuple(item.field for item in CONTRACT_FIELDS if item.required_to_issue)


def get(field: str) -> ContractField | None:
    return _BY_FIELD.get(field)


def is_answered(value: object) -> bool:
    """Whether a stored value counts as an answer.

    Whitespace is not an answer: a field holding ``"  "`` would otherwise
    suppress its question forever.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)
