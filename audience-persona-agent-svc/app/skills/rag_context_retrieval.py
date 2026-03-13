"""SKL-APA-06: RAG Context Retrieval — Prior persona analyses from tenant RAG store."""

import logging
import time
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class RAGContextRetrieval(BaseSkill):
    """Retrieve prior persona analyses from the tenant's RAG store."""

    meta = SkillMeta(
        skill_id="SKL-APA-06",
        name="rag_context_retrieval",
        description=(
            "Retrieves prior audience persona analyses from tenant RAG store "
            "for historical context and evolution tracking."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=30000,
        circuit_breaker_dependency="rag_store",
    )

    def __init__(
        self,
        rag_service_url: str = "http://localhost:8070",
        rag_enabled: bool = False,
    ) -> None:
        self.rag_service_url = rag_service_url
        self.rag_enabled = rag_enabled

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Retrieve prior persona analyses from RAG store.

        input_data keys:
          - prompt (str): Search query for RAG retrieval
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        top_k = input_data.get("top_k", 5)

        if not self.rag_enabled:
            logger.info("RAG disabled — skipping context retrieval")
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "chunks": [],
                    "chunk_count": 0,
                    "rag_enabled": False,
                    "message": "RAG retrieval disabled",
                },
                duration_ms=_elapsed(start),
            )

        if not prompt:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided for RAG retrieval",
                duration_ms=_elapsed(start),
            )

        try:
            chunks = await self._retrieve_chunks(prompt, context.tenant_id, top_k)

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "chunks": chunks,
                    "chunk_count": len(chunks),
                    "rag_enabled": True,
                },
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )

    async def _retrieve_chunks(
        self, query: str, tenant_id: str, top_k: int
    ) -> list[dict[str, Any]]:
        """Call RAG service to retrieve relevant document chunks."""
        url = f"{self.rag_service_url}/v1/retrieve"
        payload = {
            "query": query,
            "top_k": top_k,
            "filters": {
                "tenant_id": tenant_id,
                "content_type": "audience_persona",
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Tenant-ID": tenant_id},
            )
            resp.raise_for_status()
            data = resp.json()

        chunks = data.get("chunks", data.get("results", []))
        return [
            {
                "content": c.get("content", c.get("text", "")),
                "metadata": c.get("metadata", {}),
                "score": c.get("score", 0.0),
            }
            for c in chunks[:top_k]
        ]


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
