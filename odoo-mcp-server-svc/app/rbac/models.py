"""RBAC models for Odoo MCP Server."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DENY_FIELD = "deny_field"
    ESCALATE = "escalate"


class Permission(BaseModel):
    """A single permission entry in a role definition."""

    tool: str = "*"  # Tool name pattern (glob), "*" = all
    models: list[str] = Field(default_factory=lambda: ["*"])  # Odoo model patterns
    operations: list[str] = Field(
        default_factory=lambda: ["read"]
    )  # read, create, write, unlink
    fields_allowed: list[str] = Field(default_factory=list)  # empty = all
    fields_denied: list[str] = Field(default_factory=list)
    domain_filter: list[Any] = Field(
        default_factory=list
    )  # Odoo domain filter injected into queries


class RoleDefinition(BaseModel):
    """A role with permissions and optional inheritance."""

    name: str
    description: str = ""
    inherits: list[str] = Field(default_factory=list)  # Parent role names
    permissions: list[Permission] = Field(default_factory=list)


class PolicyResult(BaseModel):
    """Result of a policy evaluation."""

    decision: PolicyDecision
    role: str = ""
    reason: str = ""
    denied_fields: list[str] = Field(default_factory=list)
    domain_filter: list[Any] = Field(default_factory=list)
