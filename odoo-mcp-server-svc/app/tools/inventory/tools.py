"""Inventory & Purchase domain tools — 11 tools for warehouse operations."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CheckAvailability(BaseTool):
    name = "inventory_check_availability"
    description = (
        "Check stock availability for a picking (delivery order, "
        "receipt, or internal transfer)"
    )
    domain = "inventory"
    required_model = "stock.picking"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "picking_id": {
                "type": "integer",
                "description": "ID of the stock.picking to check",
            },
        },
        "required": ["picking_id"],
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
        picking_id = arguments["picking_id"]
        # Read the picking with its move lines
        records = await rpc_client.search_read(
            "stock.picking",
            [["id", "=", picking_id]],
            fields=[
                "name",
                "state",
                "scheduled_date",
                "picking_type_id",
                "move_ids",
            ],
        )
        if not records:
            return {"error": f"Picking {picking_id} not found"}
        picking = records[0]
        # Read move lines for availability detail
        move_ids = picking.get("move_ids", [])
        moves = []
        if move_ids:
            moves = await rpc_client.search_read(
                "stock.move",
                [["id", "in", move_ids]],
                fields=[
                    "product_id",
                    "product_uom_qty",
                    "quantity",
                    "state",
                ],
            )
        return {
            "picking_id": picking_id,
            "name": picking.get("name"),
            "state": picking.get("state"),
            "moves": moves,
        }


class CreateTransfer(BaseTool):
    name = "inventory_create_transfer"
    description = (
        "Create an internal, outgoing, or incoming stock transfer (stock.picking)"
    )
    domain = "inventory"
    required_model = "stock.picking"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "picking_type_id": {
                "type": "integer",
                "description": (
                    "ID of the picking type (e.g. internal, incoming, outgoing)"
                ),
            },
            "location_id": {
                "type": "integer",
                "description": "Source stock.location ID",
            },
            "location_dest_id": {
                "type": "integer",
                "description": "Destination stock.location ID",
            },
            "partner_id": {
                "type": "integer",
                "description": "Optional partner ID",
            },
            "scheduled_date": {
                "type": "string",
                "description": "Scheduled date (YYYY-MM-DD HH:MM:SS)",
            },
            "move_lines": {
                "type": "array",
                "description": "List of move lines to create",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "product_uom_qty": {"type": "number"},
                        "name": {
                            "type": "string",
                            "description": "Move description",
                        },
                        "location_id": {"type": "integer"},
                        "location_dest_id": {"type": "integer"},
                    },
                    "required": ["product_id", "product_uom_qty"],
                },
            },
        },
        "required": [
            "picking_type_id",
            "location_id",
            "location_dest_id",
            "move_lines",
        ],
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
            "picking_type_id": arguments["picking_type_id"],
            "location_id": arguments["location_id"],
            "location_dest_id": arguments["location_dest_id"],
        }
        if arguments.get("partner_id"):
            vals["partner_id"] = arguments["partner_id"]
        if arguments.get("scheduled_date"):
            vals["scheduled_date"] = arguments["scheduled_date"]

        # Build one2many command tuples for move_ids
        move_cmds = []
        for line in arguments["move_lines"]:
            move_vals: dict[str, Any] = {
                "product_id": line["product_id"],
                "product_uom_qty": line["product_uom_qty"],
                "name": line.get("name", "Transfer"),
                "location_id": line.get("location_id", arguments["location_id"]),
                "location_dest_id": line.get(
                    "location_dest_id", arguments["location_dest_id"]
                ),
            }
            move_cmds.append([0, 0, move_vals])
        vals["move_ids"] = move_cmds

        picking_id = await rpc_client.create("stock.picking", vals)
        return {"picking_id": picking_id, "success": True}


class ValidateTransfer(BaseTool):
    name = "inventory_validate_transfer"
    description = "Validate (confirm) a stock picking via button_validate"
    domain = "inventory"
    required_model = "stock.picking"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "picking_id": {
                "type": "integer",
                "description": "ID of the stock.picking to validate",
            },
        },
        "required": ["picking_id"],
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
        picking_id = arguments["picking_id"]
        result = await rpc_client.execute_kw(
            "stock.picking",
            "button_validate",
            [[picking_id]],
        )
        return {
            "picking_id": picking_id,
            "validated": True,
            "result": result,
        }


class CreateAdjustment(BaseTool):
    name = "inventory_create_adjustment"
    description = (
        "Create an inventory adjustment by updating stock.quant quantities directly"
    )
    domain = "inventory"
    required_model = "stock.quant"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Product to adjust",
            },
            "location_id": {
                "type": "integer",
                "description": "Stock location for the adjustment",
            },
            "inventory_quantity": {
                "type": "number",
                "description": "New counted quantity",
            },
        },
        "required": ["product_id", "location_id", "inventory_quantity"],
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
        product_id = arguments["product_id"]
        location_id = arguments["location_id"]
        inventory_quantity = arguments["inventory_quantity"]

        # Find existing quant or let Odoo create one
        quants = await rpc_client.search_read(
            "stock.quant",
            [
                ["product_id", "=", product_id],
                ["location_id", "=", location_id],
            ],
            fields=["id", "quantity", "inventory_quantity"],
            limit=1,
        )
        if quants:
            quant_id = quants[0]["id"]
            await rpc_client.write(
                "stock.quant",
                [quant_id],
                {"inventory_quantity": inventory_quantity},
            )
            # Apply the adjustment
            await rpc_client.execute_kw(
                "stock.quant",
                "action_apply_inventory",
                [[quant_id]],
            )
            return {
                "quant_id": quant_id,
                "product_id": product_id,
                "new_quantity": inventory_quantity,
                "applied": True,
            }
        else:
            # Create quant via the inventory adjustment wizard approach
            quant_id = await rpc_client.create(
                "stock.quant",
                {
                    "product_id": product_id,
                    "location_id": location_id,
                    "inventory_quantity": inventory_quantity,
                },
            )
            await rpc_client.execute_kw(
                "stock.quant",
                "action_apply_inventory",
                [[quant_id]],
            )
            return {
                "quant_id": quant_id,
                "product_id": product_id,
                "new_quantity": inventory_quantity,
                "applied": True,
            }


class GetValuation(BaseTool):
    name = "inventory_get_valuation"
    description = (
        "Retrieve stock valuation layers for products to see "
        "inventory value and cost"
    )
    domain = "inventory"
    required_model = "stock.valuation.layer"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Filter by product ID (optional)",
            },
            "domain": {
                "type": "array",
                "description": "Additional Odoo domain filters",
                "default": [],
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
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
        if arguments.get("product_id"):
            domain.append(["product_id", "=", arguments["product_id"]])
        records = await rpc_client.search_read(
            "stock.valuation.layer",
            domain,
            fields=[
                "product_id",
                "quantity",
                "unit_cost",
                "value",
                "remaining_qty",
                "remaining_value",
                "create_date",
            ],
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
        )
        return {"records": records, "count": len(records)}


class ManageLocations(BaseTool):
    name = "inventory_manage_locations"
    description = "Search and read stock locations (warehouses, bins, virtual)"
    domain = "inventory"
    required_model = "stock.location"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": "Odoo domain filter for locations",
                "default": [],
            },
            "usage": {
                "type": "string",
                "description": (
                    "Filter by usage type: internal, supplier, "
                    "customer, transit, view, production"
                ),
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
        if arguments.get("usage"):
            domain.append(["usage", "=", arguments["usage"]])
        records = await rpc_client.search_read(
            "stock.location",
            domain,
            fields=[
                "name",
                "complete_name",
                "usage",
                "location_id",
                "warehouse_id",
                "active",
            ],
            limit=arguments.get("limit", 80),
        )
        return {"records": records, "count": len(records)}


class ForecastReport(BaseTool):
    name = "inventory_forecast_report"
    description = (
        "Get stock forecast data from stock.quant showing current "
        "on-hand and reserved quantities"
    )
    domain = "inventory"
    required_model = "stock.quant"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "Filter by product ID (optional)",
            },
            "location_id": {
                "type": "integer",
                "description": "Filter by location ID (optional)",
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
        if arguments.get("product_id"):
            domain.append(["product_id", "=", arguments["product_id"]])
        if arguments.get("location_id"):
            domain.append(["location_id", "=", arguments["location_id"]])
        records = await rpc_client.search_read(
            "stock.quant",
            domain,
            fields=[
                "product_id",
                "location_id",
                "quantity",
                "reserved_quantity",
                "available_quantity",
            ],
            limit=arguments.get("limit", 80),
        )
        return {"records": records, "count": len(records)}


class CreateRFQ(BaseTool):
    name = "inventory_create_rfq"
    description = (
        "Create a purchase order (Request for Quotation) for "
        "procuring products from a supplier"
    )
    domain = "inventory"
    required_model = "purchase.order"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "partner_id": {
                "type": "integer",
                "description": "Supplier (res.partner) ID",
            },
            "order_lines": {
                "type": "array",
                "description": "List of purchase order lines",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "product_qty": {"type": "number"},
                        "price_unit": {"type": "number"},
                        "name": {
                            "type": "string",
                            "description": "Line description",
                        },
                    },
                    "required": ["product_id", "product_qty"],
                },
            },
            "date_planned": {
                "type": "string",
                "description": "Planned receipt date (YYYY-MM-DD HH:MM:SS)",
            },
            "currency_id": {
                "type": "integer",
                "description": "Currency ID (optional)",
            },
        },
        "required": ["partner_id", "order_lines"],
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
            "partner_id": arguments["partner_id"],
        }
        if arguments.get("date_planned"):
            vals["date_planned"] = arguments["date_planned"]
        if arguments.get("currency_id"):
            vals["currency_id"] = arguments["currency_id"]

        # Build one2many command tuples for order_line
        line_cmds = []
        for line in arguments["order_lines"]:
            line_vals: dict[str, Any] = {
                "product_id": line["product_id"],
                "product_qty": line["product_qty"],
            }
            if line.get("price_unit") is not None:
                line_vals["price_unit"] = line["price_unit"]
            if line.get("name"):
                line_vals["name"] = line["name"]
            line_cmds.append([0, 0, line_vals])
        vals["order_line"] = line_cmds

        order_id = await rpc_client.create("purchase.order", vals)
        return {"order_id": order_id, "success": True}


class ConfirmPurchaseOrder(BaseTool):
    name = "inventory_confirm_purchase_order"
    description = "Confirm a purchase order (RFQ to PO) via button_confirm"
    domain = "inventory"
    required_model = "purchase.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "ID of the purchase.order to confirm",
            },
        },
        "required": ["order_id"],
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
        order_id = arguments["order_id"]
        result = await rpc_client.execute_kw(
            "purchase.order",
            "button_confirm",
            [[order_id]],
        )
        return {
            "order_id": order_id,
            "confirmed": True,
            "result": result,
        }


class ReceiveProducts(BaseTool):
    name = "inventory_receive_products"
    description = (
        "Receive incoming products on a picking by setting received "
        "quantities and validating"
    )
    domain = "inventory"
    required_model = "stock.picking"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "picking_id": {
                "type": "integer",
                "description": "ID of the incoming stock.picking",
            },
            "move_quantities": {
                "type": "array",
                "description": "List of move IDs with quantities to receive",
                "items": {
                    "type": "object",
                    "properties": {
                        "move_id": {"type": "integer"},
                        "quantity": {"type": "number"},
                    },
                    "required": ["move_id", "quantity"],
                },
            },
        },
        "required": ["picking_id"],
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
        picking_id = arguments["picking_id"]

        # Update quantities on individual moves if provided
        move_quantities = arguments.get("move_quantities", [])
        for mq in move_quantities:
            await rpc_client.write(
                "stock.move",
                [mq["move_id"]],
                {"quantity": mq["quantity"]},
            )

        # Validate the picking to complete receipt
        result = await rpc_client.execute_kw(
            "stock.picking",
            "button_validate",
            [[picking_id]],
        )
        return {
            "picking_id": picking_id,
            "received": True,
            "result": result,
        }


class CreatePurchaseBill(BaseTool):
    name = "inventory_create_purchase_bill"
    description = (
        "Create a vendor bill from a confirmed purchase order via "
        "action_create_invoice"
    )
    domain = "inventory"
    required_model = "purchase.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "ID of the purchase.order to bill",
            },
        },
        "required": ["order_id"],
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
        order_id = arguments["order_id"]
        result = await rpc_client.execute_kw(
            "purchase.order",
            "action_create_invoice",
            [[order_id]],
        )
        return {
            "order_id": order_id,
            "bill_created": True,
            "result": result,
        }


ALL_INVENTORY_TOOLS = [
    CheckAvailability(),
    CreateTransfer(),
    ValidateTransfer(),
    CreateAdjustment(),
    GetValuation(),
    ManageLocations(),
    ForecastReport(),
    CreateRFQ(),
    ConfirmPurchaseOrder(),
    ReceiveProducts(),
    CreatePurchaseBill(),
]
