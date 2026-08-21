"""Persist professional Research Task configuration on Agent Runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_p5_01"
down_revision: str | None = "20260821_p3_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("target", sa.String(length=32), nullable=True))
    op.add_column("agent_runs", sa.Column("research_type", sa.String(length=32), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("depth", sa.String(length=24), nullable=False, server_default="standard"),
    )
    op.add_column(
        "agent_runs",
        sa.Column("time_range", sa.String(length=64), nullable=False, server_default="recent_1y"),
    )
    op.add_column(
        "agent_runs",
        sa.Column("output_format", sa.String(length=16), nullable=False, server_default="markdown"),
    )
    op.create_index("ix_agent_runs_target", "agent_runs", ["target"])
    for column in ("depth", "time_range", "output_format"):
        op.alter_column("agent_runs", column, server_default=None)


def downgrade() -> None:
    raise RuntimeError("Research Task configuration is expand-only and must not be downgraded automatically")
