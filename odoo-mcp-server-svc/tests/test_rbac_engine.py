"""Tests for RBAC engine — enforcing, permissive, disabled modes."""

import logging

import pytest

from app.rbac.engine import RBACDeniedError, RBACEngine
from app.rbac.evaluator import PolicyEvaluator
from app.rbac.models import (
    Permission,
    PolicyDecision,
    RoleDefinition,
)

# ── Fixtures ──


@pytest.fixture
def roles() -> dict[str, RoleDefinition]:
    """Minimal role set for engine tests."""
    return {
        "admin": RoleDefinition(
            name="admin",
            description="Admin role",
            permissions=[
                Permission(
                    tool="*",
                    models=["*"],
                    operations=["read", "create", "write", "unlink"],
                )
            ],
        ),
        "viewer": RoleDefinition(
            name="viewer",
            description="Read only",
            permissions=[
                Permission(
                    tool="*",
                    models=["*"],
                    operations=["read"],
                    fields_denied=["password"],
                )
            ],
        ),
        "sales": RoleDefinition(
            name="sales",
            description="Sales access",
            permissions=[
                Permission(
                    tool="*",
                    models=["sale.order", "crm.lead"],
                    operations=["read", "create"],
                )
            ],
        ),
    }


@pytest.fixture
def evaluator(roles: dict[str, RoleDefinition]) -> PolicyEvaluator:
    """PolicyEvaluator without caching."""
    return PolicyEvaluator(roles=roles, redis_manager=None)


@pytest.fixture
def enforcing_engine(evaluator: PolicyEvaluator) -> RBACEngine:
    """Engine in enforcing mode."""
    return RBACEngine(evaluator=evaluator, enforcement="enforcing")


@pytest.fixture
def permissive_engine(evaluator: PolicyEvaluator) -> RBACEngine:
    """Engine in permissive mode."""
    return RBACEngine(evaluator=evaluator, enforcement="permissive")


@pytest.fixture
def disabled_engine(evaluator: PolicyEvaluator) -> RBACEngine:
    """Engine in disabled mode."""
    return RBACEngine(evaluator=evaluator, enforcement="disabled")


# ── Constructor tests ──


class TestEngineInit:
    """Test RBACEngine initialization."""

    def test_valid_modes(self, evaluator: PolicyEvaluator) -> None:
        """All three valid modes are accepted."""
        for mode in ("enforcing", "permissive", "disabled"):
            engine = RBACEngine(evaluator=evaluator, enforcement=mode)
            assert engine.enforcement == mode

    def test_invalid_mode_raises(self, evaluator: PolicyEvaluator) -> None:
        """Invalid enforcement mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid enforcement mode"):
            RBACEngine(evaluator=evaluator, enforcement="invalid")

    def test_default_mode(self, evaluator: PolicyEvaluator) -> None:
        """Default mode is enforcing."""
        engine = RBACEngine(evaluator=evaluator)
        assert engine.enforcement == "enforcing"


# ── Enforcing mode tests ──


class TestEnforcingMode:
    """Test enforcing mode — deny raises exceptions."""

    async def test_allow_passes(self, enforcing_engine: RBACEngine) -> None:
        """Allowed access returns ALLOW result."""
        result = await enforcing_engine.enforce_or_raise(
            user_roles=["admin"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_deny_raises_error(self, enforcing_engine: RBACEngine) -> None:
        """Denied access raises RBACDeniedError."""
        with pytest.raises(RBACDeniedError) as exc_info:
            await enforcing_engine.enforce_or_raise(
                user_roles=["sales"],
                tool_name="write",
                model="hr.employee",
                operation="write",
            )
        assert exc_info.value.result.decision == PolicyDecision.DENY

    async def test_deny_field_raises_error(self, enforcing_engine: RBACEngine) -> None:
        """Field denial raises RBACDeniedError."""
        with pytest.raises(RBACDeniedError) as exc_info:
            await enforcing_engine.enforce_or_raise(
                user_roles=["viewer"],
                tool_name="search_read",
                model="res.users",
                operation="read",
                fields=["name", "password"],
            )
        assert exc_info.value.result.decision == PolicyDecision.DENY_FIELD
        assert "password" in exc_info.value.result.denied_fields

    async def test_check_access_does_not_raise(
        self, enforcing_engine: RBACEngine
    ) -> None:
        """check_access returns result without raising."""
        result = await enforcing_engine.check_access(
            user_roles=["sales"],
            tool_name="write",
            model="hr.employee",
            operation="write",
        )
        assert result.decision == PolicyDecision.DENY
        # No exception raised

    async def test_error_message_contains_reason(
        self, enforcing_engine: RBACEngine
    ) -> None:
        """RBACDeniedError message includes the reason."""
        with pytest.raises(RBACDeniedError) as exc_info:
            await enforcing_engine.enforce_or_raise(
                user_roles=["sales"],
                tool_name="unlink",
                model="account.move",
                operation="unlink",
            )
        assert "RBAC denied" in str(exc_info.value)

    async def test_error_has_result_attribute(
        self, enforcing_engine: RBACEngine
    ) -> None:
        """RBACDeniedError exposes the PolicyResult."""
        with pytest.raises(RBACDeniedError) as exc_info:
            await enforcing_engine.enforce_or_raise(
                user_roles=["sales"],
                tool_name="unlink",
                model="account.move",
                operation="unlink",
            )
        assert isinstance(exc_info.value.result.decision, PolicyDecision)

    async def test_enforcing_logs_warning(
        self, enforcing_engine: RBACEngine, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Enforcing mode logs a warning on denial."""
        with caplog.at_level(logging.WARNING):
            with pytest.raises(RBACDeniedError):
                await enforcing_engine.enforce_or_raise(
                    user_roles=["sales"],
                    tool_name="write",
                    model="hr.employee",
                    operation="write",
                )
        assert "RBAC DENIED (enforcing)" in caplog.text


# ── Permissive mode tests ──


class TestPermissiveMode:
    """Test permissive mode — deny logs but does not raise."""

    async def test_allow_passes(self, permissive_engine: RBACEngine) -> None:
        """Allowed access returns ALLOW result."""
        result = await permissive_engine.enforce_or_raise(
            user_roles=["admin"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_deny_does_not_raise(self, permissive_engine: RBACEngine) -> None:
        """Denied access returns DENY but does not raise."""
        result = await permissive_engine.enforce_or_raise(
            user_roles=["sales"],
            tool_name="write",
            model="hr.employee",
            operation="write",
        )
        assert result.decision == PolicyDecision.DENY
        # No exception

    async def test_deny_field_does_not_raise(
        self, permissive_engine: RBACEngine
    ) -> None:
        """Field denial returns DENY_FIELD but does not raise."""
        result = await permissive_engine.enforce_or_raise(
            user_roles=["viewer"],
            tool_name="search_read",
            model="res.users",
            operation="read",
            fields=["name", "password"],
        )
        assert result.decision == PolicyDecision.DENY_FIELD
        # No exception

    async def test_permissive_logs_warning(
        self,
        permissive_engine: RBACEngine,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Permissive mode logs a warning on denial."""
        with caplog.at_level(logging.WARNING):
            await permissive_engine.enforce_or_raise(
                user_roles=["sales"],
                tool_name="write",
                model="hr.employee",
                operation="write",
            )
        assert "RBAC DENIED (permissive" in caplog.text
        assert "allowing" in caplog.text


# ── Disabled mode tests ──


class TestDisabledMode:
    """Test disabled mode — skips evaluation entirely."""

    async def test_always_allows(self, disabled_engine: RBACEngine) -> None:
        """Disabled mode returns ALLOW for any request."""
        result = await disabled_engine.enforce_or_raise(
            user_roles=[],
            tool_name="unlink",
            model="ir.config_parameter",
            operation="unlink",
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_allows_without_roles(self, disabled_engine: RBACEngine) -> None:
        """Disabled mode works even with empty roles."""
        result = await disabled_engine.check_access(
            user_roles=[],
            tool_name="write",
            model="res.users",
            operation="write",
            fields=["password"],
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_reason_indicates_disabled(self, disabled_engine: RBACEngine) -> None:
        """Result reason indicates enforcement is disabled."""
        result = await disabled_engine.check_access(
            user_roles=[],
            tool_name="any",
            model="any",
            operation="any",
        )
        assert "disabled" in result.reason.lower()

    async def test_no_domain_filter_when_disabled(
        self, disabled_engine: RBACEngine
    ) -> None:
        """Disabled mode returns empty domain filter."""
        result = await disabled_engine.check_access(
            user_roles=["admin"],
            tool_name="search_read",
            model="sale.order",
            operation="read",
        )
        assert result.domain_filter == []


# ── check_access vs enforce_or_raise ──


class TestCheckAccessVsEnforce:
    """Test the difference between check_access and enforce_or_raise."""

    async def test_check_access_never_raises(
        self, enforcing_engine: RBACEngine
    ) -> None:
        """check_access never raises, even in enforcing mode."""
        result = await enforcing_engine.check_access(
            user_roles=["sales"],
            tool_name="unlink",
            model="account.move",
            operation="unlink",
        )
        assert result.decision == PolicyDecision.DENY

    async def test_enforce_or_raise_raises_in_enforcing(
        self, enforcing_engine: RBACEngine
    ) -> None:
        """enforce_or_raise raises in enforcing mode."""
        with pytest.raises(RBACDeniedError):
            await enforcing_engine.enforce_or_raise(
                user_roles=["sales"],
                tool_name="unlink",
                model="account.move",
                operation="unlink",
            )

    async def test_both_return_same_decision(
        self, permissive_engine: RBACEngine
    ) -> None:
        """Both methods return the same decision."""
        check_result = await permissive_engine.check_access(
            user_roles=["sales"],
            tool_name="write",
            model="hr.employee",
            operation="write",
        )
        enforce_result = await permissive_engine.enforce_or_raise(
            user_roles=["sales"],
            tool_name="write",
            model="hr.employee",
            operation="write",
        )
        assert check_result.decision == enforce_result.decision
