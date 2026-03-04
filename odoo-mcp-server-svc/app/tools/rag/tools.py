"""RAG tools — 8 tools for knowledge store operations."""

from typing import Any, Optional

from app.tools.base import BaseTool


class QueryKnowledgeTool(BaseTool):
    name = "rag_query_knowledge"
    description = "Search the RAG knowledge store with a natural language query"
    domain = "rag"
    required_model = ""
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available", "results": []}
        tenant_id = ctx.get("tenant_id", "default")
        return await rag_client.query(
            arguments["query"], tenant_id=tenant_id, top_k=arguments.get("top_k", 5)
        )


class UploadDocumentTool(BaseTool):
    name = "rag_upload_document"
    description = "Upload a document to the RAG knowledge store"
    domain = "rag"
    required_model = ""
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Document content"},
            "metadata": {"type": "object", "default": {}},
        },
        "required": ["content"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available"}
        tenant_id = ctx.get("tenant_id", "default")
        return await rag_client.upload_document(
            arguments["content"],
            arguments.get("metadata", {}),
            tenant_id=tenant_id,
        )


class ListDocumentsTool(BaseTool):
    name = "rag_list_documents"
    description = "List all documents in the RAG knowledge store"
    domain = "rag"
    required_model = ""
    required_operation = "read"
    input_schema = {"type": "object", "properties": {}}

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available", "documents": []}
        tenant_id = ctx.get("tenant_id", "default")
        return await rag_client.list_documents(tenant_id=tenant_id)


class DeleteDocumentTool(BaseTool):
    name = "rag_delete_document"
    description = "Delete a document from the RAG knowledge store"
    domain = "rag"
    required_model = ""
    required_operation = "unlink"
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Document ID to delete"},
        },
        "required": ["doc_id"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available"}
        tenant_id = ctx.get("tenant_id", "default")
        return await rag_client.delete_document(
            arguments["doc_id"], tenant_id=tenant_id
        )


class EnrichContextTool(BaseTool):
    name = "rag_enrich_context"
    description = "Enrich a query with RAG knowledge context"
    domain = "rag"
    required_model = ""
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "model": {"type": "string", "default": ""},
        },
        "required": ["query"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available"}
        tenant_id = ctx.get("tenant_id", "default")
        result = await rag_client.query(
            arguments["query"], tenant_id=tenant_id, top_k=3
        )
        results = result.get("results", [])
        context_text = "\n\n".join(
            r.get("text", r.get("content", "")) for r in results[:3]
        )
        return {"context": context_text, "sources": len(results)}


class IndexOdooRecordTool(BaseTool):
    name = "rag_index_odoo_record"
    description = "Index an Odoo record into the RAG knowledge store"
    domain = "rag"
    required_model = ""
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "Odoo model name"},
            "record_id": {"type": "integer", "description": "Record ID"},
        },
        "required": ["model", "record_id"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_sync = ctx.get("rag_sync")
        if rag_sync is None:
            return {"error": "RAG sync not available"}
        tenant_id = ctx.get("tenant_id", "default")
        return await rag_sync.sync_record(
            arguments["model"], arguments["record_id"], tenant_id
        )


class SearchByMetadataTool(BaseTool):
    name = "rag_search_by_metadata"
    description = "Search RAG documents by metadata filters"
    domain = "rag"
    required_model = ""
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "Filter by Odoo model"},
            "query": {"type": "string", "default": ""},
        },
        "required": ["model"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available", "results": []}
        tenant_id = ctx.get("tenant_id", "default")
        query = f"model:{arguments['model']} {arguments.get('query', '')}"
        return await rag_client.query(query, tenant_id=tenant_id, top_k=10)


class GetStoreStatsTool(BaseTool):
    name = "rag_get_store_stats"
    description = "Get RAG knowledge store statistics and health"
    domain = "rag"
    required_model = ""
    required_operation = "read"
    input_schema = {"type": "object", "properties": {}}

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rag_client = ctx.get("rag_client")
        if rag_client is None:
            return {"error": "RAG client not available"}
        tenant_id = ctx.get("tenant_id", "default")
        return await rag_client.get_stats(tenant_id=tenant_id)


ALL_RAG_TOOLS = [
    QueryKnowledgeTool(),
    UploadDocumentTool(),
    ListDocumentsTool(),
    DeleteDocumentTool(),
    EnrichContextTool(),
    IndexOdooRecordTool(),
    SearchByMetadataTool(),
    GetStoreStatsTool(),
]
