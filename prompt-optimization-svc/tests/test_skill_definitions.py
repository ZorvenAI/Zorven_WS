"""Unit tests for skill definition Pydantic models (US-058).

Tests SkillOutputField, SkillDefinition, and SkillsFile validators.
All tests use real Pydantic validation — no mocks.
"""

import pytest
from pydantic import ValidationError

from app.registries.skill_definitions import (
    MAX_TIMEOUT_MS,
    SKILL_ID_PATTERN,
    VALID_ROLES,
    SkillDefinition,
    SkillOutputField,
    SkillsFile,
)


def _make_skill(**overrides) -> dict:
    """Build a valid SkillDefinition dict with optional overrides."""
    base = {
        "skill_id": "SKL-TEST-01",
        "name": "Test Skill",
        "description": "A test skill for unit tests",
        "input_schema": [{"field": "input", "type": "str", "required": True}],
        "output_schema": [
            SkillOutputField(field="result", type="str"),
        ],
        "timeout_ms": 30000,
        "allowed_roles": ["OWNER", "ADMIN"],
    }
    base.update(overrides)
    return base


class TestSkillOutputField:
    """Tests for SkillOutputField validation."""

    def test_valid_output_field(self):
        f = SkillOutputField(field="brand_name", type="str", max_length=200)
        assert f.field == "brand_name"
        assert f.type == "str"
        assert f.max_length == 200

    def test_empty_field_name_raises(self):
        with pytest.raises(ValidationError, match="field name must not be empty"):
            SkillOutputField(field="", type="str")

    def test_whitespace_field_name_raises(self):
        with pytest.raises(ValidationError, match="field name must not be empty"):
            SkillOutputField(field="   ", type="str")

    def test_max_length_zero_raises(self):
        with pytest.raises(ValidationError, match="max_length must be positive"):
            SkillOutputField(field="test", type="str", max_length=0)

    def test_max_length_negative_raises(self):
        with pytest.raises(ValidationError, match="max_length must be positive"):
            SkillOutputField(field="test", type="str", max_length=-1)

    def test_max_length_none_is_valid(self):
        f = SkillOutputField(field="test", type="str", max_length=None)
        assert f.max_length is None


class TestSkillDefinition:
    """Tests for SkillDefinition validation."""

    def test_valid_skill_definition(self):
        sd = SkillDefinition(**_make_skill())
        assert sd.skill_id == "SKL-TEST-01"
        assert sd.name == "Test Skill"

    def test_invalid_skill_id_pattern(self):
        with pytest.raises(ValidationError, match="must match pattern"):
            SkillDefinition(**_make_skill(skill_id="bad-format"))

    def test_valid_skill_id_with_suffix(self):
        sd = SkillDefinition(**_make_skill(skill_id="SKL-CGA-07a"))
        assert sd.skill_id == "SKL-CGA-07a"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="name must not be empty"):
            SkillDefinition(**_make_skill(name=""))

    def test_empty_description_raises(self):
        with pytest.raises(ValidationError, match="description must not be empty"):
            SkillDefinition(**_make_skill(description=""))

    def test_timeout_negative_raises(self):
        with pytest.raises(ValidationError, match="timeout_ms must be >= 0"):
            SkillDefinition(**_make_skill(timeout_ms=-1))

    def test_timeout_exceeds_max_raises(self):
        with pytest.raises(ValidationError, match="timeout_ms must be <="):
            SkillDefinition(**_make_skill(timeout_ms=MAX_TIMEOUT_MS + 1))

    def test_timeout_at_max_is_valid(self):
        sd = SkillDefinition(**_make_skill(timeout_ms=MAX_TIMEOUT_MS))
        assert sd.timeout_ms == MAX_TIMEOUT_MS

    def test_empty_allowed_roles_raises(self):
        with pytest.raises(ValidationError, match="allowed_roles must not be empty"):
            SkillDefinition(**_make_skill(allowed_roles=[]))

    def test_invalid_role_raises(self):
        with pytest.raises(ValidationError, match="invalid roles"):
            SkillDefinition(**_make_skill(allowed_roles=["SUPERADMIN"]))

    def test_valid_roles_accepted(self):
        sd = SkillDefinition(**_make_skill(allowed_roles=["OWNER", "ADMIN"]))
        assert sd.allowed_roles == ["OWNER", "ADMIN"]


class TestSkillsFile:
    """Tests for SkillsFile root validation."""

    def test_valid_skills_file(self):
        skill = SkillDefinition(**_make_skill())
        sf = SkillsFile(skills=[skill])
        assert len(sf.skills) == 1

    def test_empty_skills_list_raises(self):
        with pytest.raises(ValidationError, match="skills list must not be empty"):
            SkillsFile(skills=[])


class TestConstants:
    """Tests for module-level constants."""

    def test_valid_roles_set(self):
        assert VALID_ROLES == {"OWNER", "ADMIN", "EDITOR", "VIEWER"}

    def test_skill_id_pattern_matches_valid(self):
        assert SKILL_ID_PATTERN.match("SKL-MRA-01")
        assert SKILL_ID_PATTERN.match("SKL-CGA-07a")

    def test_skill_id_pattern_rejects_invalid(self):
        assert not SKILL_ID_PATTERN.match("bad-format")
        assert not SKILL_ID_PATTERN.match("SKL-")
        assert not SKILL_ID_PATTERN.match("")

    def test_max_timeout_ms(self):
        assert MAX_TIMEOUT_MS == 120_000
