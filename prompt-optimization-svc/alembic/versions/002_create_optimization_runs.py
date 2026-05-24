"""Create optimization_runs table

Revision ID: 002
Revises: 001
Create Date: 2026-05-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "prompt_optimization"


def upgrade() -> None:
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("agent_code", sa.String(50), nullable=False),
        sa.Column("group_name", sa.String(100), nullable=True),
        sa.Column("state", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("mlflow_run_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deferred_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    op.create_index(
        "idx_run_state", "optimization_runs", ["state"], schema=SCHEMA
    )
    op.create_index(
        "idx_run_agent",
        "optimization_runs",
        ["agent_code", "state"],
        schema=SCHEMA,
    )
    op.create_index(
        "idx_run_group",
        "optimization_runs",
        ["group_name", "state"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("idx_run_group", table_name="optimization_runs", schema=SCHEMA)
    op.drop_index("idx_run_agent", table_name="optimization_runs", schema=SCHEMA)
    op.drop_index("idx_run_state", table_name="optimization_runs", schema=SCHEMA)
    op.drop_table("optimization_runs", schema=SCHEMA)
