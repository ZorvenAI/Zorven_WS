"""Accounting domain tools — 10 tools for invoices, payments, and reporting."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateInvoice(BaseTool):
    name = "accounting_create_invoice"
    description = "Create a customer invoice (account.move with type out_invoice)."
    domain = "accounting"
    required_model = "account.move"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "partner_id": {
                "type": "integer",
                "description": "Customer (res.partner) ID",
            },
            "invoice_date": {
                "type": "string",
                "description": "Invoice date in YYYY-MM-DD format",
            },
            "invoice_date_due": {
                "type": "string",
                "description": "Due date in YYYY-MM-DD format",
            },
            "journal_id": {
                "type": "integer",
                "description": "Accounting journal ID",
            },
            "currency_id": {
                "type": "integer",
                "description": "Currency ID (defaults to company currency)",
            },
            "invoice_line_ids": {
                "type": "array",
                "description": (
                    "Invoice lines as list of dicts with keys: "
                    "name, quantity, price_unit, account_id, "
                    "tax_ids (optional), product_id (optional)"
                ),
                "items": {"type": "object"},
            },
            "ref": {
                "type": "string",
                "description": "Payment reference / memo",
            },
            "narration": {
                "type": "string",
                "description": "Internal notes",
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
        values = {"move_type": "out_invoice"}
        for key in (
            "partner_id",
            "invoice_date",
            "invoice_date_due",
            "journal_id",
            "currency_id",
            "ref",
            "narration",
        ):
            if key in arguments:
                values[key] = arguments[key]
        # Convert line dicts to Odoo (0, 0, vals) command format
        if "invoice_line_ids" in arguments:
            values["invoice_line_ids"] = [
                (0, 0, line) for line in arguments["invoice_line_ids"]
            ]
        invoice_id = await rpc_client.create("account.move", values)
        return {
            "id": invoice_id,
            "move_type": "out_invoice",
            "partner_id": arguments["partner_id"],
        }


class CreateBill(BaseTool):
    name = "accounting_create_bill"
    description = "Create a vendor bill (account.move with type in_invoice)."
    domain = "accounting"
    required_model = "account.move"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "partner_id": {
                "type": "integer",
                "description": "Vendor (res.partner) ID",
            },
            "invoice_date": {
                "type": "string",
                "description": "Bill date in YYYY-MM-DD format",
            },
            "invoice_date_due": {
                "type": "string",
                "description": "Due date in YYYY-MM-DD format",
            },
            "journal_id": {
                "type": "integer",
                "description": "Accounting journal ID",
            },
            "ref": {
                "type": "string",
                "description": "Vendor reference",
            },
            "invoice_line_ids": {
                "type": "array",
                "description": (
                    "Bill lines as list of dicts with keys: "
                    "name, quantity, price_unit, account_id, "
                    "tax_ids (optional), product_id (optional)"
                ),
                "items": {"type": "object"},
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
        values = {"move_type": "in_invoice"}
        for key in (
            "partner_id",
            "invoice_date",
            "invoice_date_due",
            "journal_id",
            "ref",
        ):
            if key in arguments:
                values[key] = arguments[key]
        if "invoice_line_ids" in arguments:
            values["invoice_line_ids"] = [
                (0, 0, line) for line in arguments["invoice_line_ids"]
            ]
        bill_id = await rpc_client.create("account.move", values)
        return {
            "id": bill_id,
            "move_type": "in_invoice",
            "partner_id": arguments["partner_id"],
        }


class PostEntry(BaseTool):
    name = "accounting_post_entry"
    description = (
        "Post (validate) a draft journal entry, invoice, or bill. "
        "Changes state from draft to posted."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "move_id": {
                "type": "integer",
                "description": "Account move ID to post",
            },
        },
        "required": ["move_id"],
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
        move_id = arguments["move_id"]
        result = await rpc_client.execute_kw(
            "account.move",
            "action_post",
            [[move_id]],
        )
        return {"id": move_id, "status": "posted", "result": result}


class RegisterPayment(BaseTool):
    name = "accounting_register_payment"
    description = (
        "Register a payment against one or more invoices/bills "
        "using the payment register wizard."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "move_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Invoice/bill IDs to pay",
            },
            "journal_id": {
                "type": "integer",
                "description": "Payment journal ID (bank/cash)",
            },
            "amount": {
                "type": "number",
                "description": (
                    "Payment amount (defaults to invoice balance if omitted)"
                ),
            },
            "payment_date": {
                "type": "string",
                "description": "Payment date in YYYY-MM-DD format",
            },
            "payment_method_line_id": {
                "type": "integer",
                "description": "Payment method line ID",
            },
        },
        "required": ["move_ids", "journal_id"],
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
        move_ids = arguments["move_ids"]
        # Create the payment register wizard with the given context
        wizard_values = {"journal_id": arguments["journal_id"]}
        if "amount" in arguments:
            wizard_values["amount"] = arguments["amount"]
        if "payment_date" in arguments:
            wizard_values["payment_date"] = arguments["payment_date"]
        if "payment_method_line_id" in arguments:
            wizard_values["payment_method_line_id"] = arguments[
                "payment_method_line_id"
            ]
        wizard_id = await rpc_client.execute_kw(
            "account.payment.register",
            "create",
            [wizard_values],
            {"context": {"active_model": "account.move", "active_ids": move_ids}},
        )
        result = await rpc_client.execute_kw(
            "account.payment.register",
            "action_create_payments",
            [[wizard_id]],
            {"context": {"active_model": "account.move", "active_ids": move_ids}},
        )
        return {
            "move_ids": move_ids,
            "wizard_id": wizard_id,
            "result": result,
        }


class Reconcile(BaseTool):
    name = "accounting_reconcile"
    description = (
        "Reconcile journal items (account.move.line). "
        "Matches debits and credits for the given line IDs."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "line_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Account move line IDs to reconcile",
                "minItems": 2,
            },
        },
        "required": ["line_ids"],
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
        if len(line_ids) < 2:
            return {"error": "At least 2 line IDs are required to reconcile"}
        result = await rpc_client.execute_kw(
            "account.move.line",
            "reconcile",
            [line_ids],
        )
        return {"line_ids": line_ids, "reconciled": True, "result": result}


class GetBalance(BaseTool):
    name = "accounting_get_balance"
    description = (
        "Get account balances by reading journal items grouped by "
        "account. Returns debit, credit, and balance per account."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": (
                    "Optional domain filter on account.move.line, "
                    "e.g. [['date','>=','2026-01-01']]"
                ),
                "default": [],
            },
            "account_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": ("Specific account IDs to filter (optional)"),
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
            return {"error": "No RPC client available", "balances": []}
        domain = arguments.get("domain", [])
        if "account_ids" in arguments:
            domain = domain + [["account_id", "in", arguments["account_ids"]]]
        result = await rpc_client.execute_kw(
            "account.move.line",
            "read_group",
            [domain],
            {
                "fields": ["debit", "credit", "balance"],
                "groupby": ["account_id"],
            },
        )
        balances = []
        for group in result:
            balances.append(
                {
                    "account_id": group.get("account_id"),
                    "debit": group.get("debit", 0),
                    "credit": group.get("credit", 0),
                    "balance": group.get("balance", 0),
                    "count": group.get("account_id_count", 0),
                }
            )
        return {"balances": balances, "total_accounts": len(balances)}


class GenerateReport(BaseTool):
    name = "accounting_generate_report"
    description = (
        "Generate an accounting report (P&L, Balance Sheet, etc.) "
        "by calling the Odoo report engine."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "report_name": {
                "type": "string",
                "description": (
                    "Report identifier, e.g. 'account.report_financial', "
                    "'account.report_aged_receivable'"
                ),
            },
            "date_from": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format",
            },
            "date_to": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format",
            },
            "company_id": {
                "type": "integer",
                "description": "Company ID (defaults to current company)",
            },
            "options": {
                "type": "object",
                "description": ("Additional report options as key-value pairs"),
                "default": {},
            },
        },
        "required": ["report_name"],
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
        report_name = arguments["report_name"]
        options = arguments.get("options", {})
        if "date_from" in arguments:
            options["date_from"] = arguments["date_from"]
        if "date_to" in arguments:
            options["date_to"] = arguments["date_to"]
        if "company_id" in arguments:
            options["company_id"] = arguments["company_id"]
        result = await rpc_client.execute_kw(
            "account.report",
            "get_report_values",
            [report_name],
            {"options": options},
        )
        return {"report_name": report_name, "data": result}


class CreateJournalEntry(BaseTool):
    name = "accounting_create_journal_entry"
    description = (
        "Create a manual journal entry (account.move with type 'entry') "
        "with debit/credit lines."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "journal_id": {
                "type": "integer",
                "description": "Journal ID for this entry",
            },
            "date": {
                "type": "string",
                "description": "Entry date in YYYY-MM-DD format",
            },
            "ref": {
                "type": "string",
                "description": "Reference / memo",
            },
            "line_ids": {
                "type": "array",
                "description": (
                    "Journal item lines as list of dicts. Each dict "
                    "must have: account_id, name. Plus either debit "
                    "or credit (not both). Optional: partner_id, "
                    "analytic_account_id."
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["journal_id", "line_ids"],
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
            "move_type": "entry",
            "journal_id": arguments["journal_id"],
        }
        if "date" in arguments:
            values["date"] = arguments["date"]
        if "ref" in arguments:
            values["ref"] = arguments["ref"]
        # Convert line dicts to Odoo (0, 0, vals) command format
        values["line_ids"] = [(0, 0, line) for line in arguments["line_ids"]]
        move_id = await rpc_client.create("account.move", values)
        return {
            "id": move_id,
            "move_type": "entry",
            "journal_id": arguments["journal_id"],
        }


class ManageTaxes(BaseTool):
    name = "accounting_manage_taxes"
    description = (
        "Search and optionally update tax records (account.tax). "
        "Provide values to update, or omit to just search."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": (
                    "Domain filter on account.tax, "
                    "e.g. [['type_tax_use','=','sale']]"
                ),
                "default": [],
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "default": [
                    "name",
                    "amount",
                    "amount_type",
                    "type_tax_use",
                    "active",
                ],
                "description": "Fields to return",
            },
            "tax_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Specific tax IDs to update (for write)",
            },
            "values": {
                "type": "object",
                "description": (
                    "Values to write on taxes (requires tax_ids). "
                    "Omit to only search."
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
            return {"error": "No RPC client available"}
        # If tax_ids and values are provided, perform a write
        if "tax_ids" in arguments and "values" in arguments:
            success = await rpc_client.write(
                "account.tax",
                arguments["tax_ids"],
                arguments["values"],
            )
            return {
                "tax_ids": arguments["tax_ids"],
                "updated": success,
            }
        # Otherwise, search taxes
        domain = arguments.get("domain", [])
        taxes = await rpc_client.search_read(
            "account.tax",
            domain,
            fields=arguments.get(
                "fields",
                [
                    "name",
                    "amount",
                    "amount_type",
                    "type_tax_use",
                    "active",
                ],
            ),
            limit=arguments.get("limit", 80),
        )
        return {"taxes": taxes, "count": len(taxes)}


class BankReconcile(BaseTool):
    name = "accounting_bank_reconcile"
    description = (
        "Process bank statement reconciliation. Triggers the "
        "reconciliation wizard on a bank statement or its lines."
    )
    domain = "accounting"
    required_model = "account.move"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "statement_id": {
                "type": "integer",
                "description": "Bank statement ID",
            },
            "statement_line_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Specific statement line IDs to reconcile. "
                    "If omitted, processes the full statement."
                ),
            },
        },
        "required": ["statement_id"],
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
        statement_id = arguments["statement_id"]
        if "statement_line_ids" in arguments:
            line_ids = arguments["statement_line_ids"]
            result = await rpc_client.execute_kw(
                "account.bank.statement.line",
                "reconcile",
                [line_ids],
            )
            return {
                "statement_id": statement_id,
                "line_ids": line_ids,
                "result": result,
            }
        # Reconcile the entire statement
        result = await rpc_client.execute_kw(
            "account.bank.statement",
            "button_validate",
            [[statement_id]],
        )
        return {
            "statement_id": statement_id,
            "status": "validated",
            "result": result,
        }


ALL_ACCOUNTING_TOOLS = [
    CreateInvoice(),
    CreateBill(),
    PostEntry(),
    RegisterPayment(),
    Reconcile(),
    GetBalance(),
    GenerateReport(),
    CreateJournalEntry(),
    ManageTaxes(),
    BankReconcile(),
]
