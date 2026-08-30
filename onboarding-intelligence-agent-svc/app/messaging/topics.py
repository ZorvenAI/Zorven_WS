"""Kafka topic catalogue (Design §13.1).

Single source of truth for topic names and retention. AC-1 is written against
"the Terraform module that provisions fleet agent topics" — there is no
Terraform in this monorepo (zero ``.tf`` files; compose relies on
``KAFKA_AUTO_CREATE_TOPICS_ENABLE``), so this module plus
:mod:`app.messaging.provision` is what that module would have been, expressed
in the form the repository actually uses.
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
GOLDEN_CANDIDATES = TopicSpec(
    name="onboarding.golden-dataset.candidates",
    retention_ms=30 * DAY_MS,
    purpose="Admin-edit flywheel consumed by prompt-optimization-svc (§17.3)",
)

FLEET_TOPICS: Final[tuple[TopicSpec, ...]] = (
    COMMANDS,
    RESULTS,
    ESCALATIONS,
    DLQ,
    MEMORY_EVICTION,
    GOLDEN_CANDIDATES,
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


def candidate_key(tenant_id: str, prompt_id: str) -> str:
    """§13.1 keys the golden-dataset topic on ``tenant:prompt_id``.

    Lets POI's consumer partition per prompt per tenant without a repartition
    step. Getting the key wrong here is expensive to change later because it
    changes partition assignment.
    """
    return f"{tenant_id}:{prompt_id}"
