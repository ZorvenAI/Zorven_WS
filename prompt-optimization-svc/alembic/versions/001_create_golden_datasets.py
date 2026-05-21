"""Create golden_datasets table

Revision ID: 001
Revises: None
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "prompt_optimization"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "golden_datasets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("agent_code", sa.String(50), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=True),
        sa.Column(
            "input_context",
            sa.JSON(),
            nullable=False,
            comment="Context dict with {context.*} placeholders",
        ),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            comment="manual | synthetic | mined | adversarial",
        ),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Industry, maturity, objective, etc.",
        ),
        sa.Column(
            "created_at",
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
        "idx_golden_prompt",
        "golden_datasets",
        ["prompt_name", "active"],
        schema=SCHEMA,
    )
    op.create_index(
        "idx_golden_tenant",
        "golden_datasets",
        ["tenant_id", "agent_code"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_golden_tenant",
        table_name="golden_datasets",
        schema=SCHEMA,
    )
    op.drop_index(
        "idx_golden_prompt",
        table_name="golden_datasets",
        schema=SCHEMA,
    )
    op.drop_table("golden_datasets", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
