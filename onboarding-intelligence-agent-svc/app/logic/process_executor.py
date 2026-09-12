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
from app.cache.idempotency import IdempotencyGuard
from app.cache.redis_manager import RedisManager, TTL_SESSION
from app.core.logging import get_logger
from app.events.catalog import EventType
from app.events.emitter import EventEmitter
from app.logic.guardrails import GuardrailViolation
from app.messaging.producer import KafkaProducer
from app.logic.conflict_helpers import build_candidates, format_evidence_ref
from app.messaging.schemas import (
    ConflictCandidate,
    EscalationMessage,
    ProcessOptions,
)
from app.messaging.topics import ESCALATIONS, message_key
from app.providers.llm import LLMProvider
from app.services.backend_client import BackendClient
from app.skills.models import TenantContext

logger = get_logger(__name__)

# Re-export for test compatibility
_format_evidence_ref = format_evidence_ref


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
        guard: IdempotencyGuard | None = None,
    ) -> None:
        self._redis = redis
        self._backend = backend
        self._settings = settings
        self._llm = llm
        self._kafka = kafka
        self._events = events
        self._guard = guard or IdempotencyGuard(redis)
        self._prompt_loader: Any = None
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
        cached = await self._guard.check(tenant.tenant_id, f"process:{idempotency_key}")
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

        await self._guard.store(
            tenant.tenant_id, f"process:job:{job_id}", job_state, JOB_TTL
        )

        response = ProcessResponse(
            job_id=job_id,
            status=JOB_STATUS_ACCEPTED,
            estimated_duration_s=estimated,
            callback_url=callback_url,
        )

        await self._guard.store(
            tenant.tenant_id,
            f"process:{idempotency_key}",
            response.model_dump(),
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
        return await self._guard.check(tenant_id, f"process:job:{job_id}")

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
        prompt_versions: dict[str, str] = {}

        try:
            await self._update_job_status(job_key, job_id, JOB_STATUS_RUNNING)

            # L-01: resolve and pin prompt versions before processing.
            loader = getattr(self, "_prompt_loader", None)
            if loader is not None:
                from app.prompts.mapping import PROCESS_PROMPTS

                resolved, degraded = await loader.resolve_for_session(
                    PROCESS_PROMPTS, tenant.tenant_id
                )
                prompt_versions = {pid: r.version for pid, r in resolved.items()}
                session_key = keys.session(session_id)
                pipe = self._redis.client.pipeline(transaction=False)
                pipe.hset(
                    session_key,
                    "prompt_versions",
                    json.dumps(prompt_versions),
                )
                pipe.expire(session_key, TTL_SESSION)
                await pipe.execute()
                if degraded and self._events is not None:
                    from app.events.catalog import EventType

                    await self._events.emit(
                        EventType.AGENT_INVOKED,
                        tenant_id=tenant.tenant_id,
                        correlation_id=job_id,
                        session_id=session_id,
                        payload={"prompt_source": "hardcoded_fallback"},
                        outcome="DEGRADED",
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

            # J-06: auto-generate brand strategy & identity
            generated: list[str] = []
            if company_id is not None:
                generated = await self._auto_generate(
                    tenant_id=tenant.tenant_id,
                    company_id=company_id,
                    options=options,
                    job_id=job_id,
                )

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
                "generated": generated,
            }
            if extraction.dropped_ungrounded_total:
                from app.metrics import DROPPED_UNGROUNDED

                DROPPED_UNGROUNDED.inc(extraction.dropped_ungrounded_total)
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

        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning(
                "process_job_cancelled",
                job_id=job_id,
                session_id=session_id,
                error=str(exc),
            )
            summary = {"error": f"Cancelled: {exc}"}
            cb_status = JOB_STATUS_FAILED
            # Decrement the cancellation counter so the cleanup awaits
            # below do not re-raise CancelledError (Python 3.12+).
            task = asyncio.current_task()
            if task is not None:
                task.uncancel()

        await self._update_job_status(job_key, job_id, cb_status)

        if self._backend is not None and callback_url:
            await self._callback(
                callback_url=callback_url,
                tenant_id=tenant.tenant_id,
                job_id=job_id,
                status=cb_status,
                summary=summary,
                prompt_versions=prompt_versions,
            )

    async def _update_job_status(
        self, job_key: str, job_id: str, status: JobStatus
    ) -> None:
        """Merge status into existing job state so accept()-time fields survive."""
        existing_raw = await self._redis.client.get(job_key)
        merged: dict[str, Any] = {}
        if existing_raw is not None:
            try:
                merged = json.loads(existing_raw)
            except (json.JSONDecodeError, TypeError):
                pass
        merged["job_id"] = job_id
        merged["status"] = status
        await self._redis.client.set(job_key, json.dumps(merged), ex=JOB_TTL)

    async def _handle_conflicts(
        self,
        *,
        conflicts: list[dict[str, Any]],
        tenant: TenantContext,
        session_id: str,
        job_id: str,
    ) -> None:
        """J-05: create CONFLICT provenance, publish escalations, emit EVT-007."""
        try:
            tenant_uuid = uuid.UUID(tenant.tenant_id)
        except (ValueError, AttributeError):
            tenant_uuid = uuid.uuid5(uuid.NAMESPACE_URL, tenant.tenant_id)
        try:
            session_uuid = uuid.UUID(session_id) if session_id else None
        except (ValueError, AttributeError):
            session_uuid = uuid.uuid5(uuid.NAMESPACE_URL, session_id)

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
            candidates = build_candidates(c)
            msg = EscalationMessage(
                tenant_id=tenant_uuid,
                session_id=session_uuid,
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

    async def _auto_generate(
        self,
        *,
        tenant_id: str,
        company_id: int,
        options: dict[str, Any],
        job_id: str,
    ) -> list[str]:
        """J-06: trigger brand strategy/identity generation after extraction."""
        generated: list[str] = []
        try:
            opts = ProcessOptions(**options) if options else ProcessOptions()
        except Exception as exc:
            logger.warning(
                "autogen_options_invalid",
                job_id=job_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            return generated

        if self._backend is None:
            return generated

        backend = self._backend

        async def _try_strategy() -> str | None:
            try:
                result = await backend.generate_brand_strategy(
                    tenant_id=tenant_id, company_id=company_id
                )
                if result is not None:
                    return "brand_strategy"
                logger.warning(
                    "autogen_strategy_failed",
                    job_id=job_id,
                    reason="backend_returned_none",
                )
            except Exception as exc:
                logger.warning(
                    "autogen_strategy_failed",
                    job_id=job_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
            return None

        async def _try_identity() -> str | None:
            try:
                result = await backend.generate_brand_identity(
                    tenant_id=tenant_id, company_id=company_id
                )
                if result is not None:
                    return "brand_identity"
                logger.warning(
                    "autogen_identity_failed",
                    job_id=job_id,
                    reason="backend_returned_none",
                )
            except Exception as exc:
                logger.warning(
                    "autogen_identity_failed",
                    job_id=job_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
            return None

        coros = []
        if opts.auto_generate_strategy:
            coros.append(_try_strategy())
        if opts.auto_generate_identity:
            coros.append(_try_identity())

        if coros:
            results = await asyncio.gather(*coros)
            generated.extend(r for r in results if r is not None)

        if generated:
            logger.info("autogen_completed", job_id=job_id, generated=generated)

        return generated

    @staticmethod
    def _build_candidates(conflict: dict[str, Any]) -> list[ConflictCandidate]:
        """Delegate to shared helper. Kept as static method for test compat."""
        return build_candidates(conflict)

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
        prompt_versions: dict[str, str] | None = None,
    ) -> None:
        """POST the terminal result back to Django via BackendClient."""
        if self._backend is None:
            logger.error("process_callback_no_backend", job_id=job_id)
            return

        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(callback_url)
        path = urlunparse(("", "", parsed.path, parsed.params, parsed.query, ""))
        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": status,
            "summary": summary,
        }
        if prompt_versions:
            payload["prompt_versions"] = prompt_versions
        result = await self._backend.send_callback(
            path,
            payload,
            tenant_id=tenant_id,
        )
        if result is None:
            logger.error(
                "process_callback_failed",
                job_id=job_id,
                callback_url=callback_url,
            )
