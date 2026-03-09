"""Pydantic models for persona definitions."""

from pydantic import BaseModel, Field


class PersonaDefinition(BaseModel):
    """A business persona loaded from YAML config."""

    name: str
    display_name: str
    description: str
    domains: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    triggers: list[str] = Field(default_factory=list)
    priority: int = 5
