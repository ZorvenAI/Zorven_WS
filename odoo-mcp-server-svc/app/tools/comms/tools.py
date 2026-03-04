"""Communication domain tools — messages, calendar events, contacts."""

from typing import Any, Optional

from app.tools.base import BaseTool


class SendMessage(BaseTool):
    """Send an internal message on an Odoo record's chatter."""

    name = "comms_send_message"
    description = (
        "Send an internal message (mail.message) on any Odoo record's "
        "chatter, specifying the model, record ID, body, and subject"
    )
    domain = "comms"
    required_model = "mail.message"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": (
                    "Odoo model name the message is attached to, "
                    "e.g. res.partner, sale.order"
                ),
            },
            "res_id": {
                "type": "integer",
                "description": "ID of the record to post the message on",
            },
            "body": {
                "type": "string",
                "description": "HTML body of the message",
            },
            "subject": {
                "type": "string",
                "description": "Message subject line",
                "default": "",
            },
        },
        "required": ["model", "res_id", "body"],
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
            "model": arguments["model"],
            "res_id": arguments["res_id"],
            "body": arguments["body"],
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_note",
        }
        if arguments.get("subject"):
            values["subject"] = arguments["subject"]

        message_id = await rpc_client.create("mail.message", values)
        return {"id": message_id, "model": "mail.message"}


class CreateEvent(BaseTool):
    """Create a calendar event with attendees."""

    name = "comms_create_event"
    description = (
        "Create a calendar event with a name, start/stop times, "
        "attendee partner IDs, and optional description"
    )
    domain = "comms"
    required_model = "calendar.event"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Event title",
            },
            "start": {
                "type": "string",
                "description": ("Event start datetime in YYYY-MM-DD HH:MM:SS format"),
            },
            "stop": {
                "type": "string",
                "description": ("Event end datetime in YYYY-MM-DD HH:MM:SS format"),
            },
            "partner_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of partner IDs to invite as attendees",
                "default": [],
            },
            "description": {
                "type": "string",
                "description": "Event description / notes",
                "default": "",
            },
        },
        "required": ["name", "start", "stop"],
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
            "start": arguments["start"],
            "stop": arguments["stop"],
        }
        if arguments.get("partner_ids"):
            values["partner_ids"] = [(6, 0, arguments["partner_ids"])]
        if arguments.get("description"):
            values["description"] = arguments["description"]

        event_id = await rpc_client.create("calendar.event", values)
        return {"id": event_id, "model": "calendar.event"}


class CreateContact(BaseTool):
    """Create a partner / contact record."""

    name = "comms_create_contact"
    description = (
        "Create a new partner or contact with name, email, phone, "
        "and company type (person or company)"
    )
    domain = "comms"
    required_model = "res.partner"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Contact or company name",
            },
            "email": {
                "type": "string",
                "description": "Email address",
                "default": "",
            },
            "phone": {
                "type": "string",
                "description": "Phone number",
                "default": "",
            },
            "company_type": {
                "type": "string",
                "enum": ["person", "company"],
                "description": "Whether this is an individual or a company",
                "default": "person",
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

        values: dict[str, Any] = {
            "name": arguments["name"],
            "company_type": arguments.get("company_type", "person"),
        }
        if arguments.get("email"):
            values["email"] = arguments["email"]
        if arguments.get("phone"):
            values["phone"] = arguments["phone"]

        partner_id = await rpc_client.create("res.partner", values)
        return {"id": partner_id, "model": "res.partner"}


# Convenience: all communication tools for registration
ALL_COMMS_TOOLS = [
    SendMessage(),
    CreateEvent(),
    CreateContact(),
]
