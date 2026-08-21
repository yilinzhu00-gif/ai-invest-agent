"""Persist the explicit workflow selected for an Agent Run.

Revision ID: 20260821_p4_01
Revises: 20260818_p3_06
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_p4_01"
down_revision: str | None = "20260818_p3_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("workflow", sa.String(length=32), nullable=False, server_default="research"),
    )
    op.alter_column("agent_runs", "workflow", server_default=None)


def downgrade() -> None:
    op.drop_column("agent_runs", "workflow")
