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

Emission is inert in production by *configuration*, not by failure. No
``deployment/gcp`` script provisions a broker and every deployed service sets
``*_KAFKA_ENABLED=false``, so the publish is skipped outright rather than
attempted and lost — attempting it would mean a failed connection and a
warning on every single review action.

When it is enabled, the publish is queued through Celery rather than run
inline: a reviewer's click must not block on Kafka I/O, and must not fail if
the broker is unreachable.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils.crypto import salted_hmac

logger = logging.getLogger(__name__)

#: Matches EventType.PROVENANCE_REVIEWED in the agent's catalogue.
EVENT_TYPE = "onboarding.provenance.reviewed"
EVENT_REF = "EVT-109"

ACTION_CONFIRM = "CONFIRM"
ACTION_EDIT = "EDIT"


def emission_enabled() -> bool:
    """Whether EVT-109 should be published at all.

    A named predicate rather than an inline settings read, so the decision is
    testable on its own without standing up a broker or patching one out.
    """
    return bool(getattr(settings, "ONBOARDING_KAFKA_ENABLED", False))


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

    if not emission_enabled():
        # Inert by configuration rather than by failure. Every deployed
        # service sets *_KAFKA_ENABLED=false and no deployment/gcp script
        # provisions a broker, so attempting the publish would mean a failed
        # connection and a warning on every single review action.
        logger.debug("EVT-109 suppressed: Kafka disabled (field=%s)", field_name)
        return payload

    try:
        from kafka_service.tasks import publish_event_to_kafka

        # .delay(), not a direct call: publish_event_to_kafka is a Celery
        # @shared_task, and calling it directly runs it in this process — a
        # reviewer's click would then block on Kafka I/O.
        publish_event_to_kafka.delay(
            topic=f"agent.events.{tenant_id}" if tenant_id else "agent.events",
            event_type=EVENT_TYPE,
            data={**payload, "session_id": str(session_id)},
            key=str(session_id),
        )
    except Exception:  # noqa: BLE001 - see the module docstring
        logger.warning(
            "EVT-109 not queued (event_ref=%s field=%s) — review still applied",
            EVENT_REF,
            field_name,
            exc_info=True,
        )

    return payload


# ── EVT-101 · onboarding.consent.verified (F-01, AC-2) ───────────────

#: Matches EventType.CONSENT_VERIFIED in the agent's catalogue.
CONSENT_EVENT_TYPE = "onboarding.consent.verified"
CONSENT_EVENT_REF = "EVT-101"

#: Namespaces the HMAC so a subject hash cannot be compared against a hash of
#: the same string produced for any other purpose in this codebase.
CONSENT_HASH_SALT = "apps.onboarding.events.consent_subject"


def subject_name_hash(name: str) -> str:
    """A hash of the subject's name that cannot be turned back into it.

    Keyed, not bare. §12 lets the event stream carry ``subject_name_hash`` and
    never the name, and a plain SHA-256 of a personal name defeats that in an
    afternoon: the input space is small enough to enumerate, so an unkeyed
    digest of "Ada Lovelace" is "Ada Lovelace" to anyone with a name list.

    ``salted_hmac`` keys it off SECRET_KEY, which is the same root of trust the
    project already uses for OAuth token encryption. No new secret to
    provision, rotate or leave unset in one environment — and being unset is
    the failure mode that would quietly turn this back into a bare digest.

    Normalised first so the same person recorded twice hashes the same way,
    which is the only property that makes the hash useful for correlation at
    all. Case and surrounding whitespace are not identity.
    """
    normalised = " ".join(str(name or "").split()).casefold()
    return salted_hmac(CONSENT_HASH_SALT, normalised).hexdigest()


def build_consent_payload(*, consent_id, method: str, subject_name: str) -> dict:
    """The EVT-101 body, and nothing else.

    Built by a named function so a test can assert the exact key set. AC-2 says
    the event carries "consent_id, method and subject_name_hash — never the
    subject's name", and the way a name reaches an event stream is that someone
    adds a field here for a good reason. It should have to get past an
    assertion first.
    """
    return {
        "event_ref": CONSENT_EVENT_REF,
        "consent_id": str(consent_id),
        "method": method,
        "subject_name_hash": subject_name_hash(subject_name),
    }


def emit_consent_verified(
    *, tenant_id, session_id, consent_id, method: str, subject_name: str
) -> dict:
    """Publish EVT-101. Returns the payload so callers can assert on it.

    Never raises. Consent has already been recorded in the database by the time
    this runs; a broker problem must not turn a lawful, captured consent into a
    failed request the operator retries.
    """
    payload = build_consent_payload(
        consent_id=consent_id, method=method, subject_name=subject_name
    )

    if not emission_enabled():
        logger.debug("EVT-101 suppressed: Kafka disabled (consent=%s)", consent_id)
        return payload

    try:
        from kafka_service.tasks import publish_event_to_kafka

        publish_event_to_kafka.delay(
            topic=f"agent.events.{tenant_id}" if tenant_id else "agent.events",
            event_type=CONSENT_EVENT_TYPE,
            data={**payload, "session_id": str(session_id)},
            key=str(session_id),
        )
    except Exception:  # noqa: BLE001 - see the module docstring
        logger.warning(
            "EVT-101 not queued (event_ref=%s consent=%s) — consent still recorded",
            CONSENT_EVENT_REF,
            consent_id,
            exc_info=True,
        )

    return payload
