"""Manufacturing domain tools — 8 tools for MRP operations."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateBOM(BaseTool):
    name = "manufacturing_create_bom"
    description = (
        "Create a Bill of Materials (BOM) defining components "
        "needed to manufacture a product"
    )
    domain = "manufacturing"
    required_model = "mrp.bom"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "product_tmpl_id": {
                "type": "integer",
                "description": "Product template ID to manufacture",
            },
            "product_qty": {
                "type": "number",
                "description": "Quantity produced per BOM",
                "default": 1.0,
            },
            "bom_line_ids": {
                "type": "array",
                "description": "List of BOM component lines",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "integer",
                            "description": "Component product ID",
                        },
                        "product_qty": {
                            "type": "number",
                            "description": "Quantity needed",
                        },
                    },
                    "required": ["product_id", "product_qty"],
                },
            },
            "type": {
                "type": "string",
                "description": "BOM type: normal (manufacture) or phantom (kit)",
                "enum": ["normal", "phantom"],
                "default": "normal",
            },
            "routing_id": {
                "type": "integer",
                "description": "Optional routing ID for work orders",
            },
        },
        "required": ["product_tmpl_id", "bom_line_ids"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {
            "product_tmpl_id": arguments["product_tmpl_id"],
            "product_qty": arguments.get("product_qty", 1.0),
            "type": arguments.get("type", "normal"),
        }
        if arguments.get("routing_id"):
            vals["routing_id"] = arguments["routing_id"]

        # Build one2many command tuples for bom_line_ids
        line_cmds = []
        for line in arguments["bom_line_ids"]:
            line_vals: dict[str, Any] = {
                "product_id": line["product_id"],
                "product_qty": line["product_qty"],
            }
            line_cmds.append([0, 0, line_vals])
        vals["bom_line_ids"] = line_cmds

        bom_id = await rpc_client.create("mrp.bom", vals)
        return {"bom_id": bom_id, "success": True}


class CreateProduction(BaseTool):
    name = "manufacturing_create_production"
    description = "Create a manufacturing order (production order)"
    domain = "manufacturing"
    required_model = "mrp.production"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Product to manufacture",
            },
            "product_qty": {
                "type": "number",
                "description": "Quantity to produce",
            },
            "bom_id": {
                "type": "integer",
                "description": "Bill of Materials ID to use",
            },
            "date_start": {
                "type": "string",
                "description": "Planned start date (YYYY-MM-DD HH:MM:SS)",
            },
            "date_finished": {
                "type": "string",
                "description": "Planned end date (YYYY-MM-DD HH:MM:SS)",
            },
            "origin": {
                "type": "string",
                "description": "Source document reference",
            },
        },
        "required": ["product_id", "product_qty", "bom_id"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {
            "product_id": arguments["product_id"],
            "product_qty": arguments["product_qty"],
            "bom_id": arguments["bom_id"],
        }
        if arguments.get("date_start"):
            vals["date_start"] = arguments["date_start"]
        if arguments.get("date_finished"):
            vals["date_finished"] = arguments["date_finished"]
        if arguments.get("origin"):
            vals["origin"] = arguments["origin"]

        production_id = await rpc_client.create("mrp.production", vals)
        return {"production_id": production_id, "success": True}


class StartProduction(BaseTool):
    name = "manufacturing_start_production"
    description = (
        "Start a manufacturing order by reserving components "
        "(action_assign) and marking production as started "
        "(button_start)"
    )
    domain = "manufacturing"
    required_model = "mrp.production"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "production_id": {
                "type": "integer",
                "description": "ID of the mrp.production to start",
            },
        },
        "required": ["production_id"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        production_id = arguments["production_id"]

        # Reserve components
        await rpc_client.execute_kw(
            "mrp.production",
            "action_assign",
            [[production_id]],
        )
        # Start production
        result = await rpc_client.execute_kw(
            "mrp.production",
            "button_start",
            [[production_id]],
        )
        return {
            "production_id": production_id,
            "started": True,
            "result": result,
        }


class CompleteProduction(BaseTool):
    name = "manufacturing_complete_production"
    description = (
        "Complete a manufacturing order via button_mark_done to "
        "produce finished goods and consume components"
    )
    domain = "manufacturing"
    required_model = "mrp.production"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "production_id": {
                "type": "integer",
                "description": "ID of the mrp.production to mark as done",
            },
        },
        "required": ["production_id"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        production_id = arguments["production_id"]
        result = await rpc_client.execute_kw(
            "mrp.production",
            "button_mark_done",
            [[production_id]],
        )
        return {
            "production_id": production_id,
            "completed": True,
            "result": result,
        }


class PlanSchedule(BaseTool):
    name = "manufacturing_plan_schedule"
    description = (
        "Search and read planned manufacturing orders to view production schedule"
    )
    domain = "manufacturing"
    required_model = "mrp.production"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": (
                    "Filter by state: draft, confirmed, progress, "
                    "to_close, done, cancel"
                ),
            },
            "date_start_from": {
                "type": "string",
                "description": "Filter orders starting from this date (YYYY-MM-DD)",
            },
            "date_start_to": {
                "type": "string",
                "description": "Filter orders starting up to this date (YYYY-MM-DD)",
            },
            "domain": {
                "type": "array",
                "description": "Additional Odoo domain filters",
                "default": [],
            },
            "limit": {"type": "integer", "default": 80},
        },
        "required": [],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain: list = arguments.get("domain", [])
        if arguments.get("state"):
            domain.append(["state", "=", arguments["state"]])
        if arguments.get("date_start_from"):
            domain.append(["date_start", ">=", arguments["date_start_from"]])
        if arguments.get("date_start_to"):
            domain.append(["date_start", "<=", arguments["date_start_to"]])
        records = await rpc_client.search_read(
            "mrp.production",
            domain,
            fields=[
                "name",
                "product_id",
                "product_qty",
                "qty_produced",
                "state",
                "date_start",
                "date_finished",
                "bom_id",
                "origin",
            ],
            limit=arguments.get("limit", 80),
        )
        return {"records": records, "count": len(records)}


class QualityCheck(BaseTool):
    name = "manufacturing_quality_check"
    description = (
        "Record a quality check result (pass/fail) for a manufacturing quality point"
    )
    domain = "manufacturing"
    required_model = "quality.check"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "check_id": {
                "type": "integer",
                "description": "ID of the quality.check record",
            },
            "quality_state": {
                "type": "string",
                "description": "Result: pass or fail",
                "enum": ["pass", "fail"],
            },
            "note": {
                "type": "string",
                "description": "Optional notes about the check",
            },
        },
        "required": ["check_id", "quality_state"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        check_id = arguments["check_id"]
        quality_state = arguments["quality_state"]

        vals: dict[str, Any] = {"quality_state": quality_state}
        if arguments.get("note"):
            vals["note"] = arguments["note"]

        await rpc_client.write("quality.check", [check_id], vals)

        # Trigger the appropriate action based on pass/fail
        if quality_state == "pass":
            result = await rpc_client.execute_kw(
                "quality.check",
                "do_pass",
                [[check_id]],
            )
        else:
            result = await rpc_client.execute_kw(
                "quality.check",
                "do_fail",
                [[check_id]],
            )

        return {
            "check_id": check_id,
            "quality_state": quality_state,
            "recorded": True,
            "result": result,
        }


class SearchManufacturingOrders(BaseTool):
    name = "manufacturing_search_orders"
    description = "Search and read manufacturing orders with flexible filters"
    domain = "manufacturing"
    required_model = "mrp.production"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": "Odoo domain filter",
                "default": [],
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fields to return",
                "default": [],
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
            "order": {"type": "string", "default": ""},
        },
        "required": [],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain = arguments.get("domain", [])
        fields = arguments.get("fields", [])
        if not fields:
            fields = [
                "name",
                "product_id",
                "product_qty",
                "qty_produced",
                "state",
                "date_start",
                "date_finished",
                "bom_id",
                "origin",
                "priority",
            ]
        records = await rpc_client.search_read(
            "mrp.production",
            domain,
            fields=fields,
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
            order=arguments.get("order", ""),
        )
        return {"records": records, "count": len(records)}


class GetCapacity(BaseTool):
    name = "manufacturing_get_capacity"
    description = "Get work center capacity, efficiency, and current load information"
    domain = "manufacturing"
    required_model = "mrp.workcenter"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "workcenter_id": {
                "type": "integer",
                "description": "Specific work center ID to inspect (optional)",
            },
            "domain": {
                "type": "array",
                "description": "Additional Odoo domain filters",
                "default": [],
            },
            "limit": {"type": "integer", "default": 80},
        },
        "required": [],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain: list = arguments.get("domain", [])
        if arguments.get("workcenter_id"):
            domain.append(["id", "=", arguments["workcenter_id"]])
        records = await rpc_client.search_read(
            "mrp.workcenter",
            domain,
            fields=[
                "name",
                "code",
                "active",
                "capacity",
                "time_efficiency",
                "oee_target",
                "working_state",
                "blocked_time",
                "productive_time",
                "workcenter_load",
            ],
            limit=arguments.get("limit", 80),
        )
        return {"records": records, "count": len(records)}


ALL_MANUFACTURING_TOOLS = [
    CreateBOM(),
    CreateProduction(),
    StartProduction(),
    CompleteProduction(),
    PlanSchedule(),
    QualityCheck(),
    SearchManufacturingOrders(),
    GetCapacity(),
]
