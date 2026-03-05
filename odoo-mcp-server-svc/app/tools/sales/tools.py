"""Sales domain tools — 10 tools for managing quotations and sale orders."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateQuotation(BaseTool):
    name = "sales_create_quotation"
    description = "Create a new sales quotation (draft sale order) for a customer."
    domain = "sales"
    required_model = "sale.order"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "partner_id": {
                "type": "integer",
                "description": "Customer (res.partner) ID",
            },
            "date_order": {
                "type": "string",
                "description": "Order date in YYYY-MM-DD format",
            },
            "validity_date": {
                "type": "string",
                "description": "Quotation expiry date in YYYY-MM-DD format",
            },
            "pricelist_id": {
                "type": "integer",
                "description": "Pricelist ID to apply",
            },
            "payment_term_id": {
                "type": "integer",
                "description": "Payment terms ID",
            },
            "note": {
                "type": "string",
                "description": "Internal note on the quotation",
            },
            "user_id": {
                "type": "integer",
                "description": "Salesperson (res.users) ID",
            },
            "team_id": {
                "type": "integer",
                "description": "Sales team ID",
            },
        },
        "required": ["partner_id"],
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
        values = {
            k: v for k, v in arguments.items() if k != "_rbac_domain" and v is not None
        }
        order_id = await rpc_client.create("sale.order", values)
        return {"id": order_id, "partner_id": arguments["partner_id"]}


class AddOrderLine(BaseTool):
    name = "sales_add_order_line"
    description = "Add a product line to an existing sale order / quotation."
    domain = "sales"
    required_model = "sale.order"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order ID to add the line to",
            },
            "product_id": {
                "type": "integer",
                "description": "Product (product.product) ID",
            },
            "product_uom_qty": {
                "type": "number",
                "description": "Quantity",
                "default": 1,
            },
            "price_unit": {
                "type": "number",
                "description": "Unit price (overrides pricelist if set)",
            },
            "discount": {
                "type": "number",
                "description": "Discount percentage (0-100)",
                "default": 0,
            },
            "name": {
                "type": "string",
                "description": "Line description (auto-filled from product if omitted)",
            },
        },
        "required": ["order_id", "product_id"],
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
        values = {
            "order_id": arguments["order_id"],
            "product_id": arguments["product_id"],
            "product_uom_qty": arguments.get("product_uom_qty", 1),
        }
        if "price_unit" in arguments:
            values["price_unit"] = arguments["price_unit"]
        if "discount" in arguments:
            values["discount"] = arguments["discount"]
        if "name" in arguments:
            values["name"] = arguments["name"]
        line_id = await rpc_client.create("sale.order.line", values)
        return {
            "line_id": line_id,
            "order_id": arguments["order_id"],
            "product_id": arguments["product_id"],
        }


class ConfirmOrder(BaseTool):
    name = "sales_confirm_order"
    description = "Confirm a quotation, converting it into a confirmed sale order."
    domain = "sales"
    required_model = "sale.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order ID to confirm",
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
            "sale.order",
            "action_confirm",
            [[order_id]],
        )
        return {"id": order_id, "status": "confirmed", "result": result}


class CancelOrder(BaseTool):
    name = "sales_cancel_order"
    description = "Cancel a sale order."
    domain = "sales"
    required_model = "sale.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order ID to cancel",
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
            "sale.order",
            "action_cancel",
            [[order_id]],
        )
        return {"id": order_id, "status": "cancelled", "result": result}


class CreateInvoice(BaseTool):
    name = "sales_create_invoice"
    description = (
        "Create an invoice from a confirmed sale order. "
        "The order must be in 'sale' or 'done' state."
    )
    domain = "sales"
    required_model = "sale.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order ID to invoice",
            },
            "advance_payment_method": {
                "type": "string",
                "enum": ["delivered", "percentage", "fixed"],
                "description": "Invoicing method",
                "default": "delivered",
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
            "sale.order",
            "_create_invoices",
            [[order_id]],
        )
        return {"order_id": order_id, "invoice_ids": result}


class ApplyDiscount(BaseTool):
    name = "sales_apply_discount"
    description = (
        "Apply a discount percentage to one or more order lines " "on a sale order."
    )
    domain = "sales"
    required_model = "sale.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "line_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Sale order line IDs to apply discount to",
            },
            "discount": {
                "type": "number",
                "description": "Discount percentage (0-100)",
            },
        },
        "required": ["line_ids", "discount"],
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
        line_ids = arguments["line_ids"]
        discount = arguments["discount"]
        success = await rpc_client.write(
            "sale.order.line",
            line_ids,
            {"discount": discount},
        )
        return {
            "line_ids": line_ids,
            "discount": discount,
            "success": success,
        }


class SearchOrders(BaseTool):
    name = "sales_search_orders"
    description = (
        "Search sale orders with domain filters. Returns orders with "
        "partner, state, and amount info."
    )
    domain = "sales"
    required_model = "sale.order"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": ("Odoo domain filter, " "e.g. [['state','=','sale']]"),
                "default": [],
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "default": [
                    "name",
                    "partner_id",
                    "state",
                    "date_order",
                    "amount_total",
                    "user_id",
                    "invoice_status",
                ],
                "description": "Fields to return",
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
            "order": {
                "type": "string",
                "default": "date_order desc",
            },
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
            return {"error": "No RPC client available", "orders": []}
        domain = arguments.get("domain", [])
        rbac_domain = arguments.pop("_rbac_domain", [])
        if rbac_domain:
            domain = domain + rbac_domain
        orders = await rpc_client.search_read(
            "sale.order",
            domain,
            fields=arguments.get(
                "fields",
                [
                    "name",
                    "partner_id",
                    "state",
                    "date_order",
                    "amount_total",
                    "user_id",
                    "invoice_status",
                ],
            ),
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
            order=arguments.get("order", "date_order desc"),
        )
        return {"orders": orders, "count": len(orders)}


class GetOrderDetails(BaseTool):
    name = "sales_get_order_details"
    description = (
        "Get full details of a sale order including all order lines "
        "with product, quantity, and pricing."
    )
    domain = "sales"
    required_model = "sale.order"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order ID",
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
        # Read the order header
        orders = await rpc_client.execute_kw(
            "sale.order",
            "read",
            [[order_id]],
            {
                "fields": [
                    "name",
                    "partner_id",
                    "state",
                    "date_order",
                    "amount_untaxed",
                    "amount_tax",
                    "amount_total",
                    "user_id",
                    "pricelist_id",
                    "payment_term_id",
                    "note",
                    "order_line",
                ],
            },
        )
        if not orders:
            return {"error": f"Sale order {order_id} not found"}
        order = orders[0]
        # Read order lines
        line_ids = order.get("order_line", [])
        lines = []
        if line_ids:
            lines = await rpc_client.search_read(
                "sale.order.line",
                [["id", "in", line_ids]],
                fields=[
                    "product_id",
                    "name",
                    "product_uom_qty",
                    "price_unit",
                    "discount",
                    "price_subtotal",
                    "price_total",
                ],
            )
        order["lines"] = lines
        return {"order": order}


class UpdatePricelist(BaseTool):
    name = "sales_update_pricelist"
    description = (
        "Change the pricelist on a sale order. Odoo will recompute "
        "line prices based on the new pricelist."
    )
    domain = "sales"
    required_model = "sale.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order ID",
            },
            "pricelist_id": {
                "type": "integer",
                "description": "New pricelist (product.pricelist) ID",
            },
        },
        "required": ["order_id", "pricelist_id"],
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
        pricelist_id = arguments["pricelist_id"]
        success = await rpc_client.write(
            "sale.order",
            [order_id],
            {"pricelist_id": pricelist_id},
        )
        return {
            "id": order_id,
            "pricelist_id": pricelist_id,
            "success": success,
        }


class SendQuotation(BaseTool):
    name = "sales_send_quotation"
    description = (
        "Mark a quotation as sent. This triggers the 'Quotation Sent' "
        "status in Odoo."
    )
    domain = "sales"
    required_model = "sale.order"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Sale order / quotation ID to mark as sent",
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
            "sale.order",
            "action_quotation_sent",
            [[order_id]],
        )
        return {"id": order_id, "status": "sent", "result": result}


ALL_SALES_TOOLS = [
    CreateQuotation(),
    AddOrderLine(),
    ConfirmOrder(),
    CancelOrder(),
    CreateInvoice(),
    ApplyDiscount(),
    SearchOrders(),
    GetOrderDetails(),
    UpdatePricelist(),
    SendQuotation(),
]
