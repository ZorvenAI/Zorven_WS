"""Admin domain tools — users, permissions, modules, settings, data I/O, audit."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateUser(BaseTool):
    """Create a new Odoo user with login credentials and security groups."""

    name = "admin_create_user"
    description = (
        "Create a new user with login, name, and optional security " "group assignments"
    )
    domain = "admin"
    required_model = "res.users"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "login": {
                "type": "string",
                "description": "User login (typically an email address)",
            },
            "name": {
                "type": "string",
                "description": "Full name of the user",
            },
            "groups_id": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of res.groups IDs to assign",
                "default": [],
            },
        },
        "required": ["login", "name"],
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
            "login": arguments["login"],
            "name": arguments["name"],
        }
        if arguments.get("groups_id"):
            values["groups_id"] = [(6, 0, arguments["groups_id"])]

        user_id = await rpc_client.create("res.users", values)
        return {"id": user_id, "model": "res.users"}


class UpdatePermissions(BaseTool):
    """Update a user's security group assignments."""

    name = "admin_update_permissions"
    description = "Update the security groups assigned to an existing user"
    domain = "admin"
    required_model = "res.users"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "description": "ID of the user to update",
            },
            "groups_id": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Complete list of res.groups IDs to set on the user "
                    "(replaces existing)"
                ),
            },
        },
        "required": ["user_id", "groups_id"],
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

        user_id = arguments["user_id"]
        success = await rpc_client.write(
            "res.users",
            [user_id],
            {"groups_id": [(6, 0, arguments["groups_id"])]},
        )
        return {
            "id": user_id,
            "model": "res.users",
            "success": success,
        }


class ListModules(BaseTool):
    """List installed or available Odoo modules."""

    name = "admin_list_modules"
    description = (
        "Search and read Odoo modules, optionally filtered by "
        "install state (installed, uninstalled, to upgrade, etc.)"
    )
    domain = "admin"
    required_model = "ir.module.module"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": (
                    "Filter by module state: installed, uninstalled, "
                    "to upgrade, to install"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of modules to return",
                "default": 200,
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
        if arguments.get("state"):
            domain.append(("state", "=", arguments["state"]))

        records = await rpc_client.search_read(
            "ir.module.module",
            domain,
            fields=[
                "name",
                "shortdesc",
                "state",
                "installed_version",
                "summary",
            ],
            limit=arguments.get("limit", 200),
        )
        return {
            "model": "ir.module.module",
            "records": records,
            "count": len(records),
        }


class InstallModule(BaseTool):
    """Install an Odoo module immediately."""

    name = "admin_install_module"
    description = (
        "Install an Odoo module by triggering the " "button_immediate_install action"
    )
    domain = "admin"
    required_model = "ir.module.module"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "module_id": {
                "type": "integer",
                "description": "ID of the ir.module.module record to install",
            },
        },
        "required": ["module_id"],
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

        module_id = arguments["module_id"]
        result = await rpc_client.execute_kw(
            "ir.module.module",
            "button_immediate_install",
            [[module_id]],
        )
        return {
            "id": module_id,
            "model": "ir.module.module",
            "action": "button_immediate_install",
            "result": result,
        }


class GetSettings(BaseTool):
    """Get current Odoo system settings."""

    name = "admin_get_settings"
    description = (
        "Retrieve the current system configuration settings from " "res.config.settings"
    )
    domain = "admin"
    required_model = "res.config.settings"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Specific setting fields to retrieve; empty returns all"
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

        # Create a transient settings record to read current values
        settings_id = await rpc_client.create("res.config.settings", {})
        records = await rpc_client.execute_kw(
            "res.config.settings",
            "read",
            [[settings_id]],
            {"fields": arguments.get("fields", [])},
        )
        return {
            "model": "res.config.settings",
            "records": records,
        }


class UpdateSettings(BaseTool):
    """Update Odoo system settings and execute them."""

    name = "admin_update_settings"
    description = (
        "Update system configuration settings and execute them so "
        "changes take effect"
    )
    domain = "admin"
    required_model = "res.config.settings"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "values": {
                "type": "object",
                "description": (
                    "Settings fields to update, e.g. " '{"group_multi_currency": true}'
                ),
            },
        },
        "required": ["values"],
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

        # Create a transient settings record, write values, then execute
        settings_id = await rpc_client.create(
            "res.config.settings", arguments["values"]
        )
        result = await rpc_client.execute_kw(
            "res.config.settings",
            "execute",
            [[settings_id]],
        )
        return {
            "model": "res.config.settings",
            "action": "execute",
            "result": result,
        }


class ExportData(BaseTool):
    """Export data from any Odoo model using export_data."""

    name = "admin_export_data"
    description = (
        "Export data from an Odoo model by executing the export_data "
        "method with specified field names"
    )
    domain = "admin"
    required_model = "ir.model"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": "Odoo model to export from, e.g. res.partner",
            },
            "ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Record IDs to export",
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Field names to include in the export, "
                    "e.g. ['name', 'email', 'phone']"
                ),
            },
        },
        "required": ["model", "ids", "fields"],
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

        result = await rpc_client.execute_kw(
            arguments["model"],
            "export_data",
            [arguments["ids"], arguments["fields"]],
        )
        return {
            "model": arguments["model"],
            "action": "export_data",
            "result": result,
        }


class ImportData(BaseTool):
    """Import data into any Odoo model using the load method."""

    name = "admin_import_data"
    description = (
        "Import data into an Odoo model by executing the load method "
        "with field names and row data"
    )
    domain = "admin"
    required_model = "ir.model"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": "Odoo model to import into, e.g. res.partner",
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Field names matching the data columns",
            },
            "data": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "description": (
                    "Row data as a list of lists (each inner list is one record)"
                ),
            },
        },
        "required": ["model", "fields", "data"],
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

        result = await rpc_client.execute_kw(
            arguments["model"],
            "load",
            [arguments["fields"], arguments["data"]],
        )
        return {
            "model": arguments["model"],
            "action": "load",
            "result": result,
        }


class CheckPermissions(BaseTool):
    """Check model access control rules."""

    name = "admin_check_permissions"
    description = (
        "Search and read model access rules (ir.model.access) to check "
        "which groups have read/write/create/unlink permissions"
    )
    domain = "admin"
    required_model = "ir.model.access"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "model_name": {
                "type": "string",
                "description": ("Filter by Odoo model name, e.g. sale.order"),
            },
            "group_id": {
                "type": "integer",
                "description": "Filter by security group ID",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of rules to return",
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
        if arguments.get("model_name"):
            domain.append(("model_id.model", "=", arguments["model_name"]))
        if arguments.get("group_id"):
            domain.append(("group_id", "=", arguments["group_id"]))

        records = await rpc_client.search_read(
            "ir.model.access",
            domain,
            fields=[
                "name",
                "model_id",
                "group_id",
                "perm_read",
                "perm_write",
                "perm_create",
                "perm_unlink",
            ],
            limit=arguments.get("limit", 80),
        )
        return {
            "model": "ir.model.access",
            "records": records,
            "count": len(records),
        }


class ListRoles(BaseTool):
    """List Odoo security groups (roles)."""

    name = "admin_list_roles"
    description = (
        "Search and read Odoo security groups (res.groups), optionally "
        "filtered by category or name"
    )
    domain = "admin"
    required_model = "res.groups"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "category_id": {
                "type": "integer",
                "description": "Filter by module category ID",
            },
            "name_search": {
                "type": "string",
                "description": "Filter groups by name (ilike search)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of groups to return",
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
        if arguments.get("category_id"):
            domain.append(("category_id", "=", arguments["category_id"]))
        if arguments.get("name_search"):
            domain.append(("name", "ilike", arguments["name_search"]))

        records = await rpc_client.search_read(
            "res.groups",
            domain,
            fields=[
                "name",
                "full_name",
                "category_id",
                "implied_ids",
                "users",
            ],
            limit=arguments.get("limit", 80),
        )
        return {
            "model": "res.groups",
            "records": records,
            "count": len(records),
        }


class AssignRole(BaseTool):
    """Add or remove security groups from a user."""

    name = "admin_assign_role"
    description = (
        "Add or remove specific security groups from a user without "
        "replacing all existing groups"
    )
    domain = "admin"
    required_model = "res.users"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "description": "ID of the user to modify",
            },
            "add_group_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Group IDs to add to the user",
                "default": [],
            },
            "remove_group_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Group IDs to remove from the user",
                "default": [],
            },
        },
        "required": ["user_id"],
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

        user_id = arguments["user_id"]
        commands: list[tuple[int, int] | tuple[int, int, Any]] = []

        for gid in arguments.get("add_group_ids", []):
            commands.append((4, gid))
        for gid in arguments.get("remove_group_ids", []):
            commands.append((3, gid))

        if not commands:
            return {
                "id": user_id,
                "model": "res.users",
                "success": True,
                "message": "No group changes specified",
            }

        success = await rpc_client.write(
            "res.users",
            [user_id],
            {"groups_id": commands},
        )
        return {
            "id": user_id,
            "model": "res.users",
            "success": success,
        }


class AuditLog(BaseTool):
    """Search system audit / logging records."""

    name = "admin_audit_log"
    description = (
        "Search and read system audit log entries from ir.logging, "
        "optionally filtered by type, level, or function name"
    )
    domain = "admin"
    required_model = "ir.logging"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Log type filter: server or client",
            },
            "level": {
                "type": "string",
                "description": (
                    "Log level filter: DEBUG, INFO, WARNING, ERROR, CRITICAL"
                ),
            },
            "func_name": {
                "type": "string",
                "description": "Filter by function/module name (ilike)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of log entries to return",
                "default": 100,
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
        if arguments.get("type"):
            domain.append(("type", "=", arguments["type"]))
        if arguments.get("level"):
            domain.append(("level", "=", arguments["level"]))
        if arguments.get("func_name"):
            domain.append(("func_name", "ilike", arguments["func_name"]))

        records = await rpc_client.search_read(
            "ir.logging",
            domain,
            fields=[
                "name",
                "type",
                "level",
                "dbname",
                "message",
                "path",
                "func_name",
                "line",
                "create_date",
            ],
            limit=arguments.get("limit", 100),
            order="create_date desc",
        )
        return {
            "model": "ir.logging",
            "records": records,
            "count": len(records),
        }


# Convenience: all admin tools for registration
ALL_ADMIN_TOOLS = [
    CreateUser(),
    UpdatePermissions(),
    ListModules(),
    InstallModule(),
    GetSettings(),
    UpdateSettings(),
    ExportData(),
    ImportData(),
    CheckPermissions(),
    ListRoles(),
    AssignRole(),
    AuditLog(),
]
