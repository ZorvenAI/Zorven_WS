"""Optimization run model for tracking run lifecycle states."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import text

from app.models.base import Base

SCHEMA = "prompt_optimization"


class OptimizationRun(Base):
    """Tracks the lifecycle state of a GEPA optimization run."""

    __tablename__ = "optimization_runs"
    __table_args__ = (
        Index("idx_run_state", "state"),
        Index("idx_run_agent", "agent_code", "state"),
        Index("idx_run_group", "group_name", "state"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    prompt_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    agent_code: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    group_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="QUEUED"
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    deferred_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
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
            f"<OptimizationRun(id={self.id[:8]}, prompt={self.prompt_name}, "
            f"state={self.state})>"
        )
