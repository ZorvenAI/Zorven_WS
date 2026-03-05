"""Website domain tools — pages, e-commerce products, and orders."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreatePage(BaseTool):
    """Create a new website page with HTML content."""

    name = "website_create_page"
    description = (
        "Create a website page with a URL, optional HTML content, and publish state"
    )
    domain = "website"
    required_model = "website.page"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Page title / menu label",
            },
            "url": {
                "type": "string",
                "description": "Page URL path, e.g. /about-us",
            },
            "website_published": {
                "type": "boolean",
                "description": "Whether the page is published immediately",
                "default": False,
            },
            "arch_db": {
                "type": "string",
                "description": (
                    "HTML content of the page wrapped in Odoo QWeb template tags"
                ),
                "default": "",
            },
        },
        "required": ["name", "url"],
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

        values: dict[str, Any] = {
            "name": arguments["name"],
            "url": arguments["url"],
            "website_published": arguments.get("website_published", False),
        }
        if arguments.get("arch_db"):
            values["arch_db"] = arguments["arch_db"]

        page_id = await rpc_client.create("website.page", values)
        return {"id": page_id, "model": "website.page"}


class ListProducts(BaseTool):
    """List published e-commerce products."""

    name = "website_list_products"
    description = (
        "Search and read published website products with name, price, and image"
    )
    domain = "website"
    required_model = "product.template"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of products to return",
                "default": 80,
            },
            "offset": {
                "type": "integer",
                "description": "Number of records to skip",
                "default": 0,
            },
            "extra_domain": {
                "type": "array",
                "description": (
                    "Additional domain filters to apply on top of "
                    "website_published=True"
                ),
                "default": [],
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
            return {"error": "No RPC client available", "records": []}

        domain: list[Any] = [("website_published", "=", True)]
        extra = arguments.get("extra_domain", [])
        if extra:
            domain = domain + extra

        records = await rpc_client.search_read(
            "product.template",
            domain,
            fields=["name", "list_price", "image_1920", "website_url"],
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
        )
        return {
            "model": "product.template",
            "records": records,
            "count": len(records),
        }


class ProcessEcommerceOrder(BaseTool):
    """Search website sale orders for a given website."""

    name = "website_process_ecommerce_order"
    description = (
        "Search and read e-commerce sale orders, optionally filtered "
        "by website ID, state, or date range"
    )
    domain = "website"
    required_model = "sale.order"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "website_id": {
                "type": "integer",
                "description": "Filter orders by website ID",
            },
            "state": {
                "type": "string",
                "description": ("Order state filter: draft, sent, sale, done, cancel"),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of orders to return",
                "default": 80,
            },
            "offset": {
                "type": "integer",
                "description": "Number of records to skip",
                "default": 0,
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
            return {"error": "No RPC client available", "records": []}

        domain: list[Any] = []
        if arguments.get("website_id"):
            domain.append(("website_id", "=", arguments["website_id"]))
        if arguments.get("state"):
            domain.append(("state", "=", arguments["state"]))

        records = await rpc_client.search_read(
            "sale.order",
            domain,
            fields=[
                "name",
                "partner_id",
                "website_id",
                "state",
                "amount_total",
                "date_order",
                "order_line",
            ],
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
        )
        return {
            "model": "sale.order",
            "records": records,
            "count": len(records),
        }


# Convenience: all website tools for registration
ALL_WEBSITE_TOOLS = [
    CreatePage(),
    ListProducts(),
    ProcessEcommerceOrder(),
]
