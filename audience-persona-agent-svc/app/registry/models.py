"""Pydantic models for the Persona Registry."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class PersonaRegistryEntry(BaseModel):
    """A single persona entry in the registry."""

    slug: str = Field(..., description="URL-safe identifier")
    segment_label: str = Field(..., description="Descriptive persona label")
    data_source: str = Field(
        default="research_based",
        description="crm_grounded or research_based",
    )
    demographics: dict[str, Any] = Field(default_factory=dict)
    psychographics: dict[str, Any] = Field(default_factory=dict)
    pain_points: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    preferred_channels: list[str] = Field(default_factory=list)
    priority_score: float = Field(default=0.0)
    confidence_score: float = Field(default=0.0)
    narrative: str = Field(default="")
    version: int = Field(default=1)
    last_updated: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PersonaEvolution(BaseModel):
    """Tracks changes between persona versions."""

    slug: str = Field(..., description="Persona slug")
    old_version: int = Field(default=0)
    new_version: int = Field(default=0)
    changes: dict[str, Any] = Field(
        default_factory=dict,
        description="Changed fields with old/new values",
    )
    detected_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
