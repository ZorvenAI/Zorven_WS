"""AC-3 — the §15 matrix, exhaustively.

The matrix is data precisely so this test can be a table sweep. Every role
against every capability, with both allow and deny asserted — a matrix written
as `if` statements could not be covered this way, which is why A-06's technical
note forbids one.
"""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError, ErrorCode
from app.rbac.engine import (
    MATRIX,
    SKILL_CAPABILITY,
    Capability,
    RBACEngine,
    Role,
    Verdict,
)

pytestmark = pytest.mark.unit

ALL_PAIRS = [(role, cap) for cap in Capability for role in Role]


@pytest.fixture
def engine() -> RBACEngine:
    return RBACEngine()


def test_matrix_exhaustive(engine):
    """Every (role, capability) pair resolves to exactly one known verdict."""
    assert len(ALL_PAIRS) == len(list(Role)) * len(list(Capability)) == 64

    for role, capability in ALL_PAIRS:
        verdict = engine.verdict(role, capability)
        assert isinstance(verdict, Verdict), (role, capability)


def test_matrix_covers_every_capability():
    """A capability missing a row would KeyError at runtime, not in review."""
    assert set(MATRIX) == set(Capability)
    for capability, row in MATRIX.items():
        assert set(row) == set(Role), capability


@pytest.mark.parametrize("role,capability", ALL_PAIRS)
def test_every_pair_is_decided(engine, role, capability):
    assert engine.verdict(role, capability) in set(Verdict)


def test_both_allow_and_deny_are_present():
    """A matrix that only ever allows would pass a weaker test vacuously."""
    verdicts = {v for row in MATRIX.values() for v in row.values()}
    assert Verdict.ALLOW in verdicts
    assert Verdict.DENY in verdicts
    assert Verdict.ESCALATE in verdicts
    assert Verdict.VIEW_RESULT in verdicts


# ── The specific rows §15 argues for ─────────────────────────


def test_viewer_is_denied_the_research_and_extraction_skills(engine):
    for skill_id in ("SKL-OIA-01", "SKL-OIA-04", "SKL-OIA-10", "SKL-OIA-12"):
        assert engine.verdict_for_skill(Role.VIEWER, skill_id) is Verdict.DENY


def test_viewer_may_read_summaries_and_coverage(engine):
    """§15 gives VIEWER VIEW RESULT on 08 and 09 — not ALLOW, not DENY."""
    for skill_id in ("SKL-OIA-08", "SKL-OIA-09"):
        assert engine.verdict_for_skill(Role.VIEWER, skill_id) is Verdict.VIEW_RESULT


def test_editor_escalates_on_conflict_resolution(engine):
    """SKL-OIA-14: permitted, but routed for Admin approval."""
    assert engine.verdict_for_skill(Role.EDITOR, "SKL-OIA-14") is Verdict.ESCALATE
    assert engine.verdict_for_skill(Role.ADMIN, "SKL-OIA-14") is Verdict.ALLOW


def test_editor_cannot_confirm_a_key_field(engine):
    """§15's deliberate asymmetry: extraction is reversible, confirmation is not."""
    assert engine.verdict(Role.EDITOR, Capability.CONFIRM_KEY_FIELD) is Verdict.DENY
    assert engine.verdict(Role.EDITOR, Capability.EDIT_SECONDARY_FIELD) is Verdict.ALLOW


def test_editor_cannot_touch_retention_or_calendar(engine):
    assert engine.verdict(Role.EDITOR, Capability.RETENTION_AND_ERASURE) is Verdict.DENY
    assert (
        engine.verdict(Role.EDITOR, Capability.CALENDAR_OAUTH_CONNECT) is Verdict.DENY
    )


def test_everyone_may_view_recordings(engine):
    for role in Role:
        assert engine.verdict(role, Capability.VIEW_RECORDINGS) is Verdict.ALLOW


def test_every_skill_id_maps_to_a_capability():
    """A skill absent from the map would silently deny in production."""
    assert len(SKILL_CAPABILITY) == 16
    for skill_id, capability in SKILL_CAPABILITY.items():
        assert capability in MATRIX, skill_id


# ── Enforcement ──────────────────────────────────────────────


def test_enforce_raises_err_04_on_denial(engine):
    """AC-3, corrected: role denial is ERR-04, not ERR-03 (§18.4)."""
    with pytest.raises(AuthorizationError) as exc:
        engine.enforce(Role.VIEWER, "SKL-OIA-01")

    error = exc.value
    assert error.code is ErrorCode.ROLE_DENIED
    assert error.code.value == "ERR-04"
    assert error.http_status == 403
    assert error.retryable is False


def test_denial_body_carries_no_request_payload(engine):
    """AC-3: the event and the response name the role and skill, nothing else."""
    with pytest.raises(AuthorizationError) as exc:
        engine.enforce(Role.VIEWER, "SKL-OIA-10")

    body = exc.value.to_body()
    assert set(body) == {"error_code", "message", "retryable"}
    assert exc.value.context == {"role": "VIEWER", "skill_id": "SKL-OIA-10"}


def test_enforce_returns_the_verdict_when_not_denied(engine):
    assert engine.enforce(Role.ADMIN, "SKL-OIA-01") is Verdict.ALLOW
    assert engine.enforce(Role.EDITOR, "SKL-OIA-14") is Verdict.ESCALATE
    assert engine.enforce(Role.VIEWER, "SKL-OIA-08") is Verdict.VIEW_RESULT


def test_an_unknown_skill_denies_rather_than_raising_keyerror(engine):
    """The engine stays total; unknown ids are the registry's business."""
    assert engine.verdict_for_skill(Role.OWNER, "SKL-OIA-99") is Verdict.DENY


# ── Regression cover for PR #534 review findings ──────────────────────────


def test_internal_only_skills_allow_every_role_in_the_matrix(engine):
    """The matrix must agree with the full role set the YAML declares.

    Review finding: RECORD_GOLDEN_CANDIDATES denied VIEWER while §8 declares
    all four roles and marks it internal_only. An internal pipeline running
    under a VIEWER's session would have been denied by RBAC before the origin
    gate ever spoke. Externally the skill is unreachable for every role, so
    the gate — not this row — is the control.
    """
    for skill_id in ("SKL-OIA-13", "SKL-OIA-15", "SKL-OIA-16"):
        for role in Role:
            assert engine.verdict_for_skill(role, skill_id) is not Verdict.DENY, (
                f"{skill_id} denies {role.value} in the matrix, which would "
                "block an internal caller before the origin gate applies"
            )


def test_matrix_agrees_with_the_declared_roles_for_internal_only_skills():
    """Cross-check the matrix against config/skills.yaml rather than a constant."""
    from pathlib import Path as _Path

    import yaml

    root = _Path(__file__).resolve().parents[1]
    declarations = yaml.safe_load((root / "config" / "skills.yaml").read_text())
    engine = RBACEngine()

    for declaration in declarations["skills"]:
        if not declaration.get("internal_only"):
            continue
        declared = set(declaration["allowed_roles"])
        assert declared == {r.value for r in Role}, declaration["skill_id"]
        for role in Role:
            verdict = engine.verdict_for_skill(role, declaration["skill_id"])
            assert verdict is not Verdict.DENY, (
                f"{declaration['skill_id']} declares {sorted(declared)} but the "
                f"matrix denies {role.value}"
            )
