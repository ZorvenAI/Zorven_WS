"""Create tenant_configs table

Revision ID: 003
Revises: 002
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "prompt_optimization"


def upgrade() -> None:
    op.create_table(
        "tenant_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column(
            "wf3_optimization_schedule",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'monthly'"),
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
        sa.UniqueConstraint("tenant_id"),
        schema=SCHEMA,
    )

    op.create_index(
        "idx_tenant_config_tenant_id",
        "tenant_configs",
        ["tenant_id"],
        unique=True,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_tenant_config_tenant_id",
        table_name="tenant_configs",
        schema=SCHEMA,
    )
    op.drop_table("tenant_configs", schema=SCHEMA)
