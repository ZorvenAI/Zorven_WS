"""Pydantic request/response schemas for Odoo MCP Server."""

from typing import Any, Optional

from pydantic import BaseModel, Field

# ── Health ──


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "odoo-mcp-server"
    version: str = "0.1.0"
    odoo_connected: bool = False


# ── Execute (agent service contract) ──


class ExecuteRequest(BaseModel):
    """Standard agent service execute request.

    Matches the contract used by content-agent, social-agent, etc.
    The orchestrator's ExternalWrapper sends this payload.
    """

    input_prompt: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    """Standard agent service execute response."""

    status: str = "success"
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


# ── MCP Protocol ──


class MCPRequest(BaseModel):
    """Generic MCP JSON-RPC request envelope."""

    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class MCPResponse(BaseModel):
    """Generic MCP JSON-RPC response envelope."""

    jsonrpc: str = "2.0"
    id: Optional[int] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


# ── Tool Schemas ──


class ToolCallRequest(BaseModel):
    """Request to invoke a specific MCP tool."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[str] = None


class ToolCallResponse(BaseModel):
    """Response from an MCP tool invocation."""

    tool_name: str
    success: bool = True
    result: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
