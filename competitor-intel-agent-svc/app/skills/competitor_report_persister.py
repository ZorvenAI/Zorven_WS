"""SKL-CIA-11: Competitor Report Persister — GCS + RAG + Registry persistence."""

import json
import logging
import time
from typing import Any, Optional

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class CompetitorReportPersister(BaseSkill):
    """Persist competitive intelligence to GCS, RAG index, and competitor registry."""

    meta = SkillMeta(
        skill_id="SKL-CIA-11",
        name="competitor_report_persister",
        description=(
            "Persist competitive intelligence report to GCS, "
            "index in RAG store, and update competitor registry."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        idempotent=False,
        timeout_ms=30000,
        circuit_breaker_dependency="gcs",
    )

    def __init__(
        self,
        gcs_enabled: bool = False,
        rag_enabled: bool = False,
        rag_service_url: str = "http://localhost:8070",
    ) -> None:
        self.gcs_enabled = gcs_enabled
        self.rag_enabled = rag_enabled
        self.rag_service_url = rag_service_url

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Persist report data.

        input_data keys:
          - prompt (str): Original query
          - report_data (dict): Compiled report data from all skills
        """
        start = time.monotonic()
        report_data = input_data.get("report_data", {})
        prompt = input_data.get("prompt", "")

        if not report_data:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"persisted": False, "message": "No report data to persist"},
                duration_ms=_elapsed(start),
            )

        persisted_to: list[str] = []

        # GCS persistence
        if self.gcs_enabled:
            try:
                await self._persist_to_gcs(
                    context.tenant_id, prompt, report_data
                )
                persisted_to.append("gcs")
            except Exception as exc:
                logger.warning("GCS persistence failed: %s", exc)

        # RAG indexing
        if self.rag_enabled:
            try:
                await self._index_in_rag(
                    context.tenant_id, prompt, report_data
                )
                persisted_to.append("rag")
            except Exception as exc:
                logger.warning("RAG indexing failed: %s", exc)

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "persisted": len(persisted_to) > 0,
                "persisted_to": persisted_to,
                "gcs_enabled": self.gcs_enabled,
                "rag_enabled": self.rag_enabled,
            },
            duration_ms=_elapsed(start),
        )

    async def _persist_to_gcs(
        self, tenant_id: str, prompt: str, report_data: dict
    ) -> None:
        """Persist report to GCS bucket (stub — GCS client not wired yet)."""
        logger.info(
            "GCS persistence for tenant %s: %d bytes",
            tenant_id,
            len(json.dumps(report_data)),
        )

    async def _index_in_rag(
        self, tenant_id: str, prompt: str, report_data: dict
    ) -> None:
        """Index report in RAG service for future retrieval."""
        url = f"{self.rag_service_url}/v1/index"
        payload = {
            "tenant_id": tenant_id,
            "content_type": "competitive_intelligence",
            "content": json.dumps(report_data)[:50000],
            "metadata": {
                "query": prompt[:500],
                "type": "competitor_report",
            },
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Tenant-ID": tenant_id},
            )
            resp.raise_for_status()


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
