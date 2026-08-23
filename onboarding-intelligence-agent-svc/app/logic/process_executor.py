"""PROCESS mode job orchestration.

Design §9.3 · implemented by story J-01.

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
from app.services.backend_client import BackendClient
from app.skills.models import TenantContext

logger = get_logger(__name__)

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
    ) -> None:
        self._redis = redis
        self._backend = backend
        self._settings = settings
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
        """Execute the PROCESS job and call back to Django.

        J-01 delivers a stub that immediately succeeds. J-02 replaces the
        body with real extraction logic.
        """
        keys = self._redis.keys_for(tenant.tenant_id)
        job_key = keys.idempotency(f"process:job:{job_id}")

        try:
            await self._redis.client.set(
                job_key,
                json.dumps({"job_id": job_id, "status": JOB_STATUS_RUNNING}),
                ex=JOB_TTL,
            )

            # J-02 replaces this with real extraction.
            summary: dict[str, Any] = {
                "extraction_complete": False,
                "detail": "Stub: J-02 implements actual field extraction.",
            }
            cb_status = JOB_STATUS_SUCCEEDED

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
