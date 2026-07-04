"""Pydantic models for agent skill definitions (US-051).

These models define the canonical schema for config/skills.yaml files
across all 15 Zorven agent services. Used by SkillRegistryReader (US-052)
to load skills programmatically.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator

VALID_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER"}
SKILL_ID_PATTERN = re.compile(r"^SKL-[A-Za-z0-9]+-\d{2}[a-z]?$")
MAX_TIMEOUT_MS = 120_000


class SkillOutputField(BaseModel):
    """Schema definition for a single output field of a skill."""

    field: str
    type: str
    max_length: Optional[int] = None
    required: bool = True
    enum_values: Optional[list[str]] = None

    @field_validator("field")
    @classmethod
    def field_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field name must not be empty")
        return v

    @field_validator("max_length")
    @classmethod
    def max_length_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("max_length must be positive")
        return v


class SkillDefinition(BaseModel):
    """Schema for a single skill entry in skills.yaml."""

    skill_id: str
    name: str
    description: str
    input_schema: list[dict]
    output_schema: list[SkillOutputField]
    timeout_ms: int
    allowed_roles: list[str]
    idempotent: bool = True

    @field_validator("skill_id")
    @classmethod
    def skill_id_matches_pattern(cls, v: str) -> str:
        if not SKILL_ID_PATTERN.match(v):
            raise ValueError(
                f"skill_id '{v}' must match pattern SKL-<AGENT>-<NN>[a-z]?"
            )
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be empty")
        return v

    @field_validator("timeout_ms")
    @classmethod
    def timeout_in_range(cls, v: int) -> int:
        if v < 0:
            raise ValueError("timeout_ms must be >= 0")
        if v > MAX_TIMEOUT_MS:
            raise ValueError(f"timeout_ms must be <= {MAX_TIMEOUT_MS}")
        return v

    @field_validator("allowed_roles")
    @classmethod
    def roles_valid(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("allowed_roles must not be empty")
        invalid = set(v) - VALID_ROLES
        if invalid:
            raise ValueError(f"invalid roles: {invalid}")
        return v


class SkillsFile(BaseModel):
    """Root schema for a skills.yaml file."""

    skills: list[SkillDefinition]

    @field_validator("skills")
    @classmethod
    def skills_not_empty(cls, v: list[SkillDefinition]) -> list[SkillDefinition]:
        if not v:
            raise ValueError("skills list must not be empty")
        return v
