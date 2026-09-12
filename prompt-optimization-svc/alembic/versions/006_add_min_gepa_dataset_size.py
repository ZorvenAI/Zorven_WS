"""Add min_gepa_dataset_size to tenant_configs

Revision ID: 006
Revises: 005
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "prompt_optimization"


def upgrade() -> None:
    op.add_column(
        "tenant_configs",
        sa.Column(
            "min_gepa_dataset_size",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("50"),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("tenant_configs", "min_gepa_dataset_size", schema=SCHEMA)
