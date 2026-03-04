"""MCP Prompts — 8 Odoo workflow prompts for guided AI interactions."""

import logging
from typing import Optional

from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
)

logger = logging.getLogger(__name__)


WORKFLOW_PROMPTS: dict[str, dict] = {
    "order_to_cash": {
        "name": "order_to_cash",
        "description": "Guide through the Order-to-Cash cycle: quotation → order → delivery → invoice → payment",
        "arguments": [
            {
                "name": "customer_name",
                "description": "Customer or partner name",
                "required": True,
            },
            {
                "name": "product_name",
                "description": "Product to sell",
                "required": False,
            },
        ],
        "template": (
            "Walk me through the complete Order-to-Cash workflow in Odoo for "
            "customer '{customer_name}'.\n\n"
            "Steps:\n"
            "1. Create or find the customer (res.partner)\n"
            "2. Create a quotation (sale.order)\n"
            "3. Add order lines with products{product_clause}\n"
            "4. Confirm the quotation → sales order\n"
            "5. Process the delivery (stock.picking)\n"
            "6. Create and post the invoice (account.move)\n"
            "7. Register the payment\n\n"
            "Use the appropriate Odoo MCP tools at each step. "
            "Show me the data created at each stage."
        ),
    },
    "procure_to_pay": {
        "name": "procure_to_pay",
        "description": "Guide through Procure-to-Pay: purchase request → RFQ → PO → receipt → bill → payment",
        "arguments": [
            {
                "name": "vendor_name",
                "description": "Vendor or supplier name",
                "required": True,
            },
            {
                "name": "product_name",
                "description": "Product to purchase",
                "required": False,
            },
        ],
        "template": (
            "Walk me through the Procure-to-Pay workflow in Odoo for "
            "vendor '{vendor_name}'.\n\n"
            "Steps:\n"
            "1. Find or create the vendor (res.partner)\n"
            "2. Create a Request for Quotation (purchase.order)\n"
            "3. Add order lines{product_clause}\n"
            "4. Confirm the purchase order\n"
            "5. Receive the products (stock.picking)\n"
            "6. Create and validate the vendor bill\n"
            "7. Register payment to the vendor\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
    "month_end_close": {
        "name": "month_end_close",
        "description": "Guide through month-end accounting close procedures",
        "arguments": [
            {
                "name": "period",
                "description": "Accounting period (e.g., '2024-01')",
                "required": True,
            },
        ],
        "template": (
            "Guide me through the month-end close process in Odoo "
            "for period '{period}'.\n\n"
            "Steps:\n"
            "1. Review and post all draft journal entries\n"
            "2. Reconcile bank statements\n"
            "3. Review accounts receivable aging\n"
            "4. Review accounts payable aging\n"
            "5. Post depreciation entries\n"
            "6. Review and adjust accruals\n"
            "7. Run trial balance report\n"
            "8. Generate P&L and Balance Sheet\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
    "new_employee_onboard": {
        "name": "new_employee_onboard",
        "description": "Guide through new employee onboarding in HR",
        "arguments": [
            {
                "name": "employee_name",
                "description": "New employee's full name",
                "required": True,
            },
            {
                "name": "department",
                "description": "Department name",
                "required": False,
            },
        ],
        "template": (
            "Guide me through onboarding new employee '{employee_name}' "
            "in Odoo{dept_clause}.\n\n"
            "Steps:\n"
            "1. Create employee record (hr.employee)\n"
            "2. Set up department and job position\n"
            "3. Configure leave allocations\n"
            "4. Set up attendance tracking\n"
            "5. Create user account if needed\n"
            "6. Assign to projects/teams\n"
            "7. Set up payroll (if applicable)\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
    "inventory_cycle_count": {
        "name": "inventory_cycle_count",
        "description": "Guide through inventory cycle count and adjustment",
        "arguments": [
            {
                "name": "location",
                "description": "Warehouse location name",
                "required": True,
            },
        ],
        "template": (
            "Guide me through an inventory cycle count in Odoo "
            "for location '{location}'.\n\n"
            "Steps:\n"
            "1. Review current stock levels (stock.quant)\n"
            "2. Generate count sheet for the location\n"
            "3. Compare physical count vs system count\n"
            "4. Create inventory adjustments for discrepancies\n"
            "5. Validate adjustments\n"
            "6. Review valuation impact\n"
            "7. Generate variance report\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
    "customer_complaint": {
        "name": "customer_complaint",
        "description": "Handle a customer complaint end-to-end",
        "arguments": [
            {
                "name": "customer_name",
                "description": "Customer name",
                "required": True,
            },
            {
                "name": "issue",
                "description": "Brief description of the complaint",
                "required": True,
            },
        ],
        "template": (
            "Help me handle a customer complaint in Odoo.\n"
            "Customer: {customer_name}\n"
            "Issue: {issue}\n\n"
            "Steps:\n"
            "1. Look up the customer and recent orders\n"
            "2. Create a helpdesk ticket or CRM activity\n"
            "3. Check related deliveries and invoices\n"
            "4. Process return/refund if needed\n"
            "5. Create credit note if applicable\n"
            "6. Log resolution and follow-up\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
    "production_run": {
        "name": "production_run",
        "description": "Plan and execute a manufacturing production run",
        "arguments": [
            {
                "name": "product_name",
                "description": "Product to manufacture",
                "required": True,
            },
            {
                "name": "quantity",
                "description": "Quantity to produce",
                "required": True,
            },
        ],
        "template": (
            "Guide me through a production run in Odoo.\n"
            "Product: {product_name}\n"
            "Quantity: {quantity}\n\n"
            "Steps:\n"
            "1. Check the Bill of Materials (mrp.bom)\n"
            "2. Verify component availability\n"
            "3. Create manufacturing order (mrp.production)\n"
            "4. Reserve components\n"
            "5. Start production\n"
            "6. Record work order progress\n"
            "7. Quality checks\n"
            "8. Mark production as done\n"
            "9. Update finished goods inventory\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
    "tenant_setup_wizard": {
        "name": "tenant_setup_wizard",
        "description": "Set up a new tenant with Odoo database and configuration",
        "arguments": [
            {
                "name": "company_name",
                "description": "New tenant company name",
                "required": True,
            },
            {
                "name": "modules",
                "description": "Comma-separated list of modules to install",
                "required": False,
            },
        ],
        "template": (
            "Set up a new Odoo tenant for company '{company_name}'.\n\n"
            "Steps:\n"
            "1. Create/provision the Odoo database\n"
            "2. Configure company details\n"
            "3. Install required modules{modules_clause}\n"
            "4. Set up chart of accounts\n"
            "5. Configure warehouses and locations\n"
            "6. Create admin user\n"
            "7. Set up RBAC roles\n"
            "8. Configure email and notifications\n"
            "9. Run initial data import if needed\n\n"
            "Use the appropriate Odoo MCP tools at each step."
        ),
    },
}


class PromptRegistry:
    """Registry for MCP workflow prompts."""

    def list_prompts(self) -> list[Prompt]:
        """Return all registered prompts."""
        prompts = []
        for key, data in WORKFLOW_PROMPTS.items():
            args = [
                PromptArgument(
                    name=a["name"],
                    description=a.get("description", ""),
                    required=a.get("required", False),
                )
                for a in data.get("arguments", [])
            ]
            prompts.append(
                Prompt(
                    name=data["name"],
                    description=data["description"],
                    arguments=args,
                )
            )
        return prompts

    async def get_prompt(
        self, name: str, arguments: Optional[dict[str, str]] = None
    ) -> GetPromptResult:
        """Get a specific prompt with arguments filled in."""
        data = WORKFLOW_PROMPTS.get(name)
        if data is None:
            return GetPromptResult(
                description=f"Unknown prompt: {name}",
                messages=[],
            )

        arguments = arguments or {}
        template = data["template"]

        # Fill in optional clauses
        product_name = arguments.get("product_name", "")
        product_clause = f" (specifically '{product_name}')" if product_name else ""
        dept = arguments.get("department", "")
        dept_clause = f" in the {dept} department" if dept else ""
        modules = arguments.get("modules", "")
        modules_clause = f": {modules}" if modules else ""

        # Standard substitutions
        text = template.format(
            customer_name=arguments.get("customer_name", "the customer"),
            vendor_name=arguments.get("vendor_name", "the vendor"),
            period=arguments.get("period", "current period"),
            employee_name=arguments.get("employee_name", "the employee"),
            location=arguments.get("location", "main warehouse"),
            issue=arguments.get("issue", "unspecified issue"),
            product_name=arguments.get("product_name", "the product"),
            quantity=arguments.get("quantity", "TBD"),
            company_name=arguments.get("company_name", "New Company"),
            product_clause=product_clause,
            dept_clause=dept_clause,
            modules_clause=modules_clause,
        )

        return GetPromptResult(
            description=data["description"],
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=text),
                )
            ],
        )
