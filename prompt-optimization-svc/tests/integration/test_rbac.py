"""Integration tests for RBAC (US-042)."""

from app.auth.rbac import (
    Decision,
    Permission,
    Role,
    PERMISSION_MATRIX,
    check_permission,
)


class TestFullMatrix:
    """Validate every cell of the permission matrix."""

    EXPECTED = {
        (Permission.VIEW, Role.OWNER): Decision.ALLOW,
        (Permission.VIEW, Role.ADMIN): Decision.ALLOW,
        (Permission.VIEW, Role.EDITOR): Decision.ALLOW,
        (Permission.VIEW, Role.VIEWER): Decision.ALLOW,
        (Permission.REGISTER, Role.OWNER): Decision.ALLOW,
        (Permission.REGISTER, Role.ADMIN): Decision.ALLOW,
        (Permission.REGISTER, Role.EDITOR): Decision.ALLOW,
        (Permission.REGISTER, Role.VIEWER): Decision.DENY,
        (Permission.TRIGGER_OPTIMIZATION, Role.OWNER): Decision.ALLOW,
        (Permission.TRIGGER_OPTIMIZATION, Role.ADMIN): Decision.ALLOW,
        (Permission.TRIGGER_OPTIMIZATION, Role.EDITOR): Decision.ALLOW,
        (Permission.TRIGGER_OPTIMIZATION, Role.VIEWER): Decision.DENY,
        (Permission.APPROVE, Role.OWNER): Decision.ALLOW,
        (Permission.APPROVE, Role.ADMIN): Decision.ALLOW,
        (Permission.APPROVE, Role.EDITOR): Decision.DENY,
        (Permission.APPROVE, Role.VIEWER): Decision.DENY,
        (Permission.PROMOTE, Role.OWNER): Decision.ALLOW,
        (Permission.PROMOTE, Role.ADMIN): Decision.ALLOW,
        (Permission.PROMOTE, Role.EDITOR): Decision.ESCALATE,
        (Permission.PROMOTE, Role.VIEWER): Decision.DENY,
        (Permission.CREATE_OVERRIDE, Role.OWNER): Decision.ALLOW,
        (Permission.CREATE_OVERRIDE, Role.ADMIN): Decision.DENY,
        (Permission.CREATE_OVERRIDE, Role.EDITOR): Decision.DENY,
        (Permission.CREATE_OVERRIDE, Role.VIEWER): Decision.DENY,
        (Permission.DELETE_OVERRIDE, Role.OWNER): Decision.ALLOW,
        (Permission.DELETE_OVERRIDE, Role.ADMIN): Decision.DENY,
        (Permission.DELETE_OVERRIDE, Role.EDITOR): Decision.DENY,
        (Permission.DELETE_OVERRIDE, Role.VIEWER): Decision.DENY,
        (Permission.MODIFY_CONFIG, Role.OWNER): Decision.ALLOW,
        (Permission.MODIFY_CONFIG, Role.ADMIN): Decision.ALLOW,
        (Permission.MODIFY_CONFIG, Role.EDITOR): Decision.DENY,
        (Permission.MODIFY_CONFIG, Role.VIEWER): Decision.DENY,
        (Permission.ROLLBACK, Role.OWNER): Decision.ALLOW,
        (Permission.ROLLBACK, Role.ADMIN): Decision.ALLOW,
        (Permission.ROLLBACK, Role.EDITOR): Decision.DENY,
        (Permission.ROLLBACK, Role.VIEWER): Decision.DENY,
    }

    def test_all_36_cells(self):
        for (perm, role), expected in self.EXPECTED.items():
            actual = check_permission(role, perm)
            assert actual == expected, (
                f"Matrix mismatch: {role.value}×{perm.value} "
                f"expected {expected.value}, got {actual.value}"
            )

    def test_matrix_complete(self):
        """Every Permission×Role combination is defined."""
        for perm in Permission:
            assert perm in PERMISSION_MATRIX, f"Missing permission: {perm}"
            for role in Role:
                assert (
                    role in PERMISSION_MATRIX[perm]
                ), f"Missing role {role} for {perm}"
