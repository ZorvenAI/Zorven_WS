"""Tests for RBAC engine — permission matrix validation."""

import pytest

from app.rbac.engine import RBAC_MATRIX, RBACEngine


class TestRBACEngine:
    def test_owner_has_all_skills(self):
        engine = RBACEngine()
        allowed = engine.get_allowed_skills("OWNER")
        assert len(allowed) == 8

    def test_admin_has_all_skills(self):
        engine = RBACEngine()
        allowed = engine.get_allowed_skills("ADMIN")
        assert len(allowed) == 8

    def test_editor_has_all_skills(self):
        engine = RBACEngine()
        allowed = engine.get_allowed_skills("EDITOR")
        assert len(allowed) == 8

    def test_viewer_denied_synthesis(self):
        engine = RBACEngine()
        allowed = engine.get_allowed_skills("VIEWER")
        assert "SKL-MRA-03" not in allowed  # synthesis
        assert "SKL-MRA-06" not in allowed  # report gen
        assert "SKL-MRA-07" not in allowed  # RAG indexing

    def test_viewer_allowed_search(self):
        engine = RBACEngine()
        allowed = engine.get_allowed_skills("VIEWER")
        assert "SKL-MRA-01" in allowed
        assert "SKL-MRA-04" in allowed
        assert "SKL-MRA-05" in allowed
        assert "SKL-MRA-08" in allowed

    def test_check_permission_allow(self):
        engine = RBACEngine()
        decision = engine.check_permission("SKL-MRA-01", "VIEWER")
        assert decision.decision == "ALLOW"

    def test_check_permission_deny(self):
        engine = RBACEngine()
        decision = engine.check_permission("SKL-MRA-03", "VIEWER")
        assert decision.decision == "DENY"

    def test_check_unknown_skill_denied(self):
        engine = RBACEngine()
        decision = engine.check_permission("SKL-UNKNOWN", "OWNER")
        assert decision.decision == "DENY"
        assert "Unknown skill" in decision.reason

    def test_disabled_allows_all(self):
        engine = RBACEngine(enabled=False)
        decision = engine.check_permission("SKL-MRA-03", "VIEWER")
        assert decision.decision == "ALLOW"
        assert "disabled" in decision.reason

    def test_disabled_returns_all_skills(self):
        engine = RBACEngine(enabled=False)
        allowed = engine.get_allowed_skills("VIEWER")
        assert len(allowed) == 8

    def test_is_write_skill(self):
        engine = RBACEngine()
        assert engine.is_write_skill("SKL-MRA-06") is True
        assert engine.is_write_skill("SKL-MRA-07") is True
        assert engine.is_write_skill("SKL-MRA-01") is False

    def test_matrix_has_8_skills(self):
        assert len(RBAC_MATRIX) == 8

    def test_all_skills_have_owner(self):
        for skill_id, roles in RBAC_MATRIX.items():
            assert "OWNER" in roles, f"{skill_id} missing OWNER"
