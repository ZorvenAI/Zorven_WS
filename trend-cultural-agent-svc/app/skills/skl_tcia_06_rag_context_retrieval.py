"""SKL-TCIA-06: RAG Context Retrieval.

Retrieves prior trend reports from the RAG service for historical comparison.
"""

import logging
import time
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class RAGContextRetrieval(BaseSkill):
    """Retrieve prior trend analyses from the RAG knowledge base."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-06",
        name="rag_context_retrieval",
        description="Retrieve prior trend reports from RAG for historical comparison",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=10000,
        circuit_breaker_dependency="rag_store",
    )

    def __init__(
        self,
        rag_service_url: str = "",
        cb_rag: Any = None,
    ) -> None:
        self._rag_url = rag_service_url
        self._cb_rag = cb_rag

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()

        if not self._rag_url:
            logger.info("RAG service URL not configured, skipping retrieval")
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"chunks": [], "chunk_count": 0, "retrieval_score": 0.0},
                duration_ms=(time.monotonic() - start) * 1000,
            )

        query = input_data.get("prompt", "trend analysis")
        top_k = input_data.get("top_k", 5)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
                payload = {
                    "query": query,
                    "top_k": top_k,
                    "tenant_id": context.tenant_id,
                }
                response = await client.post(
                    f"{self._rag_url}/v1/retrieve", json=payload
                )
                response.raise_for_status()
                data = response.json()
                chunks = data.get("chunks", [])
                return SkillResult(
                    skill_id=self.meta.skill_id,
                    success=True,
                    data={
                        "chunks": chunks,
                        "chunk_count": len(chunks),
                        "retrieval_score": data.get("score", 0.0),
                    },
                    duration_ms=(time.monotonic() - start) * 1000,
                )
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"chunks": [], "chunk_count": 0, "retrieval_score": 0.0},
                error=str(exc),
                duration_ms=(time.monotonic() - start) * 1000,
            )
