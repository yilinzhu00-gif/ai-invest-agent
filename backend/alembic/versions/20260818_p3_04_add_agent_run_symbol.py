"""Persist an optional A-share symbol with each research run.

Revision ID: 20260818_p3_04
Revises: 20260806_p3_03
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_p3_04"
down_revision: str | None = "20260806_p3_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("symbol", sa.String(length=6), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "symbol")
