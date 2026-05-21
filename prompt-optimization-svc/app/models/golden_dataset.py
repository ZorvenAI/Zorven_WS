"""Golden dataset model for GEPA optimization evaluation."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SCHEMA = "prompt_optimization"


class GoldenDataset(Base):
    """A curated input/output example used to evaluate prompt quality.

    Golden datasets drive GEPA optimization by providing ground-truth
    examples across industries, brand maturities, and objectives.
    Each row maps a prompt name + context to an expected output.
    """

    __tablename__ = "golden_datasets"
    __table_args__ = (
        Index("idx_golden_prompt", "prompt_name", "active"),
        Index("idx_golden_tenant", "tenant_id", "agent_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    prompt_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Prompt identifier, e.g. zorven-wf1-mra-landscape"
    )
    agent_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Agent code, e.g. MRA, CGA, BPA"
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="NULL = global dataset"
    )
    input_context: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Context dict with {context.*} placeholders"
    )
    expected_output: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Golden example output"
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="manual | synthetic | mined | adversarial",
    )
    quality_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Scorer aggregate when source=mined"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), comment="Soft-delete flag"
    )
    metadata_extra: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True, comment="Industry, maturity, objective, etc."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<GoldenDataset(id={self.id}, prompt={self.prompt_name}, "
            f"agent={self.agent_code}, source={self.source})>"
        )
