"""EVT-109, emitted when a reviewer confirms or edits a field (§12).

The event catalogue proper lives in ``onboarding-intelligence-agent-svc``
(``app/events/catalog.py``). This is the Django side of one event, because
§10.2 puts the review endpoints here — so Django performs the action and
Django has to say so. The payload below mirrors the catalogue and must be
changed with it; there is no shared package to enforce that today.

**The payload carries no values.** §12 is explicit: EVT-109 carries
``field_name, action, edit_distance, classification``. The edit distance is
computed on the server and the strings are discarded, because the event stream
fans out to observability tooling with a different access model than the
tenant-scoped store — a lower-trust surface that must never see a brand's
actual data.

Emission is best-effort by design. No ``deployment/gcp`` script provisions a
broker and every deployed service sets ``*_KAFKA_ENABLED=false``, so this is
inert in production today. A reviewer's click must not fail because a broker
is missing, so every failure here is swallowed and logged.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Matches EventType.PROVENANCE_REVIEWED in the agent's catalogue.
EVENT_TYPE = "onboarding.provenance.reviewed"
EVENT_REF = "EVT-109"

ACTION_CONFIRM = "CONFIRM"
ACTION_EDIT = "EDIT"


def build_payload(
    *, field_name: str, action: str, edit_distance: int, classification: str
) -> dict:
    """The EVT-109 body, and nothing else.

    Built by a named function rather than inline so a test can assert the
    exact key set — adding a value here would be a privacy regression, and it
    should have to get past an assertion first.
    """
    return {
        "event_ref": EVENT_REF,
        "field_name": field_name,
        "action": action,
        "edit_distance": edit_distance,
        "classification": classification,
    }


def emit_provenance_reviewed(
    *,
    tenant_id,
    session_id,
    field_name: str,
    action: str,
    edit_distance: int,
    classification: str,
) -> dict:
    """Publish EVT-109. Returns the payload so callers can assert on it.

    Never raises: a review action is a human waiting on a click, and an
    unreachable broker is not their problem.
    """
    payload = build_payload(
        field_name=field_name,
        action=action,
        edit_distance=edit_distance,
        classification=classification,
    )

    try:
        from kafka_service.tasks import publish_event_to_kafka

        publish_event_to_kafka(
            topic=f"agent.events.{tenant_id}" if tenant_id else "agent.events",
            event_type=EVENT_TYPE,
            data={**payload, "session_id": str(session_id)},
            key=str(session_id),
        )
    except Exception:  # noqa: BLE001 - see the module docstring
        logger.warning(
            "EVT-109 not published (event_ref=%s field=%s) — review still applied",
            EVENT_REF,
            field_name,
            exc_info=True,
        )

    return payload
