"""SKL-OIA-13 — Record admin-edit pairs as golden-dataset candidates for the prompt
flywheel (§17.3).

Design §8.2 · implemented by story L-02.

For every field where the admin's final value diverges from the agent's
extraction, a redacted candidate is emitted to
``onboarding.golden-dataset.candidates``. prompt-optimization-svc consumes
it for GEPA offline optimisation. A failure here must never surface to the
operator (§8.2 fire-and-forget).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.core.logging import get_logger
from app.events.catalog import EventType
from app.events.emitter import EventEmitter
from app.logic.output_guardrails import redact_value
from app.messaging.producer import KafkaProducer
from app.messaging.schemas import GoldenCandidate, MessageEnvelope
from app.messaging.topics import GOLDEN_CANDIDATES, candidate_key
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)


class RecordGoldenCandidates(BaseSkill):
    """Record admin-edit pairs as golden-dataset candidates for the prompt flywheel
    (§17.3)."""

    def __init__(
        self,
        meta: Any,
        *,
        producer: KafkaProducer | None = None,
        emitter: EventEmitter | None = None,
        redis: RedisManager | None = None,
        **_kwargs: object,
    ) -> None:
        super().__init__(meta)
        self._producer = producer
        self._emitter = emitter
        self._redis = redis

    async def run(self, context: SkillContext) -> SkillResult:
        try:
            return await self._record(context)
        except Exception as exc:  # noqa: BLE001 — fire-and-forget (§8.2)
            logger.warning(
                "skl_oia_13_failed",
                error=str(exc),
                detail="golden candidate recording failed; operator unaffected",
            )
            return SkillResult(
                skill_id="SKL-OIA-13",
                output={"candidates_emitted": 0, "dlq_count": 1, "error": str(exc)},
            )

    async def _record(self, context: SkillContext) -> SkillResult:
        ic = context.input_context
        tenant_id = context.tenant_context.tenant_id
        session_id = ic.get("session_id", "")
        candidate_type = ic.get("candidate_type", "field_extraction")

        edit_distance = float(ic.get("edit_distance", 0))
        if edit_distance <= 0 and candidate_type != "sufficiency_override":
            return SkillResult(
                skill_id="SKL-OIA-13",
                output={"candidates_emitted": 0, "dlq_count": 0},
            )

        field_name = ic.get("field_name", "")
        extracted_value = str(ic.get("extracted_value", ""))
        admin_final_value = str(ic.get("admin_final_value", ""))
        classification = ic.get("classification", "SECONDARY")
        evidence_ref = ic.get("evidence_ref", "unknown")
        prompt_id = ic.get("prompt_id", "oia.extract_fields")

        if candidate_type == "sufficiency_override":
            prompt_id = "oia.sufficiency"
            classification = "KEY"
            edit_distance = 1.0

        prompt_version = await self._resolve_prompt_version(
            tenant_id, session_id, prompt_id
        )

        redacted_extracted, _ = redact_value(extracted_value)
        redacted_final, _ = redact_value(admin_final_value)

        candidate = GoldenCandidate(
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            field_name=field_name,
            input_evidence_ref=evidence_ref,
            extracted_value=str(redacted_extracted),
            admin_final_value=str(redacted_final),
            edit_distance=edit_distance,
            classification=classification,
            accepted_without_edit=False,
        )

        corr_id = context.correlation_id or uuid.uuid4().hex

        envelope = MessageEnvelope(
            correlation_id=corr_id,
            tenant_id=uuid.UUID(str(tenant_id)),
            session_id=uuid.UUID(str(session_id)) if session_id else None,
            payload=candidate.model_dump(mode="json"),
        )

        dlq_count = 0
        published = await self._publish(tenant_id, prompt_id, envelope)
        if not published:
            dlq_count = 1

        await self._emit_evt110(
            tenant_id=tenant_id,
            session_id=session_id,
            correlation_id=corr_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            edit_distance=edit_distance,
        )

        return SkillResult(
            skill_id="SKL-OIA-13",
            output={"candidates_emitted": 1, "dlq_count": dlq_count},
            prompt_version=prompt_version,
        )

    async def _resolve_prompt_version(
        self, tenant_id: str, session_id: str, prompt_id: str
    ) -> str:
        if not self._redis or not session_id:
            return "unknown"
        try:
            keys = self._redis.keys_for(tenant_id)
            session_key = keys.session(session_id)
            raw = await self._redis.client.hget(session_key, "prompt_versions")
            if raw:
                versions = json.loads(raw)
                return str(versions.get(prompt_id, "unknown"))
        except Exception:  # noqa: BLE001
            logger.debug("prompt_version_lookup_failed", prompt_id=prompt_id)
        return "unknown"

    async def _publish(
        self, tenant_id: str, prompt_id: str, envelope: MessageEnvelope
    ) -> bool:
        if not self._producer:
            logger.debug("skl_oia_13_no_producer", detail="Kafka not available")
            return False
        try:
            serialized = json.dumps(envelope.model_dump(mode="json")).encode()
            return await self._producer.send(
                GOLDEN_CANDIDATES.name,
                key=candidate_key(tenant_id, prompt_id),
                value=serialized,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("skl_oia_13_publish_failed", error=str(exc))
            return False

    async def _emit_evt110(
        self,
        *,
        tenant_id: str,
        session_id: str,
        correlation_id: str,
        prompt_id: str,
        prompt_version: str,
        edit_distance: float,
    ) -> None:
        if not self._emitter:
            return
        try:
            await self._emitter.emit(
                EventType.GOLDEN_CANDIDATE_RECORDED,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                session_id=session_id if session_id else None,
                skill_id="SKL-OIA-13",
                payload={
                    "prompt_id": prompt_id,
                    "prompt_version": prompt_version,
                    "edit_distance": edit_distance,
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning("skl_oia_13_evt110_failed")
