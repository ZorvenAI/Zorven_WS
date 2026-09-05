"""SKL-OIA-11 — Register recordings, transcripts and captured media as BrandAssets.

Design §8.1 · implemented by story J-03.

After a meeting completes, the PROCESS mode calls this skill to register
each recording, transcript export, and captured media frame as a BrandAsset
through Django's internal asset registration endpoint. This triggers the
data pipeline (ingestion → curation → RAG indexing) for each asset.

Idempotent: a repeated call with the same session_id returns the cached
result from Redis rather than re-registering assets that Django already
has via its update_or_create guard.
"""

from __future__ import annotations

import json
from typing import Any

from app.cache.redis_manager import RedisManager, TTL_IDEMPOTENCY
from app.core.logging import get_logger
from app.services.backend_client import BackendClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)

SKILL_ID = "SKL-OIA-11"


class RegisterMeetingAssets(BaseSkill):
    """Register recordings, transcripts and captured media as BrandAssets."""

    def __init__(
        self,
        meta: Any,
        *,
        backend: BackendClient | None = None,
        redis: RedisManager | None = None,
    ) -> None:
        super().__init__(meta)
        self._backend = backend
        self._redis = redis

    async def run(self, context: SkillContext) -> SkillResult:
        session_id = context.input_context.get("session_id")
        tenant_id = context.tenant_context.tenant_id
        assets = context.input_context.get("assets") or []

        if not session_id:
            return SkillResult(
                skill_id=SKILL_ID,
                output={"registered": [], "error": "session_id is required"},
            )

        if not assets:
            return SkillResult(
                skill_id=SKILL_ID,
                output={"registered": [], "skipped": "no assets to register"},
            )

        if self._backend is None:
            return SkillResult(
                skill_id=SKILL_ID,
                output={"registered": [], "error": "backend client not configured"},
            )

        cached = await self._check_idempotency(tenant_id, session_id)
        if cached is not None:
            logger.info("register_assets_idempotent_hit", session_id=session_id)
            return SkillResult(skill_id=SKILL_ID, output=cached)

        registered: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            file_name = str(asset.get("file_name") or "").strip()
            if not file_name:
                continue

            result = await self._backend.register_brand_asset(
                tenant_id=tenant_id,
                file_name=file_name,
                file_type=str(asset.get("file_type") or "application/octet-stream"),
                file_size=int(asset.get("file_size") or 0),
                gcs_uri=str(asset.get("gcs_uri") or ""),
            )

            if result is not None:
                registered.append(
                    {
                        "file_name": file_name,
                        "asset_id": result.get("asset_id"),
                        "pipeline_status": result.get("pipeline_status"),
                    }
                )
            else:
                failed.append(
                    {"file_name": file_name, "reason": "backend_write_failed"}
                )

        output: dict[str, Any] = {
            "session_id": session_id,
            "registered": registered,
            "failed": failed,
            "total": len(assets),
            "registered_count": len(registered),
            "failed_count": len(failed),
        }

        if registered:
            await self._store_idempotency(tenant_id, session_id, output)

        return SkillResult(skill_id=SKILL_ID, output=output)

    # ── Idempotency ──────────────────────────────────────────────────

    async def _check_idempotency(
        self, tenant_id: str, session_id: str
    ) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(f"skl11:{session_id}")
        raw = await self._redis.client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def _store_idempotency(
        self, tenant_id: str, session_id: str, output: dict[str, Any]
    ) -> None:
        if self._redis is None:
            return
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(f"skl11:{session_id}")
        await self._redis.client.set(key, json.dumps(output), ex=TTL_IDEMPOTENCY)
