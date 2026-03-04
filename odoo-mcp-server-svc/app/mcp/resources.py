"""MCP Resources — Odoo data resources exposed via MCP protocol.

11 Odoo resources + 5 RAG resources = 16 total.
"""

import json
import logging
from typing import Any, Optional

from mcp.types import Resource

logger = logging.getLogger(__name__)


class ResourceRegistry:
    """Registry for MCP resources."""

    def __init__(
        self,
        rpc_client: Optional[Any] = None,
        rag_client: Optional[Any] = None,
    ) -> None:
        self.rpc_client = rpc_client
        self.rag_client = rag_client

    def list_resources(self) -> list[Resource]:
        """Return all available MCP resources."""
        resources = [
            # Odoo resources
            Resource(
                uri="odoo://schema/{model}",
                name="Odoo Model Schema",
                description="Get field definitions for any Odoo model",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://config/modules",
                name="Installed Modules",
                description="List of installed Odoo modules",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://config/company",
                name="Company Info",
                description="Current company configuration",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://config/users",
                name="System Users",
                description="List of Odoo users",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://dashboard/sales",
                name="Sales Dashboard",
                description="Sales KPIs and pipeline summary",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://dashboard/inventory",
                name="Inventory Dashboard",
                description="Stock levels and transfer summary",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://dashboard/accounting",
                name="Accounting Dashboard",
                description="Financial KPIs and cash flow",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://dashboard/hr",
                name="HR Dashboard",
                description="Employee stats and leave summary",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://rbac/effective_roles",
                name="Effective Roles",
                description="Current user's effective RBAC roles and permissions",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://rbac/pending_approvals",
                name="Pending Approvals",
                description="Items awaiting RBAC escalation approval",
                mimeType="application/json",
            ),
            Resource(
                uri="odoo://tenant/info",
                name="Tenant Info",
                description="Current tenant configuration and status",
                mimeType="application/json",
            ),
            # RAG resources
            Resource(
                uri="rag://knowledge/{query}",
                name="Knowledge Query",
                description="Search RAG knowledge store",
                mimeType="application/json",
            ),
            Resource(
                uri="rag://documents/list",
                name="Document List",
                description="List documents in RAG store",
                mimeType="application/json",
            ),
            Resource(
                uri="rag://documents/{doc_id}",
                name="Document Detail",
                description="Get a specific document from RAG store",
                mimeType="application/json",
            ),
            Resource(
                uri="rag://context/{model}/{record_id}",
                name="Record Context",
                description="Get RAG context for an Odoo record",
                mimeType="application/json",
            ),
            Resource(
                uri="rag://stats",
                name="RAG Store Stats",
                description="RAG store statistics and health",
                mimeType="application/json",
            ),
        ]
        return resources

    async def read(self, uri: str) -> str:
        """Read a resource by URI."""
        if uri.startswith("odoo://schema/"):
            model = uri.replace("odoo://schema/", "")
            return await self._read_schema(model)
        elif uri == "odoo://config/modules":
            return await self._read_modules()
        elif uri == "odoo://config/company":
            return await self._read_company()
        elif uri == "odoo://config/users":
            return await self._read_users()
        elif uri == "odoo://dashboard/sales":
            return await self._read_sales_dashboard()
        elif uri == "odoo://dashboard/inventory":
            return await self._read_inventory_dashboard()
        elif uri == "odoo://dashboard/accounting":
            return await self._read_accounting_dashboard()
        elif uri == "odoo://dashboard/hr":
            return await self._read_hr_dashboard()
        elif uri == "odoo://rbac/effective_roles":
            return json.dumps({"roles": [], "note": "RBAC context required"})
        elif uri == "odoo://rbac/pending_approvals":
            return json.dumps({"approvals": []})
        elif uri == "odoo://tenant/info":
            return json.dumps({"tenant": "default", "status": "active"})
        elif uri.startswith("rag://"):
            return await self._read_rag_resource(uri)
        return json.dumps({"error": f"Unknown resource: {uri}"})

    async def _read_schema(self, model: str) -> str:
        if self.rpc_client is None:
            return json.dumps({"model": model, "error": "No Odoo connection"})
        try:
            fields = await self.rpc_client.fields_get(model)
            return json.dumps({"model": model, "fields": fields})
        except Exception as exc:
            return json.dumps({"model": model, "error": str(exc)})

    async def _read_modules(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            modules = await self.rpc_client.search_read(
                "ir.module.module",
                [["state", "=", "installed"]],
                fields=["name", "shortdesc", "state", "installed_version"],
            )
            return json.dumps({"modules": modules})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_company(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            companies = await self.rpc_client.search_read(
                "res.company",
                [],
                fields=["name", "email", "phone", "currency_id", "country_id"],
                limit=1,
            )
            return json.dumps({"company": companies[0] if companies else {}})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_users(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            users = await self.rpc_client.search_read(
                "res.users",
                [["active", "=", True]],
                fields=["name", "login", "groups_id"],
                limit=100,
            )
            return json.dumps({"users": users})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_sales_dashboard(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            orders = await self.rpc_client.search_read(
                "sale.order",
                [["state", "in", ["sale", "done"]]],
                fields=["name", "amount_total", "state", "date_order"],
                limit=20,
            )
            leads = await self.rpc_client.search_count(
                "crm.lead", [["type", "=", "opportunity"]]
            )
            return json.dumps({"recent_orders": orders, "open_opportunities": leads})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_inventory_dashboard(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            pickings = await self.rpc_client.search_read(
                "stock.picking",
                [["state", "not in", ["done", "cancel"]]],
                fields=["name", "state", "picking_type_id", "scheduled_date"],
                limit=20,
            )
            return json.dumps({"pending_transfers": pickings})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_accounting_dashboard(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            invoices = await self.rpc_client.search_read(
                "account.move",
                [
                    ["move_type", "=", "out_invoice"],
                    ["payment_state", "!=", "paid"],
                ],
                fields=["name", "amount_total", "payment_state", "date"],
                limit=20,
            )
            return json.dumps({"unpaid_invoices": invoices})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_hr_dashboard(self) -> str:
        if self.rpc_client is None:
            return json.dumps({"error": "No Odoo connection"})
        try:
            employees = await self.rpc_client.search_count(
                "hr.employee", [["active", "=", True]]
            )
            leaves = await self.rpc_client.search_count(
                "hr.leave", [["state", "=", "confirm"]]
            )
            return json.dumps({"active_employees": employees, "pending_leaves": leaves})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _read_rag_resource(self, uri: str) -> str:
        if self.rag_client is None:
            return json.dumps({"error": "RAG service not configured"})
        try:
            if uri.startswith("rag://knowledge/"):
                query = uri.replace("rag://knowledge/", "")
                result = await self.rag_client.query(query)
                return json.dumps(result)
            elif uri == "rag://documents/list":
                result = await self.rag_client.list_documents()
                return json.dumps(result)
            elif uri.startswith("rag://documents/"):
                doc_id = uri.replace("rag://documents/", "")
                result = await self.rag_client.get_document(doc_id)
                return json.dumps(result)
            elif uri.startswith("rag://context/"):
                parts = uri.replace("rag://context/", "").split("/")
                if len(parts) == 2:
                    result = await self.rag_client.get_context(parts[0], int(parts[1]))
                    return json.dumps(result)
            elif uri == "rag://stats":
                result = await self.rag_client.get_stats()
                return json.dumps(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"error": f"Unknown RAG resource: {uri}"})
