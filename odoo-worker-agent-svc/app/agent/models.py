"""Pydantic models for the PAOR reasoning loop."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A planned or executed MCP tool call."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result from an executed MCP tool call."""

    tool_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class PlanOutput(BaseModel):
    """Output from the PLAN phase of the PAOR loop."""

    thought: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    is_complete: bool = False
    final_answer: str = ""


class ReflectionOutput(BaseModel):
    """Output from the REFLECT phase of the PAOR loop."""

    reflection: str = ""
    is_complete: bool = False
    final_answer: str = ""
    next_actions: list[ToolCall] = Field(default_factory=list)


class ReasoningStep(BaseModel):
    """A single step in the PAOR reasoning loop."""

    step_number: int
    phase: str  # "plan", "act", "observe", "reflect"
    thought: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    reflection: str = ""


class AgentResult(BaseModel):
    """Final result from the PAOR reasoning loop."""

    persona_used: str
    reasoning_steps: list[ReasoningStep] = Field(default_factory=list)
    final_answer: str = ""
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    total_steps: int = 0
    success: bool = True
    error: Optional[str] = None
