"""RAG context middleware — enriches tool calls with knowledge store context.

Intercepts tools annotated with rag_context_enabled=True, builds a semantic
query from tool parameters, and injects retrieved context as background_context.
"""

import logging
from typing import Any, Optional

from app.core.config import settings
from app.rag.client import RAGClient

logger = logging.getLogger(__name__)


class RAGContextMiddleware:
    """Enriches tool calls with RAG knowledge context."""

    def __init__(self, rag_client: Optional[RAGClient] = None) -> None:
        self.rag_client = rag_client

    async def enrich(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Optionally enrich tool arguments with RAG context.

        Returns the (possibly modified) arguments dict with
        'background_context' injected.
        """
        if not settings.RAG_ENABLED or self.rag_client is None:
            return arguments

        # Build semantic query from tool arguments
        query_parts = []
        for key in ("model", "name", "query", "input_prompt", "search_term"):
            if key in arguments:
                query_parts.append(str(arguments[key]))

        # Optionally include input_prompt from context
        context_input_prompt = context.get("input_prompt")
        if context_input_prompt:
            query_parts.append(str(context_input_prompt))

        if not query_parts:
            return arguments

        query = " ".join(query_parts)[:500]
        tenant_id = context.get("tenant_id", "default")

        try:
            result = await self.rag_client.query(
                query=query, tenant_id=tenant_id, top_k=3
            )
            results = result.get("results", [])
            if results:
                context_text = "\n\n".join(
                    r.get("text", r.get("content", "")) for r in results[:3]
                )
                # Truncate to max tokens (rough estimate: 4 chars per token)
                max_chars = settings.RAG_CONTEXT_MAX_TOKENS * 4
                if len(context_text) > max_chars:
                    context_text = context_text[:max_chars]
                arguments["background_context"] = context_text
                logger.info(
                    "RAG context injected for %s (%d chars)",
                    tool_name,
                    len(context_text),
                )
        except Exception as exc:
            logger.warning("RAG context enrichment failed: %s", exc)

        return arguments
