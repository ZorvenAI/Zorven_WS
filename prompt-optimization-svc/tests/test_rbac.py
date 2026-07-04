"""Unit tests for RBAC permission matrix (US-042).

AC-4: Tests cover every cell of the matrix (4 roles × 9 permissions = 36 cells).
"""

from app.auth.rbac import (
    Decision,
    Permission,
    Role,
    check_permission,
    resolve_role,
)


# ── Matrix cell tests (AC-4: every cell) ──


class TestViewPermission:
    def test_owner_allow(self):
        assert check_permission(Role.OWNER, Permission.VIEW) == Decision.ALLOW

    def test_admin_allow(self):
        assert check_permission(Role.ADMIN, Permission.VIEW) == Decision.ALLOW

    def test_editor_allow(self):
        assert check_permission(Role.EDITOR, Permission.VIEW) == Decision.ALLOW

    def test_viewer_allow(self):
        assert check_permission(Role.VIEWER, Permission.VIEW) == Decision.ALLOW


class TestRegisterPermission:
    def test_owner_allow(self):
        assert check_permission(Role.OWNER, Permission.REGISTER) == Decision.ALLOW

    def test_admin_allow(self):
        assert check_permission(Role.ADMIN, Permission.REGISTER) == Decision.ALLOW

    def test_editor_allow(self):
        assert check_permission(Role.EDITOR, Permission.REGISTER) == Decision.ALLOW

    def test_viewer_deny(self):
        assert check_permission(Role.VIEWER, Permission.REGISTER) == Decision.DENY


class TestTriggerOptimizationPermission:
    def test_owner_allow(self):
        assert (
            check_permission(Role.OWNER, Permission.TRIGGER_OPTIMIZATION)
            == Decision.ALLOW
        )

    def test_admin_allow(self):
        assert (
            check_permission(Role.ADMIN, Permission.TRIGGER_OPTIMIZATION)
            == Decision.ALLOW
        )

    def test_editor_allow(self):
        assert (
            check_permission(Role.EDITOR, Permission.TRIGGER_OPTIMIZATION)
            == Decision.ALLOW
        )

    def test_viewer_deny(self):
        assert (
            check_permission(Role.VIEWER, Permission.TRIGGER_OPTIMIZATION)
            == Decision.DENY
        )


class TestApprovePermission:
    def test_owner_allow(self):
        assert check_permission(Role.OWNER, Permission.APPROVE) == Decision.ALLOW

    def test_admin_allow(self):
        assert check_permission(Role.ADMIN, Permission.APPROVE) == Decision.ALLOW

    def test_editor_deny(self):
        assert check_permission(Role.EDITOR, Permission.APPROVE) == Decision.DENY

    def test_viewer_deny(self):
        assert check_permission(Role.VIEWER, Permission.APPROVE) == Decision.DENY


class TestPromotePermission:
    def test_owner_allow(self):
        assert check_permission(Role.OWNER, Permission.PROMOTE) == Decision.ALLOW

    def test_admin_allow(self):
        assert check_permission(Role.ADMIN, Permission.PROMOTE) == Decision.ALLOW

    def test_editor_escalate(self):
        assert check_permission(Role.EDITOR, Permission.PROMOTE) == Decision.ESCALATE

    def test_viewer_deny(self):
        assert check_permission(Role.VIEWER, Permission.PROMOTE) == Decision.DENY


class TestCreateOverridePermission:
    def test_owner_allow(self):
        assert (
            check_permission(Role.OWNER, Permission.CREATE_OVERRIDE) == Decision.ALLOW
        )

    def test_admin_deny(self):
        assert check_permission(Role.ADMIN, Permission.CREATE_OVERRIDE) == Decision.DENY

    def test_editor_deny(self):
        assert (
            check_permission(Role.EDITOR, Permission.CREATE_OVERRIDE) == Decision.DENY
        )

    def test_viewer_deny(self):
        assert (
            check_permission(Role.VIEWER, Permission.CREATE_OVERRIDE) == Decision.DENY
        )


class TestDeleteOverridePermission:
    def test_owner_allow(self):
        assert (
            check_permission(Role.OWNER, Permission.DELETE_OVERRIDE) == Decision.ALLOW
        )

    def test_admin_deny(self):
        assert check_permission(Role.ADMIN, Permission.DELETE_OVERRIDE) == Decision.DENY

    def test_editor_deny(self):
        assert (
            check_permission(Role.EDITOR, Permission.DELETE_OVERRIDE) == Decision.DENY
        )

    def test_viewer_deny(self):
        assert (
            check_permission(Role.VIEWER, Permission.DELETE_OVERRIDE) == Decision.DENY
        )


class TestModifyConfigPermission:
    def test_owner_allow(self):
        assert check_permission(Role.OWNER, Permission.MODIFY_CONFIG) == Decision.ALLOW

    def test_admin_allow(self):
        assert check_permission(Role.ADMIN, Permission.MODIFY_CONFIG) == Decision.ALLOW

    def test_editor_deny(self):
        assert check_permission(Role.EDITOR, Permission.MODIFY_CONFIG) == Decision.DENY

    def test_viewer_deny(self):
        assert check_permission(Role.VIEWER, Permission.MODIFY_CONFIG) == Decision.DENY


class TestRollbackPermission:
    def test_owner_allow(self):
        assert check_permission(Role.OWNER, Permission.ROLLBACK) == Decision.ALLOW

    def test_admin_allow(self):
        assert check_permission(Role.ADMIN, Permission.ROLLBACK) == Decision.ALLOW

    def test_editor_deny(self):
        assert check_permission(Role.EDITOR, Permission.ROLLBACK) == Decision.DENY

    def test_viewer_deny(self):
        assert check_permission(Role.VIEWER, Permission.ROLLBACK) == Decision.DENY


# ── Enum tests ──


class TestEnums:
    def test_role_count(self):
        assert len(Role) == 4

    def test_permission_count(self):
        assert len(Permission) == 9

    def test_decision_count(self):
        assert len(Decision) == 3

    def test_all_roles(self):
        assert set(Role) == {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.VIEWER}

    def test_all_decisions(self):
        assert set(Decision) == {Decision.ALLOW, Decision.DENY, Decision.ESCALATE}


# ── resolve_role tests ──


class TestResolveRole:
    def test_owner(self):
        assert resolve_role("owner") == Role.OWNER

    def test_admin(self):
        assert resolve_role("admin") == Role.ADMIN

    def test_editor(self):
        assert resolve_role("editor") == Role.EDITOR

    def test_viewer(self):
        assert resolve_role("viewer") == Role.VIEWER

    def test_case_insensitive(self):
        assert resolve_role("OWNER") == Role.OWNER
        assert resolve_role("Admin") == Role.ADMIN

    def test_unknown_defaults_to_viewer(self):
        assert resolve_role("superuser") == Role.VIEWER

    def test_empty_defaults_to_viewer(self):
        assert resolve_role("") == Role.VIEWER

    def test_none_defaults_to_viewer(self):
        assert resolve_role(None) == Role.VIEWER
