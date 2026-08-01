"""Role-to-capability matrix (Design §15), evaluated at PG-03.

The matrix is **data**, not control flow. A-06's technical note is explicit
about why: "a matrix written as if statements cannot be exhaustively tested."
:data:`MATRIX` is parameterised the same way ``tests/test_rbac.py``
parameterises it, so every role against every capability is a table lookup on
both sides.

Roles come from the verified JWT claim only — never from a request body, a
client-controlled header, or session state (§15).

Four verdicts, not two. A-06 AC-3 describes allow and deny, but §15 also uses
ESCALATE (SKL-OIA-14 for EDITOR: "permitted but routed for Admin approval")
and VIEW_RESULT (SKL-OIA-08/09 for VIEWER: may read the output, may not run
it). Collapsing either into ALLOW or DENY would lose a distinction the design
makes deliberately.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.errors import AuthorizationError


class Role(StrEnum):
    """Platform roles. There is no SYSTEM role — see :data:`INTERNAL_ONLY`."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class Verdict(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    #: Permitted, but the result is routed for Admin approval rather than applied.
    ESCALATE = "ESCALATE"
    #: May read the result; may not invoke the capability.
    VIEW_RESULT = "VIEW_RESULT"


class Capability(StrEnum):
    """Every row of the §15 matrix.

    Skill capabilities are keyed by skill id so the registry can look one up
    directly; the non-skill rows are named actions.
    """

    RESEARCH_AND_QUESTIONNAIRE = "SKL-OIA-01..03"
    LIVE_ANALYSIS = "SKL-OIA-04..06"
    ANALYZE_CAPTURED_MEDIA = "SKL-OIA-07"
    SUMMARIZE_RECORDING = "SKL-OIA-08"
    ASSESS_WORKFLOW_COVERAGE = "SKL-OIA-09"
    EXTRACT_AND_MAP_FIELDS = "SKL-OIA-10"
    REGISTER_MEETING_ASSETS = "SKL-OIA-11"
    AUTOGEN_STRATEGY_IDENTITY = "SKL-OIA-12"
    RECORD_GOLDEN_CANDIDATES = "SKL-OIA-13"
    CONFLICT_ESCALATION = "SKL-OIA-14"
    CONFIRM_KEY_FIELD = "confirm_key_field"
    EDIT_SECONDARY_FIELD = "edit_secondary_field"
    RETENTION_AND_ERASURE = "retention_and_erasure"
    CALENDAR_OAUTH_CONNECT = "calendar_oauth_connect"
    START_LIVE_SESSION = "start_live_session"
    VIEW_RECORDINGS = "view_recordings"


A, D, E, V = Verdict.ALLOW, Verdict.DENY, Verdict.ESCALATE, Verdict.VIEW_RESULT

#: The §15 table, transcribed row for row. Column order: OWNER, ADMIN, EDITOR,
#: VIEWER.
MATRIX: dict[Capability, dict[Role, Verdict]] = {
    Capability.RESEARCH_AND_QUESTIONNAIRE: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.LIVE_ANALYSIS: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.ANALYZE_CAPTURED_MEDIA: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.SUMMARIZE_RECORDING: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: V,
    },
    Capability.ASSESS_WORKFLOW_COVERAGE: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: V,
    },
    Capability.EXTRACT_AND_MAP_FIELDS: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.REGISTER_MEETING_ASSETS: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.AUTOGEN_STRATEGY_IDENTITY: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    # SYSTEM in §15. The platform has no SYSTEM role, so §8 expresses it as the
    # full role set plus internal_only: true — the registry refuses an
    # externally-originated call regardless of the caller's role.
    Capability.RECORD_GOLDEN_CANDIDATES: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.CONFLICT_ESCALATION: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: E,
        Role.VIEWER: D,
    },
    Capability.CONFIRM_KEY_FIELD: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: D,
        Role.VIEWER: D,
    },
    Capability.EDIT_SECONDARY_FIELD: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.RETENTION_AND_ERASURE: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: D,
        Role.VIEWER: D,
    },
    Capability.CALENDAR_OAUTH_CONNECT: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: D,
        Role.VIEWER: D,
    },
    Capability.START_LIVE_SESSION: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: D,
    },
    Capability.VIEW_RECORDINGS: {
        Role.OWNER: A,
        Role.ADMIN: A,
        Role.EDITOR: A,
        Role.VIEWER: A,
    },
}

#: Skill id → capability row. Skills 01–03 and 04–06 share a row in §15.
SKILL_CAPABILITY: dict[str, Capability] = {
    "SKL-OIA-01": Capability.RESEARCH_AND_QUESTIONNAIRE,
    "SKL-OIA-02": Capability.RESEARCH_AND_QUESTIONNAIRE,
    "SKL-OIA-03": Capability.RESEARCH_AND_QUESTIONNAIRE,
    "SKL-OIA-04": Capability.LIVE_ANALYSIS,
    "SKL-OIA-05": Capability.LIVE_ANALYSIS,
    "SKL-OIA-06": Capability.LIVE_ANALYSIS,
    "SKL-OIA-07": Capability.ANALYZE_CAPTURED_MEDIA,
    "SKL-OIA-08": Capability.SUMMARIZE_RECORDING,
    "SKL-OIA-09": Capability.ASSESS_WORKFLOW_COVERAGE,
    "SKL-OIA-10": Capability.EXTRACT_AND_MAP_FIELDS,
    "SKL-OIA-11": Capability.REGISTER_MEETING_ASSETS,
    "SKL-OIA-12": Capability.AUTOGEN_STRATEGY_IDENTITY,
    "SKL-OIA-13": Capability.RECORD_GOLDEN_CANDIDATES,
    "SKL-OIA-14": Capability.CONFLICT_ESCALATION,
    # 15 and 16 are internal plumbing (prompt fetch, redaction) and carry no
    # §15 row: they are never invoked by a user directly.
    "SKL-OIA-15": Capability.VIEW_RECORDINGS,
    "SKL-OIA-16": Capability.VIEW_RECORDINGS,
}


class RBACEngine:
    """Evaluates a role against a capability. Pure lookup, no side effects."""

    def __init__(self, matrix: dict[Capability, dict[Role, Verdict]] | None = None):
        self._matrix = matrix if matrix is not None else MATRIX

    def verdict(self, role: Role, capability: Capability) -> Verdict:
        """The §15 verdict. Every (role, capability) pair has one."""
        return self._matrix[capability][role]

    def verdict_for_skill(self, role: Role, skill_id: str) -> Verdict:
        capability = SKILL_CAPABILITY.get(skill_id)
        if capability is None:
            # Unknown ids are the registry's business (PG-02), not the
            # matrix's. Denying here keeps the engine total.
            return Verdict.DENY
        return self.verdict(role, capability)

    def enforce(self, role: Role, skill_id: str) -> Verdict:
        """Raise :class:`AuthorizationError` (ERR-04) unless the call may run.

        ESCALATE and VIEW_RESULT are returned rather than raised: both mean
        "not a plain allow", and the caller decides what to do with them —
        route for approval, or serve a cached result.
        """
        verdict = self.verdict_for_skill(role, skill_id)
        if verdict is Verdict.DENY:
            raise AuthorizationError(
                f"role {role.value} may not invoke {skill_id}",
                role=role.value,
                skill_id=skill_id,
            )
        return verdict
