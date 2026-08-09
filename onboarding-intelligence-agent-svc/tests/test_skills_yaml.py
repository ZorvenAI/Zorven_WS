"""AC-4 — the YAML contract, adapted from the fleet original.

config/skills.yaml IS Design §8. This file is what stops the two drifting:
every constraint the design states about the registry is asserted here, so a
declaration that violates one fails in CI rather than at the first invocation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SKILLS_YAML = ROOT / "config" / "skills.yaml"

EXPECTED_SKILL_COUNT = 16
EXPECTED_ID_PREFIX = "SKL-OIA-"
ID_PATTERN = re.compile(r"^SKL-OIA-\d{2}[a-z]?$")
VALID_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER"}
MAX_TIMEOUT_MS = 120000
REQUIRED_SCHEMA_KEYS = {"field", "type", "required"}
#: §8: every skill takes the same five inputs.
FLEET_INPUTS = {
    "input_prompt",
    "input_context",
    "tenant_context",
    "config",
    "previous_outputs",
}


@pytest.fixture(scope="module")
def document() -> dict:
    return yaml.safe_load(SKILLS_YAML.read_text())


@pytest.fixture(scope="module")
def skills(document) -> list[dict]:
    return document["skills"]


def test_file_parses(document):
    """The manifest must be valid YAML with the fleet envelope."""
    assert document["service"] == "onboarding-intelligence-agent"
    assert document["version"] == 1
    assert isinstance(document["skills"], list)


def test_skill_count(skills):
    assert len(skills) == EXPECTED_SKILL_COUNT


def test_ids_match_the_pattern(skills):
    for skill in skills:
        assert skill["skill_id"].startswith(EXPECTED_ID_PREFIX)
        assert ID_PATTERN.match(skill["skill_id"]), skill["skill_id"]


def test_ids_are_unique(skills):
    ids = [s["skill_id"] for s in skills]
    assert len(ids) == len(set(ids))


def test_names_are_unique(skills):
    names = [s["name"] for s in skills]
    assert len(names) == len(set(names))


def test_roles_are_drawn_only_from_the_platform_set(skills):
    """§15: there is no SYSTEM role — internal_only expresses that instead."""
    for skill in skills:
        roles = set(skill["allowed_roles"])
        assert roles, f"{skill['skill_id']} declares no roles"
        assert roles <= VALID_ROLES, f"{skill['skill_id']}: {roles - VALID_ROLES}"


def test_timeout_ceiling(skills):
    for skill in skills:
        assert 0 < skill["timeout_ms"] <= MAX_TIMEOUT_MS, skill["skill_id"]


def test_every_input_schema_entry_carries_the_required_keys(skills):
    for skill in skills:
        for entry in skill["input_schema"]:
            missing = REQUIRED_SCHEMA_KEYS - set(entry)
            assert not missing, f"{skill['skill_id']}/{entry.get('field')}: {missing}"


def test_every_skill_takes_the_fleet_standard_five_inputs(skills):
    for skill in skills:
        fields = {entry["field"] for entry in skill["input_schema"]}
        assert fields == FLEET_INPUTS, f"{skill['skill_id']}: {fields}"


def test_max_retries_is_sane(skills):
    for skill in skills:
        assert 0 <= skill["max_retries"] <= 5, skill["skill_id"]


def test_descriptions_are_present(skills):
    for skill in skills:
        assert skill.get("description", "").strip(), skill["skill_id"]


def test_streaming_skills_are_the_three_live_ones(skills):
    """§8: streaming skills 04/05/06 are driven from live_session.py only."""
    streaming = {s["skill_id"] for s in skills if s.get("streaming")}
    assert streaming == {"SKL-OIA-04", "SKL-OIA-05", "SKL-OIA-06"}


def test_internal_only_skills_carry_the_full_role_set(skills):
    """§8: SYSTEM is expressed as all roles plus internal_only: true."""
    internal = [s for s in skills if s.get("internal_only")]
    assert {s["skill_id"] for s in internal} == {
        "SKL-OIA-13",
        "SKL-OIA-15",
        "SKL-OIA-16",
    }
    for skill in internal:
        assert set(skill["allowed_roles"]) == VALID_ROLES, skill["skill_id"]


def test_declared_skills_match_the_registry_modules(skills):
    """A declaration naming a module that does not exist is a startup failure."""
    for skill in skills:
        module = ROOT / "app" / "skills" / f"{skill['name']}.py"
        assert module.is_file(), f"{skill['skill_id']} has no module {module.name}"


def test_skl_oia_02_declares_count_and_depth(skills):
    """C-03's named case, adapted to the fleet's five-input contract (D3).

    The card asks for "Input schema declares count and depth as required".
    They cannot be top-level input_schema entries: §8's contract is that every
    skill takes the same five inputs, and the sweep above enforces it across
    all sixteen. Adding two fields to one skill would break the property that
    makes the registry uniform.

    So they live inside ``input_context`` — which is already required — and
    the declaration's description is where they are contracted. Asserting on
    the description keeps the card's intent testable rather than dropping it.
    """
    declaration = next(d for d in skills if d["skill_id"] == "SKL-OIA-02")

    description = declaration["description"]
    assert "count" in description
    assert "depth" in description
    assert "quick|standard|deep" in description

    required = {f["field"] for f in declaration["input_schema"] if f["required"]}
    assert "input_context" in required, "count and depth arrive inside it"
