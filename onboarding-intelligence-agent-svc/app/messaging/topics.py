"""Kafka topic catalogue (Design §13.1).

Single source of truth for topic names and retention. AC-1 is written against
"the Terraform module that provisions fleet agent topics" — there is no
Terraform in this monorepo (zero ``.tf`` files; compose relies on
``KAFKA_AUTO_CREATE_TOPICS_ENABLE``), so this module plus
:mod:`app.messaging.provision` is what that module would have been, expressed
in the form the repository actually uses.

``onboarding.golden-dataset.candidates`` is deliberately **absent**. A-03's
technical note: it belongs to L-02, and creating it early produces an empty
topic nobody consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

AGENT_NAME: Final[str] = "onboarding-intelligence"

DAY_MS: Final[int] = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class TopicSpec:
    """A topic and the retention Design §13.1 assigns it."""

    name: str
    retention_ms: int
    purpose: str
    partitions: int = 3
    replication_factor: int = 1

    @property
    def config(self) -> dict[str, str]:
        return {"retention.ms": str(self.retention_ms)}


#: Per-tenant event stream. The tenant id is part of the topic name, so the
#: name is built rather than fixed.
EVENTS_TOPIC_TEMPLATE: Final[str] = "agent.events.{tenant_id}"

COMMANDS = TopicSpec(
    name=f"agent.commands.{AGENT_NAME}",
    retention_ms=1 * DAY_MS,
    purpose="PROCESS jobs and async commands",
)
RESULTS = TopicSpec(
    name=f"agent.results.{AGENT_NAME}",
    retention_ms=1 * DAY_MS,
    purpose="Job results mirrored for consumers other than the callback",
)
ESCALATIONS = TopicSpec(
    name="agent.escalations",
    retention_ms=30 * DAY_MS,
    purpose="Shared platform escalation queue — SKL-OIA-14 output",
)
DLQ = TopicSpec(
    name=f"agent.dlq.{AGENT_NAME}",
    retention_ms=30 * DAY_MS,
    purpose="Dead-lettered commands and results after retry exhaustion",
)
MEMORY_EVICTION = TopicSpec(
    name="memory.eviction.events",
    retention_ms=3 * DAY_MS,
    purpose="L2/L3 eviction and summarization telemetry (§6)",
)

#: The fleet-mandatory set, minus the per-tenant events topic which is created
#: on demand. AC-1 calls the sixth "the heartbeat topic"; §13.1 names it
#: memory.eviction.events, and §13.1 is the catalogue, so that is what is
#: provisioned.
FLEET_TOPICS: Final[tuple[TopicSpec, ...]] = (
    COMMANDS,
    RESULTS,
    ESCALATIONS,
    DLQ,
    MEMORY_EVICTION,
)


def events_topic(tenant_id: str) -> str:
    """Topic carrying all §12 events for one tenant."""
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("tenant_id is required to build an events topic")
    return EVENTS_TOPIC_TEMPLATE.format(tenant_id=tenant_id)


def events_topic_spec(tenant_id: str) -> TopicSpec:
    return TopicSpec(
        name=events_topic(tenant_id),
        retention_ms=7 * DAY_MS,
        purpose="All structured events from §12",
    )


def message_key(tenant_id: str, session_id: str | None) -> str:
    """§13.1 keys every topic on ``tenant:session``.

    Keying on the tenant keeps one tenant's ordering independent of another's,
    and keying on the session keeps a meeting's events in order within it.
    """
    return f"{tenant_id}:{session_id or '-'}"
