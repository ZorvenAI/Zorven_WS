"""Tests for the RBAC engine."""

import pytest

from app.rbac.engine import Permission, RBACEngine


@pytest.fixture
def rbac():
    return RBACEngine()


# ── VIEWER Role ──


@pytest.mark.unit
def test_viewer_denied_odoo_skills(rbac):
    """VIEWER is denied access to Odoo skills VoCA-01, 02, 03."""
    for skill_id in ("SKL-VoCA-01", "SKL-VoCA-02", "SKL-VoCA-03"):
        perm = rbac.check_permission(skill_id, "VIEWER")
        assert perm == Permission.DENY, f"{skill_id} should be DENY for VIEWER"


@pytest.mark.unit
def test_viewer_allowed_external_skills(rbac):
    """VIEWER is allowed access to external skills VoCA-05, 06, 07, 08."""
    for skill_id in ("SKL-VoCA-05", "SKL-VoCA-06", "SKL-VoCA-07", "SKL-VoCA-08"):
        perm = rbac.check_permission(skill_id, "VIEWER")
        assert perm == Permission.ALLOW, f"{skill_id} should be ALLOW for VIEWER"


@pytest.mark.unit
def test_viewer_denied_analysis_skills(rbac):
    """VIEWER is denied access to analysis skills VoCA-09, 10, 11, 12."""
    for skill_id in ("SKL-VoCA-09", "SKL-VoCA-10", "SKL-VoCA-11", "SKL-VoCA-12"):
        perm = rbac.check_permission(skill_id, "VIEWER")
        assert perm == Permission.DENY, f"{skill_id} should be DENY for VIEWER"


@pytest.mark.unit
def test_viewer_denied_persister(rbac):
    """VIEWER is denied access to VoCA-13 (report persister)."""
    perm = rbac.check_permission("SKL-VoCA-13", "VIEWER")
    assert perm == Permission.DENY


@pytest.mark.unit
def test_viewer_allowed_escalation(rbac):
    """VIEWER is allowed access to VoCA-14 (human escalation)."""
    perm = rbac.check_permission("SKL-VoCA-14", "VIEWER")
    assert perm == Permission.ALLOW


# ── EDITOR Role ──


@pytest.mark.unit
def test_editor_allowed_odoo_skills(rbac):
    """EDITOR is allowed access to Odoo skills VoCA-01, 02, 03."""
    for skill_id in ("SKL-VoCA-01", "SKL-VoCA-02", "SKL-VoCA-03"):
        perm = rbac.check_permission(skill_id, "EDITOR")
        assert perm == Permission.ALLOW, f"{skill_id} should be ALLOW for EDITOR"


@pytest.mark.unit
def test_editor_escalate_persister(rbac):
    """EDITOR gets ESCALATE for SKL-VoCA-13 (report persister)."""
    perm = rbac.check_permission("SKL-VoCA-13", "EDITOR")
    assert perm == Permission.ESCALATE


# ── OWNER & ADMIN Roles ──


@pytest.mark.unit
def test_owner_allowed_all(rbac):
    """OWNER is allowed all 14 skills."""
    for i in range(1, 15):
        skill_id = f"SKL-VoCA-{i:02d}"
        perm = rbac.check_permission(skill_id, "OWNER")
        assert perm == Permission.ALLOW, f"{skill_id} should be ALLOW for OWNER"


@pytest.mark.unit
def test_admin_allowed_all(rbac):
    """ADMIN is allowed all 14 skills."""
    for i in range(1, 15):
        skill_id = f"SKL-VoCA-{i:02d}"
        perm = rbac.check_permission(skill_id, "ADMIN")
        assert perm == Permission.ALLOW, f"{skill_id} should be ALLOW for ADMIN"


# ── get_allowed_skills ──


@pytest.mark.unit
def test_get_allowed_skills_viewer_count(rbac):
    """VIEWER should have access to: VoCA-04, 05, 06, 07, 08, 14 = 6 skills."""
    allowed = rbac.get_allowed_skills("VIEWER")
    assert len(allowed) == 6
    assert "SKL-VoCA-05" in allowed
    assert "SKL-VoCA-14" in allowed
    assert "SKL-VoCA-01" not in allowed
    assert "SKL-VoCA-13" not in allowed
