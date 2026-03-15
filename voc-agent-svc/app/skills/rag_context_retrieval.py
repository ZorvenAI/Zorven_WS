"""SKL-VoCA-08: RAG Context Retrieval — Prior VoC reports from tenant RAG store."""

import logging
import time
from typing import Any

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class RAGContextRetrieval(BaseSkill):
    """Retrieve prior VoC reports and historical data from tenant-scoped RAG store."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-08",
        name="rag_context_retrieval",
        description=(
            "Retrieves prior VoC reports and historical feedback data "
            "from the tenant-scoped RAG store for longitudinal analysis "
            "and trend comparison."
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

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Retrieve prior VoC reports from the tenant RAG store.

        input_data keys:
          - company_name (str): Brand/company name for scoped retrieval
          - prompt (str): Search query for RAG retrieval
          - top_k (int): Number of chunks to retrieve (default 5)
        """
        start = time.monotonic()
        company_name = input_data.get("company_name", "")
        prompt = input_data.get("prompt", "")
        top_k = input_data.get("top_k", 5)

        if not self.rag_enabled:
            logger.info("RAG disabled — skipping VoC context retrieval")
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "chunks": [],
                    "retrieval_score": 0.0,
                    "sources": [],
                    "rag_enabled": False,
                    "message": "RAG retrieval disabled",
                },
                duration_ms=_elapsed(start),
            )

        # Build retrieval query from company name and prompt
        query = prompt or company_name
        if company_name and prompt:
            query = f"{company_name} voice of customer {prompt}"
        elif company_name:
            query = f"{company_name} voice of customer feedback analysis"

        if not query:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided for RAG retrieval",
                duration_ms=_elapsed(start),
            )

        try:
            chunks = await self._retrieve_chunks(query, context.tenant_id, top_k)

            # Compute average retrieval score
            retrieval_score = 0.0
            if chunks:
                scores = [c.get("score", 0.0) for c in chunks]
                retrieval_score = sum(scores) / len(scores)

            # Build sources from chunk metadata
            sources: list[dict[str, str]] = []
            for chunk in chunks:
                meta = chunk.get("metadata", {})
                source_url = meta.get("source_url", "")
                source_title = meta.get("title", meta.get("report_type", ""))
                if source_url or source_title:
                    sources.append(
                        {
                            "type": "rag",
                            "title": source_title,
                            "url": source_url,
                        }
                    )

            logger.info(
                "RAG retrieval for '%s': %d chunks, avg score %.3f",
                company_name or query[:50],
                len(chunks),
                retrieval_score,
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "chunks": chunks,
                    "retrieval_score": retrieval_score,
                    "sources": sources,
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
        """Call RAG service to retrieve relevant VoC document chunks."""
        url = f"{self.rag_service_url}/v1/retrieve"
        payload = {
            "query": query,
            "top_k": top_k,
            "filters": {
                "tenant_id": tenant_id,
                "content_type": "voice_of_customer",
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
