"""Commands Django sends to the agent (§13, ``agent.commands.*``).

Published rather than called. The B-07 technical note gives the reason: "a
revocation must succeed even if the agent is down." A synchronous call would
tie a legal action — withdrawing consent — to the availability of a service
that has no business blocking it.

So revocation is recorded in PostgreSQL first and the notification is
best-effort, gated and queued exactly like EVT-109 in ``events.py``. If the
broker is missing the consent is still revoked; only the agent's prompt
awareness of it is delayed.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: The agent's command topic, provisioned by A-05.
COMMANDS_TOPIC = "agent.commands.onboarding-intelligence"

COMMAND_CONSENT_REVOKED = "consent.revoked"

#: The close code the agent must use when it drops a live socket for revoked
#: consent. §10.2.3 and §9 both say 4403; §5.1's IG-08 row says 4401, which is
#: already spent on an invalid JWT — that row is a typo.
CLOSE_CODE_CONSENT_REVOKED = 4403


def build_consent_revoked(*, session_id, tenant_id, consent_id) -> dict:
    """The command body, and nothing else.

    Ids only — no subject name, no scope. NFR-PRIV-01 keeps personal data in
    the tenant-scoped store, and a command topic is a lower-trust surface. The
    agent can read the record if it needs the detail.
    """
    return {
        "command": COMMAND_CONSENT_REVOKED,
        "session_id": str(session_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "consent_id": str(consent_id),
        "close_code": CLOSE_CODE_CONSENT_REVOKED,
    }


def publish_consent_revoked(*, session_id, tenant_id, consent_id) -> dict:
    """Tell the agent to drop any live socket for this session.

    Never raises. Returns the payload so a caller — or a test — can assert on
    its shape without a broker.
    """
    payload = build_consent_revoked(
        session_id=session_id, tenant_id=tenant_id, consent_id=consent_id
    )

    if not commands_enabled():
        logger.debug("consent.revoked not published: Kafka disabled (%s)", session_id)
        return payload

    try:
        from kafka_service.tasks import publish_event_to_kafka

        # .delay(): publish_event_to_kafka is a Celery @shared_task, and a
        # revocation must not wait on Kafka I/O.
        publish_event_to_kafka.delay(
            topic=COMMANDS_TOPIC,
            event_type=COMMAND_CONSENT_REVOKED,
            data=payload,
            key=str(session_id),
        )
    except Exception:  # noqa: BLE001 - the revocation already succeeded
        logger.warning(
            "consent.revoked not queued for session %s — consent is still revoked",
            session_id,
            exc_info=True,
        )

    return payload


def commands_enabled() -> bool:
    """Whether agent commands should be published at all.

    A named predicate so the decision is testable without a broker and
    without patching one out.
    """
    return bool(getattr(settings, "ONBOARDING_KAFKA_ENABLED", False))
