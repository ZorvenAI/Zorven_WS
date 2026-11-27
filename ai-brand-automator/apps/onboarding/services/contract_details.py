"""Which of a company's contract details are still to be collected.

Used in two places that must not disagree: the questionnaire asks for what is
outstanding, and a meeting record refuses to be issued while a required detail
is outstanding.
"""

from __future__ import annotations

import json

from apps.onboarding import contract_fields
from apps.onboarding.contract_fields import ContractField
from apps.onboarding.models import FieldProvenance, ProvenanceStatus


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def unreviewed_contract_fields(company) -> set[str]:
    """Contract details whose value on file is still an unconfirmed guess.

    Only the newest extraction of each field counts, and only while the value
    on file is still that guess. Once a person has typed something else into
    the company form, the value is theirs, even though the old provenance row
    was never reviewed.
    """
    if company is None:
        return set()
    latest: dict[str, FieldProvenance] = {}
    for row in FieldProvenance.objects.filter(
        session__company=company,
        model_name="Company",
        field_name__in=contract_fields.contract_field_names(),
    ).order_by("field_name", "-created_at", "-pk"):
        latest.setdefault(row.field_name, row)
    return {
        field
        for field, row in latest.items()
        if row.status in (ProvenanceStatus.PENDING, ProvenanceStatus.CONFLICT)
        and _as_text(getattr(company, field, None)) == _as_text(row.extracted_value)
    }


def outstanding_contract_fields(company) -> list[ContractField]:
    """The contract details still to be collected for this company.

    Outstanding means empty, or filled by extraction and not yet confirmed. A
    value the agent wrote and nobody has reviewed is a guess about a legal
    name or an address, and asking once more is cheaper than signing a guess.

    With no company — the common case before onboarding starts — everything
    is outstanding.
    """
    if company is None:
        return list(contract_fields.CONTRACT_FIELDS)

    unreviewed = unreviewed_contract_fields(company)
    return [
        item
        for item in contract_fields.CONTRACT_FIELDS
        if item.field in unreviewed
        or not contract_fields.is_answered(getattr(company, item.field, None))
    ]
