"""Tests for Admin domain tools."""

from unittest.mock import AsyncMock

from app.tools.admin.tools import (
    ALL_ADMIN_TOOLS,
    AssignRole,
    AuditLog,
    CheckPermissions,
    CreateUser,
    ExportData,
    GetSettings,
    ImportData,
    InstallModule,
    ListModules,
    ListRoles,
    UpdatePermissions,
    UpdateSettings,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateUser:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 10
        tool = CreateUser()
        result = await tool.execute(
            {"login": "jane@example.com", "name": "Jane Doe"}, ctx
        )
        assert result["id"] == 10
        assert result["model"] == "res.users"

    async def test_create_no_client(self):
        tool = CreateUser()
        result = await tool.execute({"login": "jane@example.com", "name": "Jane Doe"})
        assert "error" in result


class TestUpdatePermissions:
    async def test_update_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = UpdatePermissions()
        result = await tool.execute({"user_id": 10, "groups_id": [1, 2, 3]}, ctx)
        assert result["success"] is True
        assert result["id"] == 10
        assert result["model"] == "res.users"


class TestListModules:
    async def test_list_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "sale",
                "shortdesc": "Sales",
                "state": "installed",
            }
        ]
        tool = ListModules()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "ir.module.module"
        assert len(result["records"]) == 1


class TestInstallModule:
    async def test_install_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = InstallModule()
        result = await tool.execute({"module_id": 50}, ctx)
        assert result["id"] == 50
        assert result["model"] == "ir.module.module"
        assert result["action"] == "button_immediate_install"


class TestGetSettings:
    async def test_get_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 99
        ctx["rpc_client"].execute_kw.return_value = [
            {"id": 99, "group_multi_currency": True}
        ]
        tool = GetSettings()
        result = await tool.execute({}, ctx)
        assert result["model"] == "res.config.settings"
        assert "records" in result


class TestUpdateSettings:
    async def test_update_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 100
        ctx["rpc_client"].execute_kw.return_value = True
        tool = UpdateSettings()
        result = await tool.execute({"values": {"group_multi_currency": True}}, ctx)
        assert result["model"] == "res.config.settings"
        assert result["action"] == "execute"


class TestExportData:
    async def test_export_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = {
            "datas": [["John", "john@example.com"]]
        }
        tool = ExportData()
        result = await tool.execute(
            {
                "model": "res.partner",
                "ids": [1],
                "fields": ["name", "email"],
            },
            ctx,
        )
        assert result["model"] == "res.partner"
        assert result["action"] == "export_data"
        assert "result" in result


class TestImportData:
    async def test_import_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = {
            "ids": [1, 2],
            "messages": [],
        }
        tool = ImportData()
        result = await tool.execute(
            {
                "model": "res.partner",
                "fields": ["name", "email"],
                "data": [
                    ["Alice", "alice@example.com"],
                    ["Bob", "bob@example.com"],
                ],
            },
            ctx,
        )
        assert result["model"] == "res.partner"
        assert result["action"] == "load"
        assert "result" in result


class TestCheckPermissions:
    async def test_check_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "sale.order access",
                "model_id": [10, "sale.order"],
                "perm_read": True,
                "perm_write": True,
                "perm_create": True,
                "perm_unlink": False,
            }
        ]
        tool = CheckPermissions()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "ir.model.access"
        assert len(result["records"]) == 1


class TestListRoles:
    async def test_list_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "Sales / User",
                "full_name": "Sales / User",
            }
        ]
        tool = ListRoles()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "res.groups"
        assert len(result["records"]) == 1


class TestAssignRole:
    async def test_assign_add_groups(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = AssignRole()
        result = await tool.execute({"user_id": 10, "add_group_ids": [1, 2]}, ctx)
        assert result["success"] is True
        assert result["id"] == 10
        assert result["model"] == "res.users"

    async def test_assign_no_changes(self):
        ctx = _mock_context()
        tool = AssignRole()
        result = await tool.execute({"user_id": 10}, ctx)
        assert result["success"] is True
        assert "No group changes" in result["message"]


class TestAuditLog:
    async def test_audit_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "odoo.modules",
                "type": "server",
                "level": "INFO",
                "message": "Module loaded",
            }
        ]
        tool = AuditLog()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert result["model"] == "ir.logging"
        assert len(result["records"]) == 1


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_update_permissions_no_client(self):
        tool = UpdatePermissions()
        result = await tool.execute({"user_id": 1, "groups_id": [1]})
        assert "error" in result

    async def test_list_modules_no_client(self):
        tool = ListModules()
        result = await tool.execute({})
        assert "error" in result

    async def test_install_module_no_client(self):
        tool = InstallModule()
        result = await tool.execute({"module_id": 1})
        assert "error" in result

    async def test_get_settings_no_client(self):
        tool = GetSettings()
        result = await tool.execute({})
        assert "error" in result

    async def test_update_settings_no_client(self):
        tool = UpdateSettings()
        result = await tool.execute({"values": {"test": True}})
        assert "error" in result

    async def test_export_data_no_client(self):
        tool = ExportData()
        result = await tool.execute(
            {"model": "res.partner", "ids": [1], "fields": ["name"]}
        )
        assert "error" in result

    async def test_import_data_no_client(self):
        tool = ImportData()
        result = await tool.execute(
            {"model": "res.partner", "fields": ["name"], "data": [["test"]]}
        )
        assert "error" in result

    async def test_check_permissions_no_client(self):
        tool = CheckPermissions()
        result = await tool.execute({})
        assert "error" in result

    async def test_list_roles_no_client(self):
        tool = ListRoles()
        result = await tool.execute({})
        assert "error" in result

    async def test_assign_role_no_client(self):
        tool = AssignRole()
        result = await tool.execute({"user_id": 1})
        assert "error" in result

    async def test_audit_log_no_client(self):
        tool = AuditLog()
        result = await tool.execute({})
        assert "error" in result


class TestAllAdminTools:
    def test_all_tools_count(self):
        assert len(ALL_ADMIN_TOOLS) == 12

    def test_all_tools_have_names(self):
        for tool in ALL_ADMIN_TOOLS:
            assert tool.name != ""
            assert tool.domain == "admin"
