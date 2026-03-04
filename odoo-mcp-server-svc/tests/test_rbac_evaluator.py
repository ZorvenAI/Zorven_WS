"""Tests for RBAC policy evaluator."""

import pytest
from unittest.mock import AsyncMock

from app.rbac.evaluator import PolicyEvaluator
from app.rbac.models import (
    Permission,
    PolicyDecision,
    PolicyResult,
    RoleDefinition,
)

# ── Fixtures ──


@pytest.fixture
def basic_roles() -> dict[str, RoleDefinition]:
    """Basic set of roles for testing."""
    return {
        "super_admin": RoleDefinition(
            name="super_admin",
            description="Full access",
            permissions=[
                Permission(
                    tool="*",
                    models=["*"],
                    operations=["read", "create", "write", "unlink"],
                )
            ],
        ),
        "sales_user": RoleDefinition(
            name="sales_user",
            description="Sales read/create",
            permissions=[
                Permission(
                    tool="*",
                    models=["crm.lead", "sale.order", "res.partner"],
                    operations=["read", "create"],
                ),
                Permission(
                    tool="*",
                    models=["product.product"],
                    operations=["read"],
                ),
            ],
        ),
        "sales_manager": RoleDefinition(
            name="sales_manager",
            description="Sales full access",
            inherits=["sales_user"],
            permissions=[
                Permission(
                    tool="*",
                    models=["crm.lead", "sale.order", "res.partner"],
                    operations=["read", "create", "write", "unlink"],
                ),
                Permission(
                    tool="*",
                    models=["sale.report"],
                    operations=["read"],
                ),
            ],
        ),
        "readonly_viewer": RoleDefinition(
            name="readonly_viewer",
            description="Read only",
            permissions=[
                Permission(
                    tool="*",
                    models=["*"],
                    operations=["read"],
                    fields_denied=["password", "password_crypt"],
                )
            ],
        ),
        "hr_user": RoleDefinition(
            name="hr_user",
            description="HR with field restrictions",
            permissions=[
                Permission(
                    tool="*",
                    models=["hr.employee"],
                    operations=["read"],
                    fields_denied=["salary", "wage"],
                ),
                Permission(
                    tool="*",
                    models=["hr.leave"],
                    operations=["read", "create"],
                ),
            ],
        ),
        "tenant_owner": RoleDefinition(
            name="tenant_owner",
            description="Tenant-scoped admin",
            inherits=["super_admin"],
            permissions=[
                Permission(
                    tool="*",
                    models=["*"],
                    operations=["read", "create", "write", "unlink"],
                    domain_filter=[["company_id", "=", "__tenant_company_id__"]],
                )
            ],
        ),
        "restricted_tool": RoleDefinition(
            name="restricted_tool",
            description="Only search_read tool",
            permissions=[
                Permission(
                    tool="search_read",
                    models=["sale.order"],
                    operations=["read"],
                )
            ],
        ),
        "field_allowed_role": RoleDefinition(
            name="field_allowed_role",
            description="Only specific fields allowed",
            permissions=[
                Permission(
                    tool="*",
                    models=["hr.employee"],
                    operations=["read"],
                    fields_allowed=["name", "department_id", "job_id"],
                )
            ],
        ),
    }


@pytest.fixture
def evaluator(basic_roles: dict[str, RoleDefinition]) -> PolicyEvaluator:
    """PolicyEvaluator without Redis caching."""
    return PolicyEvaluator(roles=basic_roles, redis_manager=None)


# ── Permission matching tests ──


class TestPermissionMatching:
    """Test basic permission matching."""

    async def test_allow_matching_model_and_operation(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Sales user can read crm.lead."""
        result = await evaluator.evaluate(
            user_roles=["sales_user"],
            tool_name="search_read",
            model="crm.lead",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_allow_create_on_permitted_model(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Sales user can create sale.order."""
        result = await evaluator.evaluate(
            user_roles=["sales_user"],
            tool_name="create",
            model="sale.order",
            operation="create",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_deny_write_for_read_only_role(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Sales user cannot write to crm.lead."""
        result = await evaluator.evaluate(
            user_roles=["sales_user"],
            tool_name="write",
            model="crm.lead",
            operation="write",
        )
        assert result.decision == PolicyDecision.DENY

    async def test_deny_unmatched_model(self, evaluator: PolicyEvaluator) -> None:
        """Sales user cannot access hr.employee."""
        result = await evaluator.evaluate(
            user_roles=["sales_user"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
        )
        assert result.decision == PolicyDecision.DENY

    async def test_wildcard_model(self, evaluator: PolicyEvaluator) -> None:
        """Super admin matches any model."""
        result = await evaluator.evaluate(
            user_roles=["super_admin"],
            tool_name="any_tool",
            model="any.model",
            operation="unlink",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_readonly_viewer_read(self, evaluator: PolicyEvaluator) -> None:
        """Readonly viewer can read any model."""
        result = await evaluator.evaluate(
            user_roles=["readonly_viewer"],
            tool_name="search_read",
            model="account.move",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_readonly_viewer_deny_write(self, evaluator: PolicyEvaluator) -> None:
        """Readonly viewer cannot write."""
        result = await evaluator.evaluate(
            user_roles=["readonly_viewer"],
            tool_name="write",
            model="account.move",
            operation="write",
        )
        assert result.decision == PolicyDecision.DENY

    async def test_tool_pattern_matching(self, evaluator: PolicyEvaluator) -> None:
        """Restricted tool role only matches search_read tool."""
        result = await evaluator.evaluate(
            user_roles=["restricted_tool"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_tool_pattern_mismatch(self, evaluator: PolicyEvaluator) -> None:
        """Restricted tool role denies other tools."""
        result = await evaluator.evaluate(
            user_roles=["restricted_tool"],
            tool_name="write",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.DENY

    async def test_unknown_role_denied(self, evaluator: PolicyEvaluator) -> None:
        """Unknown role results in denial."""
        result = await evaluator.evaluate(
            user_roles=["nonexistent_role"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.DENY

    async def test_empty_roles_denied(self, evaluator: PolicyEvaluator) -> None:
        """Empty role list results in denial."""
        result = await evaluator.evaluate(
            user_roles=[],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.DENY


# ── Inheritance tests ──


class TestInheritance:
    """Test role inheritance flattening."""

    async def test_inherited_permissions(self, evaluator: PolicyEvaluator) -> None:
        """Sales manager inherits sales_user read on product.product."""
        result = await evaluator.evaluate(
            user_roles=["sales_manager"],
            tool_name="search_read",
            model="product.product",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_child_adds_permissions(self, evaluator: PolicyEvaluator) -> None:
        """Sales manager can write (added on top of sales_user)."""
        result = await evaluator.evaluate(
            user_roles=["sales_manager"],
            tool_name="write",
            model="crm.lead",
            operation="write",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_child_exclusive_permission(self, evaluator: PolicyEvaluator) -> None:
        """Sales manager can read sale.report (own permission)."""
        result = await evaluator.evaluate(
            user_roles=["sales_manager"],
            tool_name="search_read",
            model="sale.report",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_deep_inheritance(self, evaluator: PolicyEvaluator) -> None:
        """Tenant owner inherits super_admin's wildcard access."""
        result = await evaluator.evaluate(
            user_roles=["tenant_owner"],
            tool_name="any_tool",
            model="any.model",
            operation="unlink",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_multiple_user_roles(self, evaluator: PolicyEvaluator) -> None:
        """User with both sales_user and hr_user gets combined access."""
        # Can access crm.lead (from sales_user)
        result1 = await evaluator.evaluate(
            user_roles=["sales_user", "hr_user"],
            tool_name="search_read",
            model="crm.lead",
            operation="read",
        )
        assert result1.decision == PolicyDecision.ALLOW

        # Can access hr.leave (from hr_user)
        result2 = await evaluator.evaluate(
            user_roles=["sales_user", "hr_user"],
            tool_name="create",
            model="hr.leave",
            operation="create",
        )
        assert result2.decision == PolicyDecision.ALLOW


# ── Field denial tests ──


class TestFieldDenial:
    """Test field-level access control."""

    async def test_denied_fields_blocked(self, evaluator: PolicyEvaluator) -> None:
        """Accessing denied fields returns DENY_FIELD."""
        result = await evaluator.evaluate(
            user_roles=["hr_user"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
            fields=["name", "salary"],
        )
        assert result.decision == PolicyDecision.DENY_FIELD
        assert "salary" in result.denied_fields

    async def test_non_denied_fields_allowed(self, evaluator: PolicyEvaluator) -> None:
        """Non-denied fields are allowed."""
        result = await evaluator.evaluate(
            user_roles=["hr_user"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
            fields=["name", "department_id"],
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_multiple_denied_fields(self, evaluator: PolicyEvaluator) -> None:
        """Multiple denied fields are all reported."""
        result = await evaluator.evaluate(
            user_roles=["hr_user"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
            fields=["salary", "wage"],
        )
        assert result.decision == PolicyDecision.DENY_FIELD
        assert "salary" in result.denied_fields
        assert "wage" in result.denied_fields

    async def test_readonly_viewer_password_denied(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Readonly viewer cannot access password field."""
        result = await evaluator.evaluate(
            user_roles=["readonly_viewer"],
            tool_name="search_read",
            model="res.users",
            operation="read",
            fields=["name", "password"],
        )
        assert result.decision == PolicyDecision.DENY_FIELD
        assert "password" in result.denied_fields

    async def test_no_fields_specified_allows(self, evaluator: PolicyEvaluator) -> None:
        """When no fields specified, field denial is not checked."""
        result = await evaluator.evaluate(
            user_roles=["hr_user"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
            fields=None,
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_fields_allowed_restricts(self, evaluator: PolicyEvaluator) -> None:
        """When fields_allowed is set, only those fields pass."""
        result = await evaluator.evaluate(
            user_roles=["field_allowed_role"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
            fields=["name", "salary"],
        )
        assert result.decision == PolicyDecision.DENY_FIELD
        assert "salary" in result.denied_fields

    async def test_fields_allowed_passes_valid(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Allowed fields pass validation."""
        result = await evaluator.evaluate(
            user_roles=["field_allowed_role"],
            tool_name="search_read",
            model="hr.employee",
            operation="read",
            fields=["name", "department_id"],
        )
        assert result.decision == PolicyDecision.ALLOW


# ── Domain filter injection tests ──


class TestDomainFilter:
    """Test domain filter injection."""

    async def test_domain_filter_injected(self, evaluator: PolicyEvaluator) -> None:
        """Tenant owner result includes domain filter."""
        result = await evaluator.evaluate(
            user_roles=["tenant_owner"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW
        assert len(result.domain_filter) > 0
        assert ["company_id", "=", "__tenant_company_id__"] in result.domain_filter

    async def test_no_domain_filter_for_admin(self, evaluator: PolicyEvaluator) -> None:
        """Super admin has no domain filters."""
        result = await evaluator.evaluate(
            user_roles=["super_admin"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW
        assert result.domain_filter == []

    async def test_no_domain_filter_for_basic_role(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Sales user has no domain filters."""
        result = await evaluator.evaluate(
            user_roles=["sales_user"],
            tool_name="search_read",
            model="crm.lead",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW
        assert result.domain_filter == []


# ── PolicyResult model tests ──


class TestPolicyResult:
    """Test PolicyResult model."""

    def test_allow_result(self) -> None:
        """ALLOW result has correct defaults."""
        result = PolicyResult(
            decision=PolicyDecision.ALLOW,
            reason="Access granted",
        )
        assert result.decision == PolicyDecision.ALLOW
        assert result.denied_fields == []
        assert result.domain_filter == []

    def test_deny_result_with_fields(self) -> None:
        """DENY_FIELD result contains denied fields."""
        result = PolicyResult(
            decision=PolicyDecision.DENY_FIELD,
            reason="Fields denied",
            denied_fields=["salary", "wage"],
        )
        assert result.decision == PolicyDecision.DENY_FIELD
        assert len(result.denied_fields) == 2

    def test_result_serialization(self) -> None:
        """PolicyResult round-trips through JSON."""
        result = PolicyResult(
            decision=PolicyDecision.ALLOW,
            role="admin",
            reason="Full access",
            domain_filter=[["company_id", "=", 1]],
        )
        data = result.model_dump(mode="json")
        restored = PolicyResult(**data)
        assert restored.decision == PolicyDecision.ALLOW
        assert restored.domain_filter == [["company_id", "=", 1]]


# ── Caching tests ──


class TestCaching:
    """Test caching helpers."""

    def test_cache_key_deterministic(self) -> None:
        """Same inputs produce same key."""
        k1 = PolicyEvaluator._cache_key(["admin"], "search", "res.partner", "read")
        k2 = PolicyEvaluator._cache_key(["admin"], "search", "res.partner", "read")
        assert k1 == k2
        assert k1.startswith("odoo_mcp:rbac:eval:")

    def test_cache_key_sorts_roles(self) -> None:
        """Roles are sorted for determinism."""
        k1 = PolicyEvaluator._cache_key(["b", "a"], "t", "m", "r")
        k2 = PolicyEvaluator._cache_key(["a", "b"], "t", "m", "r")
        assert k1 == k2

    def test_cache_key_differs_for_different_inputs(self) -> None:
        k1 = PolicyEvaluator._cache_key(["admin"], "search", "res.partner", "read")
        k2 = PolicyEvaluator._cache_key(["admin"], "search", "res.partner", "write")
        assert k1 != k2

    async def test_get_cached_returns_none_without_redis(self) -> None:
        evaluator = PolicyEvaluator(roles={}, redis_manager=None)
        result = await evaluator._get_cached(["admin"], "t", "m", "r")
        assert result is None

    async def test_get_cached_returns_result_from_redis(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_result.return_value = {
            "decision": "allow",
            "reason": "cached",
            "role": "",
            "denied_fields": [],
            "domain_filter": [],
        }
        evaluator = PolicyEvaluator(roles={}, redis_manager=mock_redis)
        result = await evaluator._get_cached(["admin"], "t", "m", "r")
        assert result is not None
        assert result.decision == PolicyDecision.ALLOW
        assert result.reason == "cached"

    async def test_get_cached_returns_none_on_cache_miss(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_result.return_value = None
        evaluator = PolicyEvaluator(roles={}, redis_manager=mock_redis)
        result = await evaluator._get_cached(["admin"], "t", "m", "r")
        assert result is None

    async def test_get_cached_returns_none_on_exception(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_result.side_effect = RuntimeError("fail")
        evaluator = PolicyEvaluator(roles={}, redis_manager=mock_redis)
        result = await evaluator._get_cached(["admin"], "t", "m", "r")
        assert result is None

    async def test_set_cached_noop_without_redis(self) -> None:
        evaluator = PolicyEvaluator(roles={}, redis_manager=None)
        result = PolicyResult(decision=PolicyDecision.ALLOW, reason="ok")
        # Should not raise
        await evaluator._set_cached(["admin"], "t", "m", "r", result)

    async def test_set_cached_writes_to_redis(self) -> None:
        mock_redis = AsyncMock()
        evaluator = PolicyEvaluator(roles={}, redis_manager=mock_redis)
        result = PolicyResult(decision=PolicyDecision.ALLOW, reason="ok")
        await evaluator._set_cached(["admin"], "t", "m", "r", result)
        mock_redis.set_cached_result.assert_awaited_once()

    async def test_set_cached_swallows_exception(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.set_cached_result.side_effect = RuntimeError("fail")
        evaluator = PolicyEvaluator(roles={}, redis_manager=mock_redis)
        result = PolicyResult(decision=PolicyDecision.ALLOW, reason="ok")
        # Should not raise
        await evaluator._set_cached(["admin"], "t", "m", "r", result)

    async def test_evaluate_returns_cached_result(self, basic_roles) -> None:
        """When cache has data, evaluate returns it immediately."""
        mock_redis = AsyncMock()
        mock_redis.get_cached_result.return_value = {
            "decision": "deny",
            "reason": "cached deny",
            "role": "",
            "denied_fields": [],
            "domain_filter": [],
        }
        evaluator = PolicyEvaluator(roles=basic_roles, redis_manager=mock_redis)
        result = await evaluator.evaluate(
            user_roles=["super_admin"],
            tool_name="search",
            model="res.partner",
            operation="read",
        )
        assert result.decision == PolicyDecision.DENY
        assert result.reason == "cached deny"
        # Should NOT have called set_cached since we returned early
        mock_redis.set_cached_result.assert_not_awaited()
