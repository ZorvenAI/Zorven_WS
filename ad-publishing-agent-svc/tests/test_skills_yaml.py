"""Tests for ad-publishing-agent-svc skills.yaml validation."""

import re
from pathlib import Path
from typing import Optional

import pytest
import yaml
from pydantic import BaseModel

VALID_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER"}
SKILL_ID_PATTERN = re.compile(r"^SKL-[A-Za-z0-9]+-\d{2}[a-z]?$")
MAX_TIMEOUT_MS = 120_000
SKILLS_YAML_PATH = Path(__file__).resolve().parent.parent / "config" / "skills.yaml"

EXPECTED_SKILL_COUNT = 12
EXPECTED_ID_PREFIX = "SKL-APA33-"


class SkillOutputField(BaseModel):
    field: str
    type: str
    max_length: Optional[int] = None
    required: bool = True
    enum_values: Optional[list[str]] = None


class SkillDefinition(BaseModel):
    skill_id: str
    name: str
    description: str
    input_schema: list[dict]
    output_schema: list[SkillOutputField]
    timeout_ms: int
    allowed_roles: list[str]
    idempotent: bool = True


class SkillsFile(BaseModel):
    skills: list[SkillDefinition]


@pytest.fixture(scope="module")
def raw_yaml():
    return SKILLS_YAML_PATH.read_text()


@pytest.fixture(scope="module")
def parsed_yaml():
    return yaml.safe_load(SKILLS_YAML_PATH.read_text())


@pytest.fixture(scope="module")
def validated_skills(parsed_yaml):
    return SkillsFile(**parsed_yaml)


def test_skills_yaml_exists():
    assert SKILLS_YAML_PATH.exists(), f"skills.yaml not found at {SKILLS_YAML_PATH}"


def test_skills_yaml_valid_yaml(raw_yaml):
    data = yaml.safe_load(raw_yaml)
    assert isinstance(data, dict), "YAML root should be a mapping"
    assert "skills" in data, "YAML must have a 'skills' key"


def test_skills_yaml_validates_against_pydantic(parsed_yaml):
    skills_file = SkillsFile(**parsed_yaml)
    assert len(skills_file.skills) > 0, "Must have at least one skill"


def test_correct_skill_count(validated_skills):
    assert (
        len(validated_skills.skills) == EXPECTED_SKILL_COUNT
    ), f"Expected {EXPECTED_SKILL_COUNT} skills, got {len(validated_skills.skills)}"


def test_skill_ids_match_agent_prefix(validated_skills):
    for skill in validated_skills.skills:
        assert skill.skill_id.startswith(
            EXPECTED_ID_PREFIX
        ), f"Skill ID '{skill.skill_id}' does not start with '{EXPECTED_ID_PREFIX}'"


def test_no_duplicate_skill_ids(validated_skills):
    ids = [s.skill_id for s in validated_skills.skills]
    assert len(ids) == len(set(ids)), (
        f"Duplicate skill IDs found: " f"{[x for x in ids if ids.count(x) > 1]}"
    )


def test_valid_roles(validated_skills):
    for skill in validated_skills.skills:
        for role in skill.allowed_roles:
            assert role in VALID_ROLES, (
                f"Skill '{skill.skill_id}' has invalid role '{role}'. "
                f"Valid roles: {VALID_ROLES}"
            )


def test_timeout_in_range(validated_skills):
    for skill in validated_skills.skills:
        assert 0 <= skill.timeout_ms <= MAX_TIMEOUT_MS, (
            f"Skill '{skill.skill_id}' timeout_ms={skill.timeout_ms} "
            f"out of range [0, {MAX_TIMEOUT_MS}]"
        )


def test_descriptions_not_empty(validated_skills):
    for skill in validated_skills.skills:
        assert (
            skill.description.strip()
        ), f"Skill '{skill.skill_id}' has an empty description"


def test_input_schema_entries_have_required_keys(validated_skills):
    required_keys = {"field", "type", "required"}
    for skill in validated_skills.skills:
        for i, entry in enumerate(skill.input_schema):
            missing = required_keys - set(entry.keys())
            assert not missing, (
                f"Skill '{skill.skill_id}' input_schema[{i}] "
                f"missing keys: {missing}"
            )
