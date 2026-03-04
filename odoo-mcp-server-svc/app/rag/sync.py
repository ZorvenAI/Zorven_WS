"""Odoo-RAG sync — indexes Odoo records into the RAG knowledge store.

Supports event-driven sync (via Kafka) and periodic nightly sync
for configured models.
"""

import logging
from typing import Any, Optional

from app.core.config import settings
from app.rag.client import RAGClient

logger = logging.getLogger(__name__)

# Models that can be indexed into RAG
INDEXABLE_MODELS = [
    "product.template",
    "product.product",
    "sale.order",
    "purchase.order",
    "account.move",
    "hr.employee",
    "project.project",
    "crm.lead",
    "res.partner",
]


class OdooRAGSync:
    """Syncs Odoo records to the RAG knowledge store."""

    def __init__(
        self,
        rag_client: Optional[RAGClient] = None,
        rpc_client: Optional[Any] = None,
    ) -> None:
        self.rag_client = rag_client
        self.rpc_client = rpc_client

    async def sync_record(
        self,
        model: str,
        record_id: int,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Sync a single Odoo record to RAG store."""
        if self.rag_client is None or self.rpc_client is None:
            return {"error": "RAG or RPC client not available"}

        if model not in INDEXABLE_MODELS:
            return {"error": f"Model {model} is not indexable"}

        try:
            # Read the record from Odoo
            records = await self.rpc_client.search_read(
                model, [["id", "=", record_id]], limit=1
            )
            if not records:
                return {"error": f"Record {model}/{record_id} not found"}

            record = records[0]

            # Build document content
            content = self._build_document_content(model, record)
            metadata = {
                "source": "odoo",
                "model": model,
                "record_id": record_id,
                "tenant_id": tenant_id,
                "name": record.get("name", record.get("display_name", "")),
            }

            # Upload to RAG
            result = await self.rag_client.upload_document(
                content=content,
                metadata=metadata,
                tenant_id=tenant_id,
            )
            return {"synced": True, "model": model, "record_id": record_id, **result}

        except Exception as exc:
            logger.error("Failed to sync %s/%d: %s", model, record_id, exc)
            return {"error": str(exc)}

    async def sync_model(
        self,
        model: str,
        tenant_id: str = "default",
        limit: int = 100,
        domain: Optional[list] = None,
    ) -> dict[str, Any]:
        """Sync all records of a model to RAG store."""
        if self.rag_client is None or self.rpc_client is None:
            return {"error": "RAG or RPC client not available"}

        domain = domain or []
        synced = 0
        errors = 0

        try:
            records = await self.rpc_client.search_read(model, domain, limit=limit)
            for record in records:
                try:
                    content = self._build_document_content(model, record)
                    await self.rag_client.upload_document(
                        content=content,
                        metadata={
                            "source": "odoo",
                            "model": model,
                            "record_id": record["id"],
                            "tenant_id": tenant_id,
                        },
                        tenant_id=tenant_id,
                    )
                    synced += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to sync %s/%d: %s",
                        model,
                        record.get("id", 0),
                        exc,
                    )
                    errors += 1

        except Exception as exc:
            logger.error("Failed to sync model %s: %s", model, exc)
            return {"error": str(exc)}

        return {"model": model, "synced": synced, "errors": errors}

    async def handle_record_change(self, event: dict[str, Any]) -> None:
        """Handle a Kafka event for an Odoo record change."""
        model = event.get("model", "")
        record_id = event.get("record_id", 0)
        tenant_id = event.get("tenant_id", "default")
        action = event.get("action", "update")

        if action == "delete":
            logger.info("Record deleted: %s/%d — skipping RAG sync", model, record_id)
            return

        if model in INDEXABLE_MODELS:
            await self.sync_record(model, record_id, tenant_id)

    @staticmethod
    def _build_document_content(model: str, record: dict[str, Any]) -> str:
        """Build a text representation of an Odoo record for RAG indexing."""
        parts = [f"Model: {model}"]
        for key, value in record.items():
            if key == "id" or value is False or value is None:
                continue
            if isinstance(value, (list, tuple)) and len(value) == 2:
                # Many2one field: [id, display_name]
                parts.append(f"{key}: {value[1]}")
            elif isinstance(value, str) and len(value) > 500:
                parts.append(f"{key}: {value[:500]}...")
            else:
                parts.append(f"{key}: {value}")
        return "\n".join(parts)
