"""
Request/response schemas for odoo-worker-agent-svc.

Follows the standard agent service contract used by all microservices
in this monorepo, with additional fields for persona and PAOR tracking.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    """Standard agent service request from the pipeline orchestrator."""

    input_prompt: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    """Standard agent service response with persona and PAOR extensions."""

    status: str = "success"
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    result_data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    persona_used: Optional[str] = None
    tools_called: list[str] = Field(default_factory=list)
    reasoning_steps: int = 0


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    service: str = "odoo-worker-agent-svc"
