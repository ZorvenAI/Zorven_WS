"""Create schema_snapshots table

Revision ID: 004
Revises: 003
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "prompt_optimization"


def upgrade() -> None:
    op.create_table(
        "schema_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("agent_code", sa.String(50), nullable=False),
        sa.Column(
            "schema_json",
            sa.dialects.postgresql.JSON(),
            nullable=False,
        ),
        sa.Column("optimization_run_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    op.create_index(
        "idx_snapshot_prompt",
        "schema_snapshots",
        ["prompt_name"],
        schema=SCHEMA,
    )
    op.create_index(
        "idx_snapshot_agent",
        "schema_snapshots",
        ["agent_code"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("idx_snapshot_agent", table_name="schema_snapshots", schema=SCHEMA)
    op.drop_index("idx_snapshot_prompt", table_name="schema_snapshots", schema=SCHEMA)
    op.drop_table("schema_snapshots", schema=SCHEMA)
