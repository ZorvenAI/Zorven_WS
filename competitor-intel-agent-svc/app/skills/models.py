"""Skill metadata, context, and result models."""

from typing import Any

from pydantic import BaseModel, Field


class SkillMeta(BaseModel):
    """Metadata describing a skill's capabilities and constraints."""

    skill_id: str = Field(..., description="Unique skill ID, e.g. SKL-CIA-01")
    name: str = Field(..., description="Machine-readable skill name")
    description: str = Field(default="", description="Human-readable description")
    allowed_roles: list[str] = Field(
        default_factory=lambda: ["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        description="Roles permitted to invoke this skill",
    )
    idempotent: bool = True
    max_retries: int = 3
    timeout_ms: int = 30000
    circuit_breaker_dependency: str = Field(
        default="",
        description="Name of the circuit breaker dependency (e.g. 'tavily', 'llm')",
    )


class SkillContext(BaseModel):
    """Execution context passed to each skill invocation."""

    session_id: str = ""
    tenant_id: str = ""
    user_role: str = "EDITOR"
    previous_skill_results: dict[str, Any] = Field(default_factory=dict)
    skill_context_text: str = Field(
        default="", description="Orchestrator-injected skill markdown context"
    )
    config: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    """Outcome of a single skill execution."""

    skill_id: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0
    retry_count: int = 0
    tokens_used: int = 0
