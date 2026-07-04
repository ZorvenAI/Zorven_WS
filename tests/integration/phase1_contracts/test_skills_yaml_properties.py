"""
US-051 Cross-Service Validation — Skills YAML Property Tests.

Hypothesis-based property tests for the SkillDefinition schema. Exercises
the Pydantic model with random valid and invalid inputs, plus a roundtrip
test that loads every real skills.yaml, serializes to dict, and re-validates.

No mocks — all tests use real Pydantic validation and real file I/O.
"""

import re
from pathlib import Path
from typing import Optional

import pytest
import yaml
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError, field_validator

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

    @field_validator("field")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field name must not be empty")
        return v

    @field_validator("max_length")
    @classmethod
    def validate_max_length(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError(f"max_length must be >= 0, got {v}")
        return v


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
# Hypothesis Strategies
# ---------------------------------------------------------------------------

valid_roles = st.sampled_from(["OWNER", "ADMIN", "EDITOR", "VIEWER"])
valid_role_lists = st.lists(valid_roles, min_size=1, max_size=4, unique=True)
valid_skill_ids = st.from_regex(r"SKL-[A-Za-z0-9]{2,6}-\d{2}[a-z]?", fullmatch=True)
valid_timeouts = st.integers(min_value=0, max_value=120000)
valid_field_names = st.from_regex(r"[a-z][a-z0-9_]{1,30}", fullmatch=True)
valid_field_types = st.sampled_from(
    ["string", "integer", "float", "boolean", "object", "array"]
)

valid_input_fields = st.lists(
    st.builds(
        SkillInputField,
        field=valid_field_names,
        type=valid_field_types,
        required=st.booleans(),
    ),
    min_size=1,
    max_size=5,
)

valid_output_fields = st.lists(
    st.builds(
        SkillOutputField,
        field=valid_field_names,
        type=valid_field_types,
        description=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        max_length=st.one_of(st.none(), st.integers(min_value=0, max_value=1000)),
    ),
    min_size=1,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestSkillDefinitionProperties:
    """Hypothesis property tests for SkillDefinition Pydantic model."""

    @given(
        skill_id=valid_skill_ids,
        name=st.from_regex(r"[a-z][a-z0-9_]{2,30}", fullmatch=True),
        description=st.text(min_size=5, max_size=200),
        input_schema=valid_input_fields,
        output_schema=valid_output_fields,
        timeout_ms=valid_timeouts,
        allowed_roles=valid_role_lists,
        idempotent=st.booleans(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_skill_definition_always_validates(
        self,
        skill_id,
        name,
        description,
        input_schema,
        output_schema,
        timeout_ms,
        allowed_roles,
        idempotent,
    ):
        """Any combination of valid strategy values produces a valid model."""
        skill = SkillDefinition(
            skill_id=skill_id,
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            timeout_ms=timeout_ms,
            allowed_roles=allowed_roles,
            idempotent=idempotent,
        )
        assert skill.skill_id == skill_id
        assert skill.timeout_ms == timeout_ms

    @given(
        bad_id=st.sampled_from(
            [
                "skl-mra-01",  # wrong case for SKL prefix
                "SKL-01",  # missing prefix segment
                "SKL-A-01",  # prefix too short (1 char)
                "SKL-ABCDEFGH-01",  # prefix too long (8 chars)
                "MRA-01",  # missing SKL-
                "SKL-MRA-1",  # single digit
                "SKL-MRA-001",  # three digits
                "",  # empty
                "INVALID",  # no structure
            ]
        )
    )
    @settings(max_examples=20)
    def test_invalid_skill_id_rejected(self, bad_id):
        """Invalid skill_id patterns are rejected by the validator."""
        with pytest.raises(ValidationError, match="skill_id"):
            SkillDefinition(
                skill_id=bad_id,
                name="test_skill",
                description="Test",
                input_schema=[
                    SkillInputField(field="prompt", type="string", required=True)
                ],
                output_schema=[SkillOutputField(field="result", type="string")],
                timeout_ms=30000,
                allowed_roles=["OWNER"],
                idempotent=True,
            )

    @given(timeout=st.integers(min_value=-100000, max_value=-1))
    @settings(max_examples=20)
    def test_negative_timeout_rejected(self, timeout):
        """Negative timeout values fail validation."""
        with pytest.raises(ValidationError, match="timeout_ms"):
            SkillDefinition(
                skill_id="SKL-TST-01",
                name="test_skill",
                description="Test",
                input_schema=[
                    SkillInputField(field="prompt", type="string", required=True)
                ],
                output_schema=[SkillOutputField(field="result", type="string")],
                timeout_ms=timeout,
                allowed_roles=["OWNER"],
                idempotent=True,
            )

    @given(timeout=st.integers(min_value=120001, max_value=1000000))
    @settings(max_examples=20)
    def test_excessive_timeout_rejected(self, timeout):
        """Timeout values > 120000 fail validation."""
        with pytest.raises(ValidationError, match="timeout_ms"):
            SkillDefinition(
                skill_id="SKL-TST-01",
                name="test_skill",
                description="Test",
                input_schema=[
                    SkillInputField(field="prompt", type="string", required=True)
                ],
                output_schema=[SkillOutputField(field="result", type="string")],
                timeout_ms=timeout,
                allowed_roles=["OWNER"],
                idempotent=True,
            )

    def test_empty_roles_rejected(self):
        """Empty allowed_roles list fails validation."""
        with pytest.raises(ValidationError, match="allowed_roles"):
            SkillDefinition(
                skill_id="SKL-TST-01",
                name="test_skill",
                description="Test",
                input_schema=[
                    SkillInputField(field="prompt", type="string", required=True)
                ],
                output_schema=[SkillOutputField(field="result", type="string")],
                timeout_ms=30000,
                allowed_roles=[],
                idempotent=True,
            )

    @given(
        bad_role=st.sampled_from(
            ["admin", "owner", "SUPERUSER", "ROOT", "MANAGER", "viewer", ""]
        )
    )
    @settings(max_examples=20)
    def test_invalid_role_rejected(self, bad_role):
        """Roles not in VALID_ROLES set fail validation."""
        with pytest.raises(ValidationError, match="allowed_roles"):
            SkillDefinition(
                skill_id="SKL-TST-01",
                name="test_skill",
                description="Test",
                input_schema=[
                    SkillInputField(field="prompt", type="string", required=True)
                ],
                output_schema=[SkillOutputField(field="result", type="string")],
                timeout_ms=30000,
                allowed_roles=[bad_role],
                idempotent=True,
            )

    @given(
        field_name=valid_field_names,
        field_type=valid_field_types,
        description=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        max_length=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
    )
    @settings(max_examples=30)
    def test_valid_output_field_validates(
        self, field_name, field_type, description, max_length
    ):
        """Valid SkillOutputField combinations always pass."""
        output = SkillOutputField(
            field=field_name,
            type=field_type,
            description=description,
            max_length=max_length,
        )
        assert output.field == field_name
        assert output.type == field_type

    def test_empty_field_name_rejected(self):
        """Empty field names fail validation."""
        with pytest.raises(ValidationError, match="field"):
            SkillOutputField(field="", type="string")

    @given(neg_length=st.integers(min_value=-10000, max_value=-1))
    @settings(max_examples=20)
    def test_negative_max_length_rejected(self, neg_length):
        """Negative max_length values fail validation."""
        with pytest.raises(ValidationError, match="max_length"):
            SkillOutputField(field="test_field", type="string", max_length=neg_length)

    def test_real_skills_yaml_roundtrip(self):
        """Load each real skills.yaml, serialize to dict, re-validate (roundtrip)."""
        errors = []
        for svc in AGENT_SERVICES:
            path = REPO_ROOT / svc / "config" / "skills.yaml"
            with open(path) as f:
                raw = yaml.safe_load(f)

            # First pass: parse from YAML
            try:
                parsed = SkillsFile(**raw)
            except ValidationError as exc:
                errors.append(f"{svc} (parse): {exc}")
                continue

            # Roundtrip: serialize to dict, then re-validate
            serialized = parsed.model_dump()
            try:
                reparsed = SkillsFile(**serialized)
            except ValidationError as exc:
                errors.append(f"{svc} (roundtrip): {exc}")
                continue

            # Verify equality
            if len(parsed.skills) != len(reparsed.skills):
                errors.append(
                    f"{svc}: skill count mismatch after roundtrip "
                    f"({len(parsed.skills)} vs {len(reparsed.skills)})"
                )
                continue

            for orig, rt in zip(parsed.skills, reparsed.skills):
                if orig.skill_id != rt.skill_id:
                    errors.append(
                        f"{svc}: skill_id mismatch {orig.skill_id} vs {rt.skill_id}"
                    )

        assert errors == [], "Roundtrip validation failures:\n" + "\n".join(errors)
