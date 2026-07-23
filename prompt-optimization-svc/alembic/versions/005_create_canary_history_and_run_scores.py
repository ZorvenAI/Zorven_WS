"""Create canary_history table and add score columns to optimization_runs

Revision ID: 005
Revises: 004
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "prompt_optimization"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # Create canary_history table for persistent canary deployment records
    op.create_table(
        "canary_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("canary_version", sa.Integer(), nullable=False),
        sa.Column("production_version", sa.Integer(), nullable=False),
        sa.Column("agent_code", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("final_regression_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_canary_prompt", "canary_history", ["prompt_name"], schema=SCHEMA
    )
    op.create_index(
        "idx_canary_outcome", "canary_history", ["outcome"], schema=SCHEMA
    )
    op.create_index(
        "idx_canary_ended", "canary_history", ["ended_at"], schema=SCHEMA
    )

    # Add score/cost columns to optimization_runs
    op.add_column(
        "optimization_runs",
        sa.Column("score_before", sa.Float(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "optimization_runs",
        sa.Column("score_after", sa.Float(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "optimization_runs",
        sa.Column("improvement", sa.Float(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "optimization_runs",
        sa.Column("cost_usd", sa.Float(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("optimization_runs", "cost_usd", schema=SCHEMA)
    op.drop_column("optimization_runs", "improvement", schema=SCHEMA)
    op.drop_column("optimization_runs", "score_after", schema=SCHEMA)
    op.drop_column("optimization_runs", "score_before", schema=SCHEMA)

    op.drop_index("idx_canary_ended", table_name="canary_history", schema=SCHEMA)
    op.drop_index("idx_canary_outcome", table_name="canary_history", schema=SCHEMA)
    op.drop_index("idx_canary_prompt", table_name="canary_history", schema=SCHEMA)
    op.drop_table("canary_history", schema=SCHEMA)
