"""Pydantic models for runtime agent skills."""

from pydantic import BaseModel, Field


class SkillMeta(BaseModel):
    """Metadata parsed from YAML frontmatter of a skill file."""

    name: str
    version: str = "1.0"
    description: str = ""
    target_agents: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    priority: int = 0
    max_tokens: int = 500


class LoadedSkill(BaseModel):
    """A fully loaded skill with metadata and body content."""

    meta: SkillMeta
    body: str
    file_path: str
