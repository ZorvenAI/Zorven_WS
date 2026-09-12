"""Writing provenance rows under PG-06 (Design §5.3).

PG-06: "A PROCESS re-run must not overwrite any field whose
FieldProvenance.status is EDITED or CONFIRMED. Conflicts are surfaced through
SKL-OIA-14, never silently resolved."

**This guard is weaker than the grounding constraint, deliberately and
visibly.** OG-01 lives in PostgreSQL, so no write path can evade it. PG-06
cannot: it compares the row being written to the row already there, which is
UPDATE-time logic a CheckConstraint cannot express. So it lives here, and a
caller that goes straight to ``FieldProvenance.objects.bulk_create`` bypasses
it — the same hole the B-05 card warns about for grounding.

That is the acceptance criterion as written ("the model-level expression of
PG-06"), and it is recorded rather than papered over: **J-03 must write
through ``write_provenance`` and not through the manager.** A PostgreSQL
trigger would close the gap properly and is the obvious follow-up if the
convention proves insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.onboarding.models import FieldProvenance, ProvenanceStatus


@dataclass(frozen=True)
class WriteResult:
    """What a write actually did, so a caller can report it.

    ``conflicted`` is not an error: PG-06 says conflicts are surfaced, never
    silently resolved, so they are returned for SKL-OIA-14 to escalate rather
    than raised and lost.
    """

    created: list[FieldProvenance]
    updated: list[FieldProvenance]
    conflicted: list[FieldProvenance]

    @property
    def total(self) -> int:
        return len(self.created) + len(self.updated) + len(self.conflicted)


@transaction.atomic
def write_provenance(session, rows: list[dict]) -> WriteResult:
    """Write provenance for *session*, honouring PG-06.

    Each entry in *rows* needs at least ``model_name``, ``field_name``,
    ``extracted_value`` and one source. A row whose existing status is
    CONFIRMED or EDITED is **not** overwritten; it is marked CONFLICT and
    returned so the caller can escalate.

    Grounding is not re-checked here. The database refuses an unsourced row
    on its own, and duplicating that check in Python would create a second
    definition of the rule that could drift from the first.
    """
    created: list[FieldProvenance] = []
    updated: list[FieldProvenance] = []
    conflicted: list[FieldProvenance] = []

    existing = {
        (row.model_name, row.field_name): row
        for row in FieldProvenance.objects.filter(session=session).select_for_update()
    }

    for row in rows:
        key = (row["model_name"], row["field_name"])
        current = existing.get(key)

        if current is None:
            created.append(
                FieldProvenance.objects.create(
                    session=session, tenant=session.tenant, **row
                )
            )
            continue

        if current.is_protected:
            # PG-06: a reviewer's decision outranks a re-run. The row keeps
            # its reviewed value; CONFLICT records that the agent disagreed,
            # which is what SKL-OIA-14 escalates.
            current.status = ProvenanceStatus.CONFLICT
            current.save(update_fields=["status", "updated_at"])
            conflicted.append(current)
            continue

        for field, value in row.items():
            setattr(current, field, value)
        current.save()
        updated.append(current)

    return WriteResult(created=created, updated=updated, conflicted=conflicted)
