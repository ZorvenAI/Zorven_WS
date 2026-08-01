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
from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType
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

        # Reconcile retention on topics that already exist. This is the whole
        # reason the provisioner exists rather than relying on Kafka's
        # auto-create: an auto-created topic gets the broker default, so
        # agent.escalations would silently keep 7 days instead of 30 — a
        # compliance gap that looks like a working topic.
        for spec in specs:
            if spec.name not in existing:
                continue
            try:
                changed = await _reconcile_retention(admin, spec)
            except KafkaError as exc:
                report.failed[spec.name] = f"retention reconcile failed: {exc}"
                continue
            if changed:
                report.reconciled.append(spec.name)
            else:
                report.existing.append(spec.name)

        logger.info(
            "kafka topics provisioned: created=%s existing=%s reconciled=%s "
            "failed=%s",
            report.created,
            report.existing,
            report.reconciled,
            list(report.failed),
        )
        return report
    finally:
        await admin.close()


async def _current_retention(admin: AIOKafkaAdminClient, topic: str) -> str | None:
    """Read ``retention.ms`` as the broker currently has it."""
    resource = ConfigResource(ConfigResourceType.TOPIC, topic)
    responses = await admin.describe_configs([resource])
    for response in responses:
        for described in response.resources:
            # The resource tuple's arity varies with the DescribeConfigs API
            # version (5 fields here, 6 in later ones); the config entries are
            # always last, and each entry starts (name, value, ...).
            entries = described[-1]
            for entry in entries:
                if entry[0] == "retention.ms":
                    return str(entry[1])
    return None


async def _reconcile_retention(admin: AIOKafkaAdminClient, spec: TopicSpec) -> bool:
    """Set ``retention.ms`` to the catalogue value. True when it changed."""
    current = await _current_retention(admin, spec.name)
    desired = str(spec.retention_ms)
    if current == desired:
        return False

    await admin.alter_configs(
        [ConfigResource(ConfigResourceType.TOPIC, spec.name, configs=spec.config)]
    )
    logger.info("topic retention reconciled: %s %s -> %s", spec.name, current, desired)
    return True


async def retention_of(bootstrap_servers: str, topic: str) -> str | None:
    """Public read of a topic's retention, for tests and diagnostics."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        return await _current_retention(admin, topic)
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
