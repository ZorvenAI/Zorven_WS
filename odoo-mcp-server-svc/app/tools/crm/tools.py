"""CRM domain tools — 10 tools for managing leads and opportunities."""

from typing import Any, Optional

from app.tools.base import BaseTool


class SearchLeads(BaseTool):
    name = "crm_search_leads"
    description = (
        "Search CRM leads/opportunities with domain filters. "
        "Returns leads with stage, salesperson, and revenue info."
    )
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": "Odoo domain filter, e.g. [['stage_id','=',1]]",
                "default": [],
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "default": [
                    "name",
                    "contact_name",
                    "email_from",
                    "phone",
                    "stage_id",
                    "user_id",
                    "expected_revenue",
                    "priority",
                    "create_date",
                ],
                "description": "Fields to return",
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
            "order": {
                "type": "string",
                "default": "create_date desc",
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
            return {"error": "No RPC client available", "leads": []}
        domain = arguments.get("domain", [])
        rbac_domain = arguments.pop("_rbac_domain", [])
        if rbac_domain:
            domain = domain + rbac_domain
        leads = await rpc_client.search_read(
            "crm.lead",
            domain,
            fields=arguments.get(
                "fields",
                [
                    "name",
                    "contact_name",
                    "email_from",
                    "phone",
                    "stage_id",
                    "user_id",
                    "expected_revenue",
                    "priority",
                    "create_date",
                ],
            ),
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
            order=arguments.get("order", "create_date desc"),
        )
        return {"leads": leads, "count": len(leads)}


class CreateLead(BaseTool):
    name = "crm_create_lead"
    description = (
        "Create a new CRM lead/opportunity with contact details "
        "and expected revenue."
    )
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Lead/opportunity title",
            },
            "contact_name": {
                "type": "string",
                "description": "Contact person name",
            },
            "email_from": {
                "type": "string",
                "description": "Contact email address",
            },
            "phone": {
                "type": "string",
                "description": "Contact phone number",
            },
            "expected_revenue": {
                "type": "number",
                "description": "Expected revenue amount",
                "default": 0,
            },
            "priority": {
                "type": "string",
                "enum": ["0", "1", "2", "3"],
                "description": "Priority: 0=Normal, 1=Low, 2=High, 3=Very High",
                "default": "0",
            },
            "partner_id": {
                "type": "integer",
                "description": "Linked partner/customer ID",
            },
            "user_id": {
                "type": "integer",
                "description": "Salesperson (res.users) ID",
            },
            "team_id": {
                "type": "integer",
                "description": "Sales team ID",
            },
            "description": {
                "type": "string",
                "description": "Internal notes / description",
            },
        },
        "required": ["name"],
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
        lead_id = await rpc_client.create("crm.lead", values)
        return {"id": lead_id, "name": arguments["name"]}


class UpdateLead(BaseTool):
    name = "crm_update_lead"
    description = "Update fields on an existing CRM lead/opportunity."
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {
                "type": "integer",
                "description": "ID of the lead to update",
            },
            "values": {
                "type": "object",
                "description": (
                    "Dictionary of field names to new values, "
                    "e.g. {'expected_revenue': 50000}"
                ),
            },
        },
        "required": ["lead_id", "values"],
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
        lead_id = arguments["lead_id"]
        success = await rpc_client.write("crm.lead", [lead_id], arguments["values"])
        return {"id": lead_id, "success": success}


class MoveStage(BaseTool):
    name = "crm_move_stage"
    description = "Move a CRM lead/opportunity to a different pipeline stage."
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {
                "type": "integer",
                "description": "ID of the lead to move",
            },
            "stage_id": {
                "type": "integer",
                "description": "Target stage ID (crm.stage)",
            },
        },
        "required": ["lead_id", "stage_id"],
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
        lead_id = arguments["lead_id"]
        stage_id = arguments["stage_id"]
        success = await rpc_client.write("crm.lead", [lead_id], {"stage_id": stage_id})
        return {"id": lead_id, "stage_id": stage_id, "success": success}


class AssignSalesperson(BaseTool):
    name = "crm_assign_salesperson"
    description = "Assign a salesperson to a CRM lead/opportunity."
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {
                "type": "integer",
                "description": "ID of the lead",
            },
            "user_id": {
                "type": "integer",
                "description": "Salesperson (res.users) ID",
            },
        },
        "required": ["lead_id", "user_id"],
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
        lead_id = arguments["lead_id"]
        user_id = arguments["user_id"]
        success = await rpc_client.write("crm.lead", [lead_id], {"user_id": user_id})
        return {"id": lead_id, "user_id": user_id, "success": success}


class LogActivity(BaseTool):
    name = "crm_log_activity"
    description = (
        "Log a scheduled activity (call, meeting, email, etc.) " "on a CRM lead."
    )
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {
                "type": "integer",
                "description": "ID of the CRM lead",
            },
            "activity_type_id": {
                "type": "integer",
                "description": (
                    "Activity type ID (mail.activity.type), "
                    "e.g. 1=Email, 2=Call, 3=Meeting"
                ),
            },
            "summary": {
                "type": "string",
                "description": "Short summary of the activity",
            },
            "note": {
                "type": "string",
                "description": "Detailed note / description",
            },
            "date_deadline": {
                "type": "string",
                "description": "Due date in YYYY-MM-DD format",
            },
            "user_id": {
                "type": "integer",
                "description": "Assigned user ID (defaults to current user)",
            },
        },
        "required": ["lead_id", "activity_type_id", "date_deadline"],
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
            "res_model_id": await self._get_model_id(rpc_client, "crm.lead"),
            "res_id": arguments["lead_id"],
            "activity_type_id": arguments["activity_type_id"],
            "date_deadline": arguments["date_deadline"],
        }
        if "summary" in arguments:
            values["summary"] = arguments["summary"]
        if "note" in arguments:
            values["note"] = arguments["note"]
        if "user_id" in arguments:
            values["user_id"] = arguments["user_id"]
        activity_id = await rpc_client.execute_kw(
            "mail.activity",
            "create",
            [values],
        )
        return {"activity_id": activity_id, "lead_id": arguments["lead_id"]}

    @staticmethod
    async def _get_model_id(rpc_client: Any, model_name: str) -> int:
        """Resolve ir.model ID for a given model name."""
        result = await rpc_client.search_read(
            "ir.model",
            [["model", "=", model_name]],
            fields=["id"],
            limit=1,
        )
        if not result:
            raise ValueError(f"Model not found: {model_name}")
        return result[0]["id"]


class MarkWon(BaseTool):
    name = "crm_mark_won"
    description = "Mark a CRM lead/opportunity as Won."
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {
                "type": "integer",
                "description": "ID of the lead to mark as won",
            },
        },
        "required": ["lead_id"],
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
        lead_id = arguments["lead_id"]
        result = await rpc_client.execute_kw(
            "crm.lead",
            "action_set_won",
            [[lead_id]],
        )
        return {"id": lead_id, "status": "won", "result": result}


class MarkLost(BaseTool):
    name = "crm_mark_lost"
    description = "Mark a CRM lead/opportunity as Lost."
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {
                "type": "integer",
                "description": "ID of the lead to mark as lost",
            },
            "lost_reason_id": {
                "type": "integer",
                "description": "Lost reason ID (crm.lost.reason)",
            },
        },
        "required": ["lead_id"],
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
        lead_id = arguments["lead_id"]
        kwargs = {}
        if "lost_reason_id" in arguments:
            kwargs["lost_reason_id"] = arguments["lost_reason_id"]
        result = await rpc_client.execute_kw(
            "crm.lead",
            "action_set_lost",
            [[lead_id]],
            kwargs if kwargs else None,
        )
        return {"id": lead_id, "status": "lost", "result": result}


class GetPipelineStats(BaseTool):
    name = "crm_get_pipeline_stats"
    description = (
        "Get CRM pipeline statistics grouped by stage, including "
        "lead count and total expected revenue per stage."
    )
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": "Optional domain filter for leads",
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
            return {"error": "No RPC client available", "stages": []}
        domain = arguments.get("domain", [])
        rbac_domain = arguments.pop("_rbac_domain", [])
        if rbac_domain:
            domain = domain + rbac_domain
        result = await rpc_client.execute_kw(
            "crm.lead",
            "read_group",
            [domain],
            {
                "fields": ["expected_revenue"],
                "groupby": ["stage_id"],
            },
        )
        stages = []
        for group in result:
            stages.append(
                {
                    "stage_id": group.get("stage_id"),
                    "count": group.get("stage_id_count", 0),
                    "expected_revenue": group.get("expected_revenue", 0),
                }
            )
        return {"stages": stages, "total_stages": len(stages)}


class MergeLeads(BaseTool):
    name = "crm_merge_leads"
    description = (
        "Merge multiple CRM leads/opportunities into one. "
        "The first ID in the list is the target record."
    )
    domain = "crm"
    required_model = "crm.lead"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "List of lead IDs to merge. First ID becomes "
                    "the surviving record."
                ),
                "minItems": 2,
            },
        },
        "required": ["lead_ids"],
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
        lead_ids = arguments["lead_ids"]
        if len(lead_ids) < 2:
            return {"error": "At least 2 lead IDs are required to merge"}
        result = await rpc_client.execute_kw(
            "crm.lead",
            "merge_opportunity",
            [lead_ids],
        )
        return {
            "merged_into": lead_ids[0],
            "merged_ids": lead_ids[1:],
            "result": result,
        }


ALL_CRM_TOOLS = [
    SearchLeads(),
    CreateLead(),
    UpdateLead(),
    MoveStage(),
    AssignSalesperson(),
    LogActivity(),
    MarkWon(),
    MarkLost(),
    GetPipelineStats(),
    MergeLeads(),
]
