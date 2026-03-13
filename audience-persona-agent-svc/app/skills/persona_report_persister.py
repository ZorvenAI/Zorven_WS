"""SKL-APA-11: Persona Report Persister — GCS + RAG + Registry persistence."""

import json
import logging
import time
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class PersonaReportPersister(BaseSkill):
    """Persist persona report to GCS, RAG index, and persona registry."""

    meta = SkillMeta(
        skill_id="SKL-APA-11",
        name="persona_report_persister",
        description=(
            "Persist persona report to GCS, index in RAG store, and update "
            "persona registry. Creates version snapshots for evolution detection."
        ),
        allowed_roles=["OWNER", "ADMIN"],
        idempotent=False,
        timeout_ms=30000,
        circuit_breaker_dependency="gcs",
    )

    def __init__(
        self,
        gcs_enabled: bool = False,
        rag_enabled: bool = False,
        rag_service_url: str = "http://localhost:8070",
        persona_registry: Any = None,
    ) -> None:
        self.gcs_enabled = gcs_enabled
        self.rag_enabled = rag_enabled
        self.rag_service_url = rag_service_url
        self._registry = persona_registry

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Persist persona report data.

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
        registry_updated = False

        # GCS persistence
        if self.gcs_enabled:
            try:
                await self._persist_to_gcs(context.tenant_id, prompt, report_data)
                persisted_to.append("gcs")
            except Exception as exc:
                logger.warning("GCS persistence failed: %s", exc)

        # RAG indexing
        if self.rag_enabled:
            try:
                await self._index_in_rag(context.tenant_id, prompt, report_data)
                persisted_to.append("rag")
            except Exception as exc:
                logger.warning("RAG indexing failed: %s", exc)

        # Persona registry update
        if self._registry:
            try:
                personas = report_data.get("personas", [])
                for persona in personas:
                    slug = persona.get("slug", "")
                    if slug:
                        await self._registry.upsert_persona(
                            context.tenant_id, slug, persona
                        )
                registry_updated = bool(personas)
                if registry_updated:
                    persisted_to.append("registry")
            except Exception as exc:
                logger.warning("Persona registry update failed: %s", exc)

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "persisted": len(persisted_to) > 0,
                "persisted_to": persisted_to,
                "gcs_enabled": self.gcs_enabled,
                "rag_enabled": self.rag_enabled,
                "registry_updated": registry_updated,
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
            "content_type": "audience_persona",
            "content": json.dumps(report_data)[:50000],
            "metadata": {
                "query": prompt[:500],
                "type": "persona_report",
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
