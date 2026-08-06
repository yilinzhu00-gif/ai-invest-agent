"""Persist Agent Run retry attempts for Celery worker recovery."""

import sqlalchemy as sa
from alembic import op

revision = "20260806_p3_02"
down_revision = "20260806_p3_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("agent_runs", "attempt_count", server_default=None)


def downgrade() -> None:
    raise RuntimeError("P3 worker lifecycle migration is expand-only and must not be downgraded automatically")
