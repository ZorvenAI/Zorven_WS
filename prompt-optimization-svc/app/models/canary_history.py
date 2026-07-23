"""Canary deployment history model for persistent storage."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import text

from app.models.base import Base

SCHEMA = "prompt_optimization"


class CanaryHistory(Base):
    """Persistent record of canary deployment outcomes."""

    __tablename__ = "canary_history"
    __table_args__ = (
        Index("idx_canary_prompt", "prompt_name"),
        Index("idx_canary_outcome", "outcome"),
        Index("idx_canary_ended", "ended_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    prompt_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    production_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_code: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    outcome: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    final_regression_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<CanaryHistory(prompt={self.prompt_name}, v{self.canary_version}, "
            f"outcome={self.outcome})>"
        )
