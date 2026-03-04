"""Generic ORM tools — 8 foundational tools for any Odoo model."""

from typing import Any, Optional

from app.tools.base import BaseTool


class OdooSearchTool(BaseTool):
    name = "odoo_search"
    description = "Search Odoo records by domain filter, returns list of IDs"
    domain = "generic"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "Odoo model name"},
            "domain": {
                "type": "array",
                "description": "Odoo domain filter",
                "default": [],
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
            "order": {"type": "string", "default": ""},
        },
        "required": ["model"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "ids": []}
        model = arguments["model"]
        domain = arguments.get("domain", [])
        rbac_domain = arguments.pop("_rbac_domain", [])
        if rbac_domain:
            domain = domain + rbac_domain
        ids = await rpc_client.execute_kw(
            model,
            "search",
            [domain],
            {
                "limit": arguments.get("limit", 80),
                "offset": arguments.get("offset", 0),
                "order": arguments.get("order", ""),
            },
        )
        return {"model": model, "ids": ids, "count": len(ids)}


class OdooReadTool(BaseTool):
    name = "odoo_read"
    description = "Read Odoo records by IDs, returns field values"
    domain = "generic"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "ids": {"type": "array", "items": {"type": "integer"}},
            "fields": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        "required": ["model", "ids"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        records = await rpc_client.execute_kw(
            arguments["model"],
            "read",
            [arguments["ids"]],
            {"fields": arguments.get("fields", [])},
        )
        return {"model": arguments["model"], "records": records}


class OdooCreateTool(BaseTool):
    name = "odoo_create"
    description = "Create a new Odoo record"
    domain = "generic"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "values": {"type": "object"},
        },
        "required": ["model", "values"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        record_id = await rpc_client.create(arguments["model"], arguments["values"])
        return {"model": arguments["model"], "id": record_id}


class OdooWriteTool(BaseTool):
    name = "odoo_write"
    description = "Update existing Odoo records"
    domain = "generic"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "ids": {"type": "array", "items": {"type": "integer"}},
            "values": {"type": "object"},
        },
        "required": ["model", "ids", "values"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        success = await rpc_client.write(
            arguments["model"], arguments["ids"], arguments["values"]
        )
        return {
            "model": arguments["model"],
            "ids": arguments["ids"],
            "success": success,
        }


class OdooDeleteTool(BaseTool):
    name = "odoo_delete"
    description = "Delete Odoo records by IDs"
    domain = "generic"
    required_operation = "unlink"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "ids": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["model", "ids"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        success = await rpc_client.unlink(arguments["model"], arguments["ids"])
        return {
            "model": arguments["model"],
            "ids": arguments["ids"],
            "deleted": success,
        }


class OdooSearchReadTool(BaseTool):
    name = "odoo_search_read"
    description = "Search and read Odoo records in a single call"
    domain = "generic"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "domain": {"type": "array", "default": []},
            "fields": {"type": "array", "items": {"type": "string"}, "default": []},
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
            "order": {"type": "string", "default": ""},
        },
        "required": ["model"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain = arguments.get("domain", [])
        rbac_domain = arguments.pop("_rbac_domain", [])
        if rbac_domain:
            domain = domain + rbac_domain
        records = await rpc_client.search_read(
            arguments["model"],
            domain,
            fields=arguments.get("fields"),
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
            order=arguments.get("order", ""),
        )
        return {"model": arguments["model"], "records": records, "count": len(records)}


class OdooGetFieldsTool(BaseTool):
    name = "odoo_get_fields"
    description = "Get field definitions for an Odoo model"
    domain = "generic"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "attributes": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["string", "type", "required", "readonly"],
            },
        },
        "required": ["model"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "fields": {}}
        fields = await rpc_client.fields_get(
            arguments["model"],
            attributes=arguments.get("attributes"),
        )
        return {"model": arguments["model"], "fields": fields}


class OdooExecuteMethodTool(BaseTool):
    name = "odoo_execute_method"
    description = "Execute an arbitrary Odoo ORM method on a model"
    domain = "generic"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "method": {"type": "string"},
            "args": {"type": "array", "default": []},
            "kwargs": {"type": "object", "default": {}},
        },
        "required": ["model", "method"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        result = await rpc_client.execute_kw(
            arguments["model"],
            arguments["method"],
            arguments.get("args", []),
            arguments.get("kwargs"),
        )
        return {
            "model": arguments["model"],
            "method": arguments["method"],
            "result": result,
        }


# Convenience: all generic tools for registration
ALL_GENERIC_TOOLS = [
    OdooSearchTool(),
    OdooReadTool(),
    OdooCreateTool(),
    OdooWriteTool(),
    OdooDeleteTool(),
    OdooSearchReadTool(),
    OdooGetFieldsTool(),
    OdooExecuteMethodTool(),
]
