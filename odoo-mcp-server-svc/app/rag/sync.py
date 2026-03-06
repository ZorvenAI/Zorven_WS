"""Odoo-RAG sync — indexes Odoo records into the RAG knowledge store.

Supports event-driven sync (via Kafka) and periodic nightly sync
for configured models. Generates deterministic document IDs for
idempotent Vertex AI upserts.
"""

import logging
from typing import Any, Optional

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


def make_doc_id(model: str, record_id: int) -> str:
    """Generate a deterministic document ID for an Odoo record.

    Format: odoo-{model_underscore}-{record_id}
    Example: odoo-sale_order-42
    """
    model_underscore = model.replace(".", "_")
    return f"odoo-{model_underscore}-{record_id}"


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
            doc_id = make_doc_id(model, record_id)
            record_name = record.get("name", record.get("display_name", ""))

            # Build structured document content for Vertex AI
            document_content = self._build_document_content(model, record)
            metadata = {
                "source": "odoo",
                "model": model,
                "record_id": record_id,
                "tenant_id": tenant_id,
                "name": record_name,
            }

            # Upload to RAG (facade handles Vertex AI vs HTTP)
            result = await self.rag_client.upload_document(
                content=document_content,
                metadata=metadata,
                tenant_id=tenant_id,
                doc_id=doc_id,
            )
            return {
                **result,
                "synced": True,
                "model": model,
                "record_id": record_id,
                "doc_id": doc_id,
            }

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
                    record_id = record["id"]
                    doc_id = make_doc_id(model, record_id)
                    document_content = self._build_document_content(model, record)
                    metadata = {
                        "source": "odoo",
                        "model": model,
                        "record_id": record_id,
                        "tenant_id": tenant_id,
                    }
                    await self.rag_client.upload_document(
                        content=document_content,
                        metadata=metadata,
                        tenant_id=tenant_id,
                        doc_id=doc_id,
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
            if self.rag_client is not None:
                doc_id = make_doc_id(model, record_id)
                await self.rag_client.delete_document(doc_id, tenant_id=tenant_id)
            return

        if model in INDEXABLE_MODELS:
            await self.sync_record(model, record_id, tenant_id)

    @staticmethod
    def _build_document_content(model: str, record: dict[str, Any]) -> dict[str, Any]:
        """Build structured document content for Vertex AI indexing.

        Returns a dict with document_type, metadata, and extracted_text
        matching the Django backend's document format.
        """
        # Build extracted text from record fields
        text_parts = []
        record_name = ""
        for key, value in record.items():
            if key == "id" or value is False or value is None:
                continue
            if key in ("name", "display_name"):
                record_name = str(value)
            if isinstance(value, (list, tuple)) and len(value) == 2:
                # Many2one field: [id, display_name]
                text_parts.append(f"{key}: {value[1]}")
            elif isinstance(value, str) and len(value) > 500:
                text_parts.append(f"{key}: {value[:500]}...")
            else:
                text_parts.append(f"{key}: {value}")

        model_underscore = model.replace(".", "_")
        return {
            "document_type": f"odoo_{model_underscore}",
            "metadata": {
                "source": "odoo",
                "model": model,
                "record_id": record.get("id", 0),
                "name": record_name,
            },
            "extracted_text": "\n".join(text_parts),
        }
