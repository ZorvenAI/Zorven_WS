#!/usr/bin/env python3
"""Standalone CLI validator for agent skills.yaml files (US-051).

Usage:
    python scripts/validate_skills_yaml.py <path-to-skills.yaml>
    python scripts/validate_skills_yaml.py --all

Self-contained — no cross-service imports.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator

VALID_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER"}
SKILL_ID_PATTERN = re.compile(r"^SKL-[A-Za-z0-9]+-\d{2}[a-z]?$")
MAX_TIMEOUT_MS = 120_000

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


class SkillOutputField(BaseModel):
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
            raise ValueError(f"skill_id '{v}' must match SKL-<AGENT>-<NN>[a-z]?")
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
    skills: list[SkillDefinition]

    @field_validator("skills")
    @classmethod
    def skills_not_empty(cls, v: list[SkillDefinition]) -> list[SkillDefinition]:
        if not v:
            raise ValueError("skills list must not be empty")
        return v


def validate_file(path: Path) -> tuple[bool, str]:
    """Validate a single skills.yaml file. Returns (ok, message)."""
    if not path.exists():
        return False, f"File not found: {path}"

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return False, f"YAML parse error: {e}"

    if not isinstance(data, dict):
        return False, "Root element must be a mapping with 'skills' key"

    try:
        skills_file = SkillsFile(**data)
    except Exception as e:
        return False, f"Validation error: {e}"

    # Check for duplicate skill_ids
    ids = [s.skill_id for s in skills_file.skills]
    dupes = [sid for sid in ids if ids.count(sid) > 1]
    if dupes:
        return False, f"Duplicate skill_ids: {set(dupes)}"

    return True, f"OK — {len(skills_file.skills)} skills validated"


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <skills.yaml> | --all")
        return 1

    if sys.argv[1] == "--all":
        repo_root = Path(__file__).resolve().parent.parent
        paths = [repo_root / svc / "config" / "skills.yaml" for svc in AGENT_SERVICES]
    else:
        paths = [Path(sys.argv[1])]

    all_ok = True
    for path in paths:
        ok, msg = validate_file(path)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {path.name} ({path.parent.parent.name}): {msg}")
        if not ok:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
