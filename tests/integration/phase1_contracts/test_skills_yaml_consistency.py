"""
US-051 Cross-Service Validation — Skills YAML Consistency Tests.

Validates that ALL 15 agent services have consistent, valid skills.yaml
files with no duplicate skill IDs, correct role vocabulary, and sane
timeout bounds. No mocks — all tests use real file I/O and Pydantic
validation against the actual config/skills.yaml files on disk.
"""

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

AGENT_SERVICES = [
    "market-research-agent-svc",
    "competitor-intel-agent-svc",
    "audience-persona-agent-svc",
    "trend-cultural-agent-svc",
    "voc-agent-svc",
    "brand-positioning-agent-svc",
    "brand-architecture-agent-svc",
    "brand-personality-agent-svc",
    "brand-naming-agent-svc",
    "brand-story-agent-svc",
    "campaign-architecture-agent-svc",
    "creative-generation-agent-svc",
    "ad-publishing-agent-svc",
    "campaign-optimization-agent-svc",
    "intelligence-loop-agent-svc",
]

VALID_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER"}

EXPECTED_TOTAL_SKILLS = 179  # 8+12+14+12+14+12+12+12+14+14+12+13+12+13+5

# ---------------------------------------------------------------------------
# Inline Pydantic Models (no cross-service imports)
# ---------------------------------------------------------------------------


class SkillInputField(BaseModel):
    field: str
    type: str
    required: bool = True


class SkillOutputField(BaseModel):
    field: str
    type: str
    description: Optional[str] = None
    max_length: Optional[int] = None


class SkillDefinition(BaseModel):
    skill_id: str
    name: str
    description: str
    input_schema: list[SkillInputField]
    output_schema: list[SkillOutputField]
    timeout_ms: int
    allowed_roles: list[str]
    idempotent: bool

    @field_validator("skill_id")
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        if not re.match(r"^SKL-[A-Za-z0-9]{2,6}-\d{2}[a-z]?$", v):
            raise ValueError(f"skill_id '{v}' does not match SKL-<PREFIX>-<NN> pattern")
        return v

    @field_validator("allowed_roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("allowed_roles must not be empty")
        invalid = set(v) - VALID_ROLES
        if invalid:
            raise ValueError(f"Invalid roles: {invalid}")
        return v

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"timeout_ms must be >= 0, got {v}")
        if v > 120000:
            raise ValueError(f"timeout_ms must be <= 120000, got {v}")
        return v


class SkillsFile(BaseModel):
    skills: list[SkillDefinition]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_skills_yaml(service: str) -> dict:
    """Load and parse a service's skills.yaml file."""
    path = REPO_ROOT / service / "config" / "skills.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _all_skills() -> list[tuple[str, SkillDefinition]]:
    """Return (service_name, SkillDefinition) for every skill across all services."""
    results = []
    for svc in AGENT_SERVICES:
        data = _load_skills_yaml(svc)
        parsed = SkillsFile(**data)
        for skill in parsed.skills:
            results.append((svc, skill))
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSkillsYamlConsistency:
    """Cross-service consistency checks for all 15 skills.yaml files."""

    def test_all_15_skills_yaml_files_exist(self):
        """Verify all 15 config/skills.yaml files exist on disk."""
        missing = []
        for svc in AGENT_SERVICES:
            path = REPO_ROOT / svc / "config" / "skills.yaml"
            if not path.exists():
                missing.append(str(path))
        assert missing == [], f"Missing skills.yaml files: {missing}"

    def test_global_skill_id_uniqueness(self):
        """No duplicate skill_ids across ALL 179 skills in 15 services."""
        seen: dict[str, str] = {}  # skill_id -> service
        duplicates = []
        for svc, skill in _all_skills():
            if skill.skill_id in seen:
                duplicates.append(
                    f"{skill.skill_id} in both {seen[skill.skill_id]} and {svc}"
                )
            else:
                seen[skill.skill_id] = svc
        assert duplicates == [], f"Duplicate skill_ids found: {duplicates}"

    def test_consistent_role_vocabulary(self):
        """All roles across all services are from {OWNER, ADMIN, EDITOR, VIEWER}."""
        invalid_entries = []
        for svc, skill in _all_skills():
            bad_roles = set(skill.allowed_roles) - VALID_ROLES
            if bad_roles:
                invalid_entries.append(
                    f"{svc}/{skill.skill_id}: invalid roles {bad_roles}"
                )
        assert (
            invalid_entries == []
        ), f"Invalid role vocabulary found: {invalid_entries}"

    def test_timeout_bounds_sanity(self):
        """All timeouts are in [0, 120000] ms range."""
        violations = []
        for svc, skill in _all_skills():
            if skill.timeout_ms < 0 or skill.timeout_ms > 120000:
                violations.append(
                    f"{svc}/{skill.skill_id}: timeout_ms={skill.timeout_ms}"
                )
        assert violations == [], f"Timeout out of [0, 120000] range: {violations}"

    def test_every_agent_has_at_least_one_skill(self):
        """No empty skills lists in any service."""
        empty_services = []
        for svc in AGENT_SERVICES:
            data = _load_skills_yaml(svc)
            parsed = SkillsFile(**data)
            if len(parsed.skills) == 0:
                empty_services.append(svc)
        assert (
            empty_services == []
        ), f"Services with empty skills lists: {empty_services}"

    def test_all_files_validate_against_pydantic(self):
        """Every entry in every file validates against the Pydantic schema."""
        errors = []
        for svc in AGENT_SERVICES:
            data = _load_skills_yaml(svc)
            try:
                SkillsFile(**data)
            except Exception as exc:
                errors.append(f"{svc}: {exc}")
        assert errors == [], "Validation failures:\n" + "\n".join(errors)

    def test_total_skill_count(self):
        """Total across all 15 services is exactly 179."""
        total = 0
        per_service = {}
        for svc in AGENT_SERVICES:
            data = _load_skills_yaml(svc)
            parsed = SkillsFile(**data)
            count = len(parsed.skills)
            per_service[svc] = count
            total += count
        assert total == EXPECTED_TOTAL_SKILLS, (
            f"Expected {EXPECTED_TOTAL_SKILLS} total skills, got {total}. "
            f"Per-service breakdown: {per_service}"
        )
