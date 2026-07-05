"""Schema snapshot model for tracking output_schema at optimization time (US-056)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SCHEMA = "prompt_optimization"


class SchemaSnapshot(Base):
    """Stores skill output_schema at time of PRODUCTION optimization.

    Used by SchemaChangeDetector to compare current schema against
    the last known-good state and detect FIELD_ADDED, LENGTH_CHANGED,
    and REQUIRED_CHANGED diffs.
    """

    __tablename__ = "schema_snapshots"
    __table_args__ = (
        Index("idx_snapshot_prompt", "prompt_name"),
        Index("idx_snapshot_agent", "agent_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Prompt identifier, e.g. zorven-wf1-mra-synthesis",
    )
    agent_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Agent code, e.g. mra, cga",
    )
    schema_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Serialized list[SkillOutputField] at snapshot time",
    )
    optimization_run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Associated optimization run ID",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<SchemaSnapshot(id={self.id}, prompt={self.prompt_name}, "
            f"agent={self.agent_code})>"
        )
