"""Shared data classes for skill execution."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillMeta:
    """Metadata describing a skill's identity and constraints."""

    skill_id: str
    name: str
    description: str
    allowed_roles: list[str] = field(
        default_factory=lambda: ["OWNER", "ADMIN", "EDITOR", "VIEWER"]
    )
    idempotent: bool = True
    max_retries: int = 1
    timeout_ms: int = 30000
    circuit_breaker_dependency: str = ""


@dataclass
class SkillContext:
    """Runtime context passed to every skill execution."""

    session_id: str = ""
    tenant_id: str = ""
    user_role: str = "EDITOR"
    previous_skill_results: dict[str, Any] = field(default_factory=dict)
    skill_context_text: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillResult:
    """Result returned by a skill execution."""

    skill_id: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
    retry_count: int = 0
    tokens_used: int = 0
