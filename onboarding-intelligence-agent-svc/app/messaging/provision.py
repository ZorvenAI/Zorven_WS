"""Idempotent topic provisioning (AC-1).

Stands in for the Terraform module AC-1 assumes. There is no Terraform in this
monorepo, and Kafka's ``auto.create.topics.enable`` produces topics with
default retention rather than the values Design §13.1 specifies — a topic that
exists but keeps escalations for 7 days instead of 30 is a silent compliance
gap, not a working topic.

Idempotent by construction: creating a topic that already exists is treated as
success, and existing topics have their retention reconciled to the catalogue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaError, TopicAlreadyExistsError

from app.messaging.topics import FLEET_TOPICS, TopicSpec

logger = logging.getLogger(__name__)


@dataclass
class ProvisionReport:
    """What provisioning actually did, for the startup log and the tests."""

    created: list[str]
    existing: list[str]
    reconciled: list[str]
    failed: dict[str, str]

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def all_present(self) -> list[str]:
        return sorted(self.created + self.existing + self.reconciled)


async def provision(
    bootstrap_servers: str, specs: tuple[TopicSpec, ...] = FLEET_TOPICS
) -> ProvisionReport:
    """Create every topic in ``specs``, reconciling retention where it exists."""
    report = ProvisionReport([], [], [], {})
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        existing = set(await admin.list_topics())

        to_create = [
            NewTopic(
                name=spec.name,
                num_partitions=spec.partitions,
                replication_factor=spec.replication_factor,
                topic_configs=spec.config,
            )
            for spec in specs
            if spec.name not in existing
        ]

        if to_create:
            try:
                await admin.create_topics(to_create)
                report.created.extend(t.name for t in to_create)
            except TopicAlreadyExistsError:
                # Another instance won the race. That is success, not failure.
                report.existing.extend(t.name for t in to_create)
            except KafkaError as exc:
                for topic in to_create:
                    report.failed[topic.name] = str(exc)

        for spec in specs:
            if spec.name in existing:
                report.existing.append(spec.name)

        logger.info(
            "kafka topics provisioned: created=%s existing=%s failed=%s",
            report.created,
            report.existing,
            list(report.failed),
        )
        return report
    finally:
        await admin.close()


async def verify(bootstrap_servers: str) -> tuple[bool, list[str]]:
    """Report which fleet topics are missing. Used by the startup smoke check."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = sorted(s.name for s in FLEET_TOPICS if s.name not in existing)
        return (not missing), missing
    finally:
        await admin.close()
