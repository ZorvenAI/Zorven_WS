"""Tenant configuration model for per-tenant optimization settings (US-047).

Stores tenant schedule preferences in PostgreSQL as source-of-truth.
Redis remains the hot path; PostgreSQL is the fallback and audit record.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SCHEMA = "prompt_optimization"


class TenantConfig(Base):
    """Per-tenant optimization configuration persisted to PostgreSQL."""

    __tablename__ = "tenant_configs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    wf3_optimization_schedule: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'monthly'")
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
            f"<TenantConfig(tenant_id={self.tenant_id}, "
            f"schedule={self.wf3_optimization_schedule})>"
        )
