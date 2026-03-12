"""SKL-MRA-05: RAG Context Retrieval — Query existing RAG service."""

import logging
import time
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class RAGContextRetrieval(BaseSkill):
    """Retrieves relevant context from the RAG uploader agent service."""

    meta = SkillMeta(
        skill_id="SKL-MRA-05",
        name="rag_context_retrieval",
        description="Retrieve context from RAG vector store via rag-uploader-agent-service",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=15000,
        circuit_breaker_dependency="rag_store",
    )

    def __init__(self, rag_service_url: str, enabled: bool = False) -> None:
        self.rag_service_url = rag_service_url.rstrip("/")
        self.enabled = enabled

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Retrieve RAG context.

        input_data keys:
          - query (str): Retrieval query
          - top_k (int): Number of chunks to retrieve (default 5)
        """
        start = time.monotonic()

        if not self.enabled:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "chunks": [],
                    "retrieval_score": 0.0,
                    "skipped": True,
                    "reason": "RAG service disabled",
                },
                duration_ms=_elapsed(start),
            )

        query = input_data.get("query", "")
        top_k = input_data.get("top_k", 5)

        if not query:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided",
                duration_ms=_elapsed(start),
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.rag_service_url}/v1/retrieve",
                    json={
                        "query": query,
                        "top_k": top_k,
                        "tenant_id": context.tenant_id,
                    },
                    headers={"X-Tenant-ID": context.tenant_id},
                )
                resp.raise_for_status()
                data = resp.json()

            chunks = data.get("chunks", [])
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "chunks": chunks,
                    "retrieval_score": data.get("score", 0.0),
                    "chunk_count": len(chunks),
                },
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("RAGContextRetrieval failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
