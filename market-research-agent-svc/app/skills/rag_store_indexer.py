"""SKL-MRA-07: RAG Store Indexer — Index content into RAG service."""

import logging
import time

import httpx

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class RAGStoreIndexer(BaseSkill):
    """Indexes research content into the RAG uploader agent service."""

    meta = SkillMeta(
        skill_id="SKL-MRA-07",
        name="rag_store_indexer",
        description="Index research content into RAG vector store",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=30000,
        circuit_breaker_dependency="rag_store",
    )

    def __init__(self, rag_service_url: str, enabled: bool = False) -> None:
        self.rag_service_url = rag_service_url.rstrip("/")
        self.enabled = enabled

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Index content into RAG store.

        input_data keys:
          - content (str): Text content to index
          - metadata (dict): Metadata for the content
          - chunk_type (str): Type of content (e.g. 'research_report')
        """
        start = time.monotonic()

        if not self.enabled:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "indexed_count": 0,
                    "skipped": True,
                    "reason": "RAG service disabled",
                },
                duration_ms=_elapsed(start),
            )

        content = input_data.get("content", "")
        metadata = input_data.get("metadata", {})
        chunk_type = input_data.get("chunk_type", "research_report")

        if not content:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No content provided for indexing",
                duration_ms=_elapsed(start),
            )

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{self.rag_service_url}/v1/index",
                    json={
                        "content": content,
                        "metadata": {
                            **metadata,
                            "tenant_id": context.tenant_id,
                            "chunk_type": chunk_type,
                            "source": "market-research-agent",
                        },
                    },
                    headers={"X-Tenant-ID": context.tenant_id},
                )
                resp.raise_for_status()
                data = resp.json()

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "indexed_count": data.get("indexed_count", 1),
                    "vector_ids": data.get("vector_ids", []),
                    "data_store_id": data.get("data_store_id", ""),
                },
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("RAGStoreIndexer failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
