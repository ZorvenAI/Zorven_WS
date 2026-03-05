"""Marketing domain tools — email campaigns, mass mailings, social posts."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateCampaign(BaseTool):
    """Create an email marketing campaign (mass mailing)."""

    name = "marketing_create_campaign"
    description = (
        "Create an email marketing campaign with subject, target model, "
        "HTML body, and mailing contact lists"
    )
    domain = "marketing"
    required_model = "mailing.mailing"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "mailing_model_id": {
                "type": "integer",
                "description": (
                    "ID of the ir.model record for the target model "
                    "(e.g. mailing.contact)"
                ),
            },
            "body_html": {
                "type": "string",
                "description": "HTML body content of the email",
            },
            "contact_list_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of mailing contact list IDs",
                "default": [],
            },
        },
        "required": ["subject", "mailing_model_id", "body_html"],
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
            "subject": arguments["subject"],
            "mailing_model_id": arguments["mailing_model_id"],
            "body_html": arguments["body_html"],
        }
        if arguments.get("contact_list_ids"):
            values["contact_list_ids"] = [(6, 0, arguments["contact_list_ids"])]

        mailing_id = await rpc_client.create("mailing.mailing", values)
        return {"id": mailing_id, "model": "mailing.mailing"}


class SendMailing(BaseTool):
    """Send an existing mailing campaign immediately."""

    name = "marketing_send_mailing"
    description = (
        "Trigger immediate sending of a mailing campaign by executing "
        "the action_send_mail method"
    )
    domain = "marketing"
    required_model = "mailing.mailing"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "mailing_id": {
                "type": "integer",
                "description": "ID of the mailing.mailing record to send",
            },
        },
        "required": ["mailing_id"],
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

        mailing_id = arguments["mailing_id"]
        result = await rpc_client.execute_kw(
            "mailing.mailing",
            "action_send_mail",
            [[mailing_id]],
        )
        return {
            "id": mailing_id,
            "model": "mailing.mailing",
            "action": "action_send_mail",
            "result": result,
        }


class SchedulePost(BaseTool):
    """Schedule a social media post."""

    name = "marketing_schedule_post"
    description = (
        "Create a social media post with a message, scheduled date, "
        "and target social account IDs"
    )
    domain = "marketing"
    required_model = "social.post"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Post message content",
            },
            "scheduled_date": {
                "type": "string",
                "description": (
                    "Scheduled publish datetime in YYYY-MM-DD HH:MM:SS format"
                ),
            },
            "account_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of social account IDs to post to",
                "default": [],
            },
        },
        "required": ["message", "scheduled_date"],
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
            "message": arguments["message"],
            "scheduled_date": arguments["scheduled_date"],
        }
        if arguments.get("account_ids"):
            values["account_ids"] = [(6, 0, arguments["account_ids"])]

        post_id = await rpc_client.create("social.post", values)
        return {"id": post_id, "model": "social.post"}


# Convenience: all marketing tools for registration
ALL_MARKETING_TOOLS = [
    CreateCampaign(),
    SendMailing(),
    SchedulePost(),
]
