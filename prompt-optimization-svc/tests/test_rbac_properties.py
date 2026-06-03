"""Hypothesis property tests for RBAC (US-042)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.auth.rbac import (
    Decision,
    Permission,
    Role,
    check_permission,
)


class TestRbacProperties:
    @given(st.sampled_from(list(Permission)))
    @settings(max_examples=9, deadline=None)
    def test_owner_always_allow(self, permission):
        assert check_permission(Role.OWNER, permission) == Decision.ALLOW

    @given(st.sampled_from(list(Permission)))
    @settings(max_examples=9, deadline=None)
    def test_viewer_deny_except_view(self, permission):
        decision = check_permission(Role.VIEWER, permission)
        if permission == Permission.VIEW:
            assert decision == Decision.ALLOW
        else:
            assert decision == Decision.DENY

    @given(st.sampled_from(list(Role)), st.sampled_from(list(Permission)))
    @settings(max_examples=36, deadline=None)
    def test_always_returns_valid_decision(self, role, permission):
        decision = check_permission(role, permission)
        assert decision in (Decision.ALLOW, Decision.DENY, Decision.ESCALATE)

    @given(st.sampled_from(list(Role)), st.sampled_from(list(Permission)))
    @settings(max_examples=36, deadline=None)
    def test_deterministic(self, role, permission):
        d1 = check_permission(role, permission)
        d2 = check_permission(role, permission)
        assert d1 == d2

    def test_only_one_escalate_cell(self):
        """ESCALATE only exists for EDITOR + PROMOTE."""
        escalate_count = 0
        for perm in Permission:
            for role in Role:
                if check_permission(role, perm) == Decision.ESCALATE:
                    escalate_count += 1
                    assert role == Role.EDITOR
                    assert perm == Permission.PROMOTE
        assert escalate_count == 1
