"""Add run links, style and feedback fields to structured memory."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_p6_01"
down_revision: str | None = "20260821_p5_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_memories", sa.Column("investment_style", sa.String(length=128), nullable=True))
    op.add_column("research_memories", sa.Column("source_run_id", sa.Uuid(), nullable=True))
    op.add_column("research_memories", sa.Column("research_type", sa.String(length=32), nullable=True))
    op.add_column("research_memories", sa.Column("user_feedback", sa.Text(), nullable=True))
    op.create_index("ix_research_memories_source_run_id", "research_memories", ["source_run_id"])


def downgrade() -> None:
    raise RuntimeError("Structured memory context is expand-only and must not be downgraded automatically")
