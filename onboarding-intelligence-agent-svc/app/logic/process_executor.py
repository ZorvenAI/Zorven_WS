"""PROCESS mode job orchestration.

Design §9.3 · implemented by story J-01, evidence assembly by J-02.

J-01 delivers the dispatch envelope, idempotency and lifecycle callback.
J-02 fills in the actual extraction logic inside ``_run_job``.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Literal

from app.api.schemas import EvidenceManifest, ProcessResponse
from app.cache.redis_manager import RedisManager, TTL_IDEMPOTENCY
from app.core.logging import get_logger
from app.events.catalog import EventType
from app.events.emitter import EventEmitter
from app.logic.guardrails import GuardrailViolation
from app.messaging.producer import KafkaProducer
from app.messaging.schemas import ConflictCandidate, EscalationMessage
from app.messaging.topics import ESCALATIONS, message_key
from app.providers.llm import LLMProvider
from app.services.backend_client import BackendClient
from app.skills.models import TenantContext

logger = get_logger(__name__)


def _format_evidence_ref(span: dict[str, Any]) -> str:
    """Format an evidence span as a reference pointer, never including text."""
    rec_id = span.get("recording_id")
    med_id = span.get("media_id")
    if rec_id:
        t_start = span.get("t_start", "")
        t_end = span.get("t_end", "")
        return f"recording:{rec_id}:{t_start}-{t_end}"
    if med_id:
        return f"media:{med_id}"
    return "unknown"


JOB_TTL = 3600
JobStatus = Literal["ACCEPTED", "RUNNING", "SUCCEEDED", "FAILED"]
JOB_STATUS_ACCEPTED: JobStatus = "ACCEPTED"
JOB_STATUS_RUNNING: JobStatus = "RUNNING"
JOB_STATUS_SUCCEEDED: JobStatus = "SUCCEEDED"
JOB_STATUS_FAILED: JobStatus = "FAILED"


class ProcessExecutor:
    """Accept PROCESS jobs, store state in Redis, run in background."""

    def __init__(
        self,
        redis: RedisManager,
        backend: BackendClient | None = None,
        settings: Any = None,
        llm: LLMProvider | None = None,
        kafka: KafkaProducer | None = None,
        events: EventEmitter | None = None,
    ) -> None:
        self._redis = redis
        self._backend = backend
        self._settings = settings
        self._llm = llm
        self._kafka = kafka
        self._events = events
        self._running_tasks: set[asyncio.Task[None]] = set()

    async def accept(
        self,
        *,
        tenant: TenantContext,
        session_id: str,
        manifest: EvidenceManifest,
        options: dict[str, Any],
        callback_url: str,
        idempotency_key: str,
    ) -> ProcessResponse:
        """Accept a PROCESS job, returning 202 immediately."""
        cached = await self._check_idempotency(tenant.tenant_id, idempotency_key)
        if cached is not None:
            logger.info(
                "process_idempotent_hit",
                session_id=session_id,
                idempotency_key=idempotency_key[:16],
            )
            return ProcessResponse.model_validate(cached)

        job_id = uuid.uuid4().hex
        estimated = getattr(self._settings, "PROCESS_TIMEOUT_S", 300)

        job_state = {
            "job_id": job_id,
            "session_id": session_id,
            "tenant_id": tenant.tenant_id,
            "status": JOB_STATUS_ACCEPTED,
            "manifest": manifest.model_dump(),
            "options": options,
            "callback_url": callback_url,
            "created_at": time.time(),
        }

        keys = self._redis.keys_for(tenant.tenant_id)
        job_key = keys.idempotency(f"process:job:{job_id}")
        await self._redis.client.set(job_key, json.dumps(job_state), ex=JOB_TTL)

        response = ProcessResponse(
            job_id=job_id,
            status=JOB_STATUS_ACCEPTED,
            estimated_duration_s=estimated,
            callback_url=callback_url,
        )

        await self._store_idempotency(
            tenant.tenant_id, idempotency_key, response.model_dump()
        )

        task = asyncio.create_task(
            self._run_job(
                job_id=job_id,
                tenant=tenant,
                session_id=session_id,
                manifest=manifest,
                options=options,
                callback_url=callback_url,
            )
        )
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

        return response

    async def get_job(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        """Retrieve job state from Redis."""
        keys = self._redis.keys_for(tenant_id)
        job_key = keys.idempotency(f"process:job:{job_id}")
        raw = await self._redis.client.get(job_key)
        if raw is None:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            return data
        except (json.JSONDecodeError, TypeError):
            return None

    async def _run_job(
        self,
        *,
        job_id: str,
        tenant: TenantContext,
        session_id: str,
        manifest: EvidenceManifest,
        options: dict[str, Any],
        callback_url: str,
    ) -> None:
        """Execute the PROCESS job and call back to Django."""
        keys = self._redis.keys_for(tenant.tenant_id)
        job_key = keys.idempotency(f"process:job:{job_id}")

        try:
            await self._redis.client.set(
                job_key,
                json.dumps({"job_id": job_id, "status": JOB_STATUS_RUNNING}),
                ex=JOB_TTL,
            )

            from app.logic.evidence_assembler import EvidenceAssembler
            from app.logic.memory_compression import compress_if_needed
            from app.logic.coverage import compute_coverage
            from app.logic.coverage_crosscheck import crosscheck_coverage

            assembler = EvidenceAssembler(
                redis=self._redis,
                backend=self._backend,
                settings=self._settings,
            )
            evidence = await assembler.assemble(
                tenant_id=tenant.tenant_id,
                session_id=session_id,
                manifest=manifest,
            )

            if self._llm is not None:
                evidence.blocks, evidence.compressed = await compress_if_needed(
                    evidence.blocks, self._llm, self._settings
                )
                if evidence.compressed:
                    evidence.token_estimate = sum(
                        len(b.text) // 4 for b in evidence.blocks
                    )

            question_states = assembler.question_states_for_coverage()
            threshold = getattr(self._settings, "COVERAGE_GREEN_THRESHOLD", 0.7)
            full_coverage = compute_coverage(question_states, threshold)

            incremental = await self._load_incremental_coverage(
                tenant.tenant_id, session_id
            )
            tolerance = getattr(self._settings, "COVERAGE_CROSSCHECK_TOLERANCE", 0.05)
            differences = crosscheck_coverage(
                full_coverage, incremental, tolerance=tolerance
            )
            for diff in differences:
                logger.warning(
                    "process_coverage_difference",
                    job_id=job_id,
                    workflow=diff.workflow,
                    full_pct=diff.full_pct,
                    incremental_pct=diff.incremental_pct,
                    delta=diff.delta,
                    cause=diff.cause,
                )

            # ── J-03: field extraction ────────────────────────────
            from app.logic.field_extractor import (
                ExtractionResult,
                FieldExtractor,
                StepBudgetExceeded,
            )
            from app.logic.field_types import WIZARD_PAGES

            extraction = ExtractionResult()
            company_id = evidence.company_id

            if self._llm is not None and self._backend is not None:
                # PG-01: emit plan before any tool call
                logger.info(
                    "pg01_plan_emitted",
                    job_id=job_id,
                    pages=sorted(WIZARD_PAGES.keys()),
                    field_count=sum(
                        len(fields) for _label, fields in WIZARD_PAGES.values()
                    ),
                    step_budget=getattr(self._settings, "EXTRACTION_MAX_STEPS", 40),
                )

                existing_provenance = await self._backend.get_existing_provenance(
                    tenant_id=tenant.tenant_id,
                    session_id=session_id,
                )

                try:
                    extractor = FieldExtractor(
                        llm=self._llm,
                        settings=self._settings,
                    )
                    extraction = await extractor.extract_all(
                        evidence_blocks=evidence.blocks,
                        existing_provenance=existing_provenance,
                        valid_recording_ids=evidence.valid_recording_ids,
                        valid_media_ids=evidence.valid_media_ids,
                        tenant_id=tenant.tenant_id,
                    )
                except StepBudgetExceeded as exc:
                    logger.error(
                        "process_step_budget_exceeded",
                        job_id=job_id,
                        error=str(exc),
                    )
                    extraction = ExtractionResult()
                except GuardrailViolation as exc:
                    logger.error(
                        "process_guardrail_violation",
                        job_id=job_id,
                        rule_id=exc.verdict.rule_id,
                        action=exc.verdict.action.value,
                        detail=exc.verdict.detail,
                    )
                    raise

                # Write back to Django
                if extraction.fields_written and company_id is not None:
                    field_values = {
                        f["field_name"]: f["value"] for f in extraction.fields_written
                    }
                    await self._backend.patch_company_fields(
                        tenant_id=tenant.tenant_id,
                        company_id=company_id,
                        fields=field_values,
                    )

                    provenance_records = [
                        {
                            "model_name": f["model_name"],
                            "field_name": f["field_name"],
                            "extracted_value": f["value"],
                            "confidence": f["confidence"],
                            "classification": f["classification"],
                            "source_span": (
                                f["evidence"][0] if f["evidence"] else None
                            ),
                        }
                        for f in extraction.fields_written
                    ]
                    await self._backend.create_provenance_bulk(
                        tenant_id=tenant.tenant_id,
                        session_id=session_id,
                        records=provenance_records,
                    )

                # J-05: handle conflicts — create CONFLICT provenance,
                # publish escalations, emit EVT-007
                if extraction.conflicts:
                    await self._handle_conflicts(
                        conflicts=extraction.conflicts,
                        tenant=tenant,
                        session_id=session_id,
                        job_id=job_id,
                    )

            conflict_summary = self._sanitise_conflicts(extraction.conflicts)

            summary: dict[str, Any] = {
                "extraction_complete": True,
                "evidence_blocks": len(evidence.blocks),
                "compressed": evidence.compressed,
                "token_estimate": evidence.token_estimate,
                "missing_media": evidence.missing_media,
                "coverage": full_coverage.as_map(),
                "coverage_satisfied": full_coverage.satisfied,
                "blocking_gaps": full_coverage.blocking_gaps,
                "degraded_questions": evidence.degraded_question_ids,
                "fields_written": len(extraction.fields_written),
                "fields_skipped": len(extraction.fields_skipped),
                "conflicts": conflict_summary,
                "dropped_ungrounded": extraction.dropped_ungrounded_total,
                "steps_used": extraction.steps_used,
            }
            cb_status = JOB_STATUS_SUCCEEDED

        except GuardrailViolation as exc:
            logger.error(
                "process_guardrail_block",
                job_id=job_id,
                session_id=session_id,
                rule_id=exc.verdict.rule_id,
                action=exc.verdict.action.value,
                detail=exc.verdict.detail,
            )
            summary = {
                "error": str(exc),
                "guardrail_violation": {
                    "rule_id": exc.verdict.rule_id,
                    "action": exc.verdict.action.value,
                    "detail": exc.verdict.detail,
                },
            }
            cb_status = JOB_STATUS_FAILED

        except Exception as exc:
            logger.error(
                "process_job_failed",
                job_id=job_id,
                session_id=session_id,
                error=str(exc),
            )
            summary = {"error": str(exc)}
            cb_status = JOB_STATUS_FAILED

        await self._redis.client.set(
            job_key,
            json.dumps({"job_id": job_id, "status": cb_status}),
            ex=JOB_TTL,
        )

        if self._backend is not None and callback_url:
            await self._callback(
                callback_url=callback_url,
                tenant_id=tenant.tenant_id,
                job_id=job_id,
                status=cb_status,
                summary=summary,
            )

    async def _handle_conflicts(
        self,
        *,
        conflicts: list[dict[str, Any]],
        tenant: TenantContext,
        session_id: str,
        job_id: str,
    ) -> None:
        """J-05: create CONFLICT provenance, publish escalations, emit EVT-007."""
        # 1. Create CONFLICT provenance records
        if self._backend is not None:
            conflict_provenance = [
                {
                    "model_name": "Company",
                    "field_name": c["field_name"],
                    "extracted_value": c["new_value"],
                    "confidence": c.get("new_confidence"),
                    "classification": c.get("new_classification"),
                    "source_span": (
                        c["new_evidence"][0] if c.get("new_evidence") else None
                    ),
                    "status": "CONFLICT",
                }
                for c in conflicts
            ]
            await self._backend.create_provenance_bulk(
                tenant_id=tenant.tenant_id,
                session_id=session_id,
                records=conflict_provenance,
            )

        # 2. Build and publish EscalationMessages
        for c in conflicts:
            candidates = self._build_candidates(c)
            msg = EscalationMessage(
                tenant_id=uuid.UUID(tenant.tenant_id),
                session_id=uuid.UUID(session_id) if session_id else None,
                reason_code="FIELD_CONFLICT",
                field_name=c["field_name"],
                confidence=c.get("new_confidence"),
                candidates=candidates,
                context_ref=f"job:{job_id}",
            )

            if self._kafka is not None:
                try:
                    payload = msg.model_dump_json().encode()
                    key = message_key(tenant.tenant_id, session_id)
                    await self._kafka.send(ESCALATIONS.name, key=key, value=payload)
                except Exception as exc:
                    logger.warning(
                        "escalation_publish_failed",
                        field=c["field_name"],
                        error=str(exc),
                    )

            # 3. Emit EVT-007
            if self._events is not None:
                try:
                    await self._events.emit(
                        EventType.AGENT_ESCALATED,
                        tenant_id=tenant.tenant_id,
                        correlation_id=job_id,
                        session_id=session_id,
                        payload={
                            "escalation_id": str(msg.escalation_id),
                            "reason_code": msg.reason_code,
                            "field_name": c["field_name"],
                            "candidate_count": len(candidates),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "evt007_emit_failed",
                        field=c["field_name"],
                        error=str(exc),
                    )

        logger.info(
            "conflicts_escalated",
            job_id=job_id,
            count=len(conflicts),
        )

    @staticmethod
    def _build_candidates(conflict: dict[str, Any]) -> list[ConflictCandidate]:
        """Build ConflictCandidate list from an enriched conflict dict."""
        candidates: list[ConflictCandidate] = []

        existing_span = conflict.get("existing_source_span")
        if existing_span:
            ref = _format_evidence_ref(existing_span)
        else:
            ref = f"provenance:{conflict['field_name']}"
        candidates.append(
            ConflictCandidate(
                source="existing",
                evidence_ref=ref,
                confidence=conflict.get("existing_confidence"),
            )
        )

        new_evidence = conflict.get("new_evidence", [])
        new_ref = (
            _format_evidence_ref(new_evidence[0])
            if new_evidence
            else f"extraction:{conflict['field_name']}"
        )
        candidates.append(
            ConflictCandidate(
                source="new",
                evidence_ref=new_ref,
                confidence=conflict.get("new_confidence"),
                classification=conflict.get("new_classification"),
            )
        )

        return candidates

    @staticmethod
    def _sanitise_conflicts(
        conflicts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Strip values from conflict records for the callback summary."""
        return [
            {
                "field_name": c["field_name"],
                "existing_status": c["existing_status"],
                "new_confidence": c.get("new_confidence"),
                "new_classification": c.get("new_classification"),
            }
            for c in conflicts
        ]

    async def _load_incremental_coverage(
        self, tenant_id: str, session_id: str
    ) -> dict[str, Any] | None:
        """Load incremental coverage values stored by G-06 during LIVE."""
        keys = self._redis.keys_for(tenant_id)
        cov_key = keys.coverage(session_id)
        try:
            raw = await self._redis.client.hgetall(  # type: ignore[misc,unused-ignore]
                cov_key
            )
        except Exception:
            logger.warning(
                "process_incremental_coverage_failed",
                session_id=session_id,
            )
            return None
        if not raw:
            return None
        return {str(k): v for k, v in raw.items()}

    async def _callback(
        self,
        *,
        callback_url: str,
        tenant_id: str,
        job_id: str,
        status: str,
        summary: dict[str, Any],
    ) -> None:
        """POST the terminal result back to Django via BackendClient."""
        if self._backend is None:
            logger.error("process_callback_no_backend", job_id=job_id)
            return

        from urllib.parse import urlparse

        parsed = urlparse(callback_url)
        path = parsed.path
        result = await self._backend._post(
            path,
            {"job_id": job_id, "status": status, "summary": summary},
            tenant_id=tenant_id,
        )
        if result is None:
            logger.error(
                "process_callback_failed",
                job_id=job_id,
                callback_url=callback_url,
            )

    async def _check_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(f"process:{idempotency_key}")
        raw = await self._redis.client.get(key)
        if raw is None:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            return data
        except (json.JSONDecodeError, TypeError):
            return None

    async def _store_idempotency(
        self, tenant_id: str, idempotency_key: str, response: dict[str, Any]
    ) -> None:
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(f"process:{idempotency_key}")
        await self._redis.client.set(key, json.dumps(response), ex=TTL_IDEMPOTENCY)
