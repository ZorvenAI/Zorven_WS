"""Tests for tool dispatcher — RBAC, audit, and error paths."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import BaseTool
from app.tools.dispatcher import ToolDispatcher
from app.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeTool(BaseTool):
    """Minimal concrete tool for testing the dispatcher."""

    name = "fake_tool"
    description = "A fake tool for testing"
    domain = "test"
    required_model = "test.model"
    required_operation = "read"
    input_schema = {"type": "object", "properties": {}}

    async def execute(self, arguments, context=None):
        return {"ok": True, "args": arguments}


class FailingTool(BaseTool):
    """Tool that always raises during execute."""

    name = "failing_tool"
    description = "A tool that always fails"
    domain = "test"
    required_model = "test.model"
    required_operation = "write"
    input_schema = {"type": "object", "properties": {}}

    async def execute(self, arguments, context=None):
        raise RuntimeError("Tool execution boom")


def _make_registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


# ---------------------------------------------------------------------------
# Basic dispatch
# ---------------------------------------------------------------------------


class TestDispatchBasic:
    async def test_unknown_tool_returns_error(self):
        registry = ToolRegistry()
        dispatcher = ToolDispatcher(registry)
        result = await dispatcher.dispatch("nonexistent", {})
        assert result["success"] is False
        assert "Unknown tool: nonexistent" in result["error"]
        assert result["duration_ms"] == 0

    async def test_successful_dispatch(self):
        dispatcher = ToolDispatcher(_make_registry(FakeTool()))
        result = await dispatcher.dispatch("fake_tool", {"key": "val"})
        assert result["success"] is True
        assert result["result"] == {"ok": True, "args": {"key": "val"}}
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], float)

    async def test_context_defaults_to_empty_dict(self):
        dispatcher = ToolDispatcher(_make_registry(FakeTool()))
        result = await dispatcher.dispatch("fake_tool", {}, context=None)
        assert result["success"] is True

    async def test_tool_execution_exception_returns_error(self):
        dispatcher = ToolDispatcher(_make_registry(FailingTool()))
        result = await dispatcher.dispatch("failing_tool", {})
        assert result["success"] is False
        assert "Tool execution boom" in result["error"]
        assert result["duration_ms"] > 0


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class TestDispatchRBAC:
    async def test_rbac_pass_no_domain_filter(self):
        """RBAC succeeds, policy has no domain_filter."""
        rbac = AsyncMock()
        policy = MagicMock()
        policy.domain_filter = None
        rbac.enforce_or_raise.return_value = policy

        dispatcher = ToolDispatcher(_make_registry(FakeTool()), rbac_engine=rbac)
        result = await dispatcher.dispatch(
            "fake_tool",
            {"x": 1},
            {"user_roles": ["admin"]},
        )
        assert result["success"] is True
        # _rbac_domain should NOT be in arguments passed to tool
        assert "_rbac_domain" not in result["result"]["args"]
        rbac.enforce_or_raise.assert_awaited_once_with(
            user_roles=["admin"],
            tool_name="fake_tool",
            model="test.model",
            operation="read",
        )

    async def test_rbac_pass_with_domain_filter(self):
        """RBAC succeeds, policy has domain_filter — injected into arguments."""
        rbac = AsyncMock()
        policy = MagicMock()
        policy.domain_filter = [("active", "=", True)]
        rbac.enforce_or_raise.return_value = policy

        dispatcher = ToolDispatcher(_make_registry(FakeTool()), rbac_engine=rbac)
        result = await dispatcher.dispatch(
            "fake_tool",
            {"x": 1},
            {"user_roles": ["sales"]},
        )
        assert result["success"] is True
        assert result["result"]["args"]["_rbac_domain"] == [("active", "=", True)]

    async def test_rbac_pass_policy_is_none(self):
        """RBAC returns None policy — no domain injection, tool still runs."""
        rbac = AsyncMock()
        rbac.enforce_or_raise.return_value = None

        dispatcher = ToolDispatcher(_make_registry(FakeTool()), rbac_engine=rbac)
        result = await dispatcher.dispatch("fake_tool", {})
        assert result["success"] is True

    async def test_rbac_raises_exception(self):
        """RBAC enforcement fails — returns error with duration."""
        rbac = AsyncMock()
        rbac.enforce_or_raise.side_effect = PermissionError("Access denied")

        dispatcher = ToolDispatcher(_make_registry(FakeTool()), rbac_engine=rbac)
        result = await dispatcher.dispatch(
            "fake_tool",
            {},
            {"user_roles": ["guest"]},
        )
        assert result["success"] is False
        assert "Access denied" in result["error"]
        assert result["duration_ms"] > 0

    async def test_rbac_default_user_roles_empty(self):
        """When context has no user_roles key, defaults to empty list."""
        rbac = AsyncMock()
        rbac.enforce_or_raise.return_value = None

        dispatcher = ToolDispatcher(_make_registry(FakeTool()), rbac_engine=rbac)
        await dispatcher.dispatch("fake_tool", {}, {})
        rbac.enforce_or_raise.assert_awaited_once_with(
            user_roles=[],
            tool_name="fake_tool",
            model="test.model",
            operation="read",
        )

    async def test_no_rbac_engine_skips_check(self):
        """When rbac_engine is None, RBAC check is skipped entirely."""
        dispatcher = ToolDispatcher(_make_registry(FakeTool()))
        result = await dispatcher.dispatch("fake_tool", {})
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


class TestDispatchAudit:
    async def test_audit_logger_called_on_success(self):
        audit = MagicMock()
        dispatcher = ToolDispatcher(_make_registry(FakeTool()), audit_logger=audit)
        result = await dispatcher.dispatch("fake_tool", {}, {"tenant_id": "t1"})
        assert result["success"] is True
        audit.log.assert_called_once()
        call_kwargs = audit.log.call_args[1]
        assert call_kwargs["tool_name"] == "fake_tool"
        assert call_kwargs["tenant_id"] == "t1"
        assert call_kwargs["success"] is True
        assert call_kwargs["error"] == ""
        assert call_kwargs["duration_ms"] > 0

    async def test_audit_logger_called_on_tool_failure(self):
        audit = MagicMock()
        dispatcher = ToolDispatcher(_make_registry(FailingTool()), audit_logger=audit)
        result = await dispatcher.dispatch("failing_tool", {}, {"tenant_id": "t2"})
        assert result["success"] is False
        audit.log.assert_called_once()
        call_kwargs = audit.log.call_args[1]
        assert call_kwargs["tool_name"] == "failing_tool"
        assert call_kwargs["tenant_id"] == "t2"
        assert call_kwargs["success"] is False
        assert "Tool execution boom" in call_kwargs["error"]

    async def test_audit_logger_called_on_rbac_failure(self):
        rbac = AsyncMock()
        rbac.enforce_or_raise.side_effect = PermissionError("Forbidden")
        audit = MagicMock()
        dispatcher = ToolDispatcher(
            _make_registry(FakeTool()),
            rbac_engine=rbac,
            audit_logger=audit,
        )
        result = await dispatcher.dispatch("fake_tool", {}, {"tenant_id": "t3"})
        assert result["success"] is False
        audit.log.assert_called_once()
        call_kwargs = audit.log.call_args[1]
        assert call_kwargs["success"] is False
        assert "Forbidden" in call_kwargs["error"]
        assert call_kwargs["tenant_id"] == "t3"

    async def test_no_audit_logger_does_not_crash(self):
        """Dispatcher works without audit_logger (logger.info still runs)."""
        dispatcher = ToolDispatcher(_make_registry(FakeTool()))
        result = await dispatcher.dispatch("fake_tool", {})
        assert result["success"] is True

    async def test_audit_tenant_defaults_to_unknown(self):
        """When context has no tenant_id, _audit uses 'unknown'."""
        audit = MagicMock()
        dispatcher = ToolDispatcher(_make_registry(FakeTool()), audit_logger=audit)
        await dispatcher.dispatch("fake_tool", {}, {})
        call_kwargs = audit.log.call_args[1]
        assert call_kwargs["tenant_id"] == "unknown"

    async def test_audit_tenant_defaults_to_unknown_with_none_context(self):
        """When context is None (defaults to {}), tenant_id is 'unknown'."""
        audit = MagicMock()
        dispatcher = ToolDispatcher(_make_registry(FakeTool()), audit_logger=audit)
        await dispatcher.dispatch("fake_tool", {}, None)
        call_kwargs = audit.log.call_args[1]
        assert call_kwargs["tenant_id"] == "unknown"


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


class TestDispatchDuration:
    async def test_duration_is_positive_on_success(self):
        dispatcher = ToolDispatcher(_make_registry(FakeTool()))
        result = await dispatcher.dispatch("fake_tool", {})
        assert result["duration_ms"] >= 0

    async def test_duration_is_rounded_on_success(self):
        dispatcher = ToolDispatcher(_make_registry(FakeTool()))
        result = await dispatcher.dispatch("fake_tool", {})
        # round(x, 2) returns float
        assert isinstance(result["duration_ms"], float)

    async def test_unknown_tool_has_zero_duration(self):
        dispatcher = ToolDispatcher(ToolRegistry())
        result = await dispatcher.dispatch("nope", {})
        assert result["duration_ms"] == 0
