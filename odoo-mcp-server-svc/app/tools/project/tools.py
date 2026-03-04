"""Project domain tools — task management, timesheets, profitability."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateTask(BaseTool):
    """Create a project task with assignees, deadline, and tags."""

    name = "project_create_task"
    description = (
        "Create a new project task with name, project, assignees, "
        "deadline, description, and tags"
    )
    domain = "project"
    required_model = "project.task"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Task title",
            },
            "project_id": {
                "type": "integer",
                "description": "ID of the project to create the task in",
            },
            "user_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of user IDs to assign to the task",
                "default": [],
            },
            "date_deadline": {
                "type": "string",
                "description": "Task deadline in YYYY-MM-DD format",
            },
            "description": {
                "type": "string",
                "description": "Task description (HTML supported)",
                "default": "",
            },
            "tag_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of tag IDs to attach to the task",
                "default": [],
            },
        },
        "required": ["name", "project_id"],
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
            "project_id": arguments["project_id"],
        }

        if arguments.get("user_ids"):
            values["user_ids"] = [(6, 0, arguments["user_ids"])]
        if arguments.get("date_deadline"):
            values["date_deadline"] = arguments["date_deadline"]
        if arguments.get("description"):
            values["description"] = arguments["description"]
        if arguments.get("tag_ids"):
            values["tag_ids"] = [(6, 0, arguments["tag_ids"])]

        task_id = await rpc_client.create("project.task", values)
        return {"id": task_id, "model": "project.task"}


class UpdateTask(BaseTool):
    """Update an existing project task's fields."""

    name = "project_update_task"
    description = (
        "Update an existing project task — change stage, priority, "
        "assignees, deadline, or any other writable field"
    )
    domain = "project"
    required_model = "project.task"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "integer",
                "description": "ID of the task to update",
            },
            "values": {
                "type": "object",
                "description": (
                    "Fields to update, e.g. "
                    '{"stage_id": 4, "priority": "1", "date_deadline": "2026-04-01"}'
                ),
            },
        },
        "required": ["task_id", "values"],
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

        task_id = arguments["task_id"]
        values = arguments["values"]

        success = await rpc_client.write("project.task", [task_id], values)
        return {
            "id": task_id,
            "model": "project.task",
            "success": success,
        }


class LogTimesheet(BaseTool):
    """Log a timesheet entry against a project task."""

    name = "project_log_timesheet"
    description = (
        "Log a timesheet entry with hours worked on a specific " "project task"
    )
    domain = "project"
    required_model = "account.analytic.line"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "integer",
                "description": "ID of the task to log time against",
            },
            "project_id": {
                "type": "integer",
                "description": "ID of the project",
            },
            "unit_amount": {
                "type": "number",
                "description": "Number of hours worked",
            },
            "name": {
                "type": "string",
                "description": "Description of work performed",
                "default": "/",
            },
        },
        "required": ["task_id", "project_id", "unit_amount"],
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
            "task_id": arguments["task_id"],
            "project_id": arguments["project_id"],
            "unit_amount": arguments["unit_amount"],
            "name": arguments.get("name", "/"),
        }

        line_id = await rpc_client.create("account.analytic.line", values)
        return {"id": line_id, "model": "account.analytic.line"}


class GetProfitability(BaseTool):
    """Retrieve project profitability data."""

    name = "project_get_profitability"
    description = (
        "Get project profitability data including revenues, costs, "
        "and margins for one or more projects"
    )
    domain = "project"
    required_model = "project.project"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "project_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of project IDs to retrieve profitability for",
                "default": [],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of records to return",
                "default": 80,
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
        project_ids = arguments.get("project_ids", [])
        if project_ids:
            domain.append(("id", "in", project_ids))

        records = await rpc_client.search_read(
            "project.project",
            domain,
            fields=[
                "name",
                "partner_id",
                "analytic_account_id",
                "budget",
                "total_planned_amount",
                "total_effective_amount",
                "remaining_hours",
                "total_timesheet_time",
            ],
            limit=arguments.get("limit", 80),
        )
        return {
            "model": "project.project",
            "records": records,
            "count": len(records),
        }


# Convenience: all project tools for registration
ALL_PROJECT_TOOLS = [
    CreateTask(),
    UpdateTask(),
    LogTimesheet(),
    GetProfitability(),
]
