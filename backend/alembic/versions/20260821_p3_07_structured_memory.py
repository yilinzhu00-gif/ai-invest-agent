"""Add structured user and research memory tables.

The existing ``agent_memories`` table remains the human-confirmed run-summary
store.  These tables hold explicit user profile and historical report data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_p3_07"
down_revision: str | None = "20260821_p4_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_workspace_rls(table: str, policy: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {policy} ON {table} USING "
        "(workspace_id = current_setting('app.current_workspace_id', true)) "
        "WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true))"
    )


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("investment_preferences", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("industries", sa.JSON(), nullable=False),
        sa.Column("historical_stocks", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_user_memories_workspace_user"),
    )
    op.create_index("ix_user_memories_workspace_id", "user_memories", ["workspace_id"])
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])
    _add_workspace_rls("user_memories", "user_memories_workspace_isolation")

    op.create_table(
        "research_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("report_title", sa.String(length=512), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("symbol", sa.String(length=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_research_memories_confidence"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_memories_workspace_id", "research_memories", ["workspace_id"])
    op.create_index("ix_research_memories_user_id", "research_memories", ["user_id"])
    op.create_index("ix_research_memories_symbol", "research_memories", ["symbol"])
    op.create_index(
        "ix_research_memories_workspace_date",
        "research_memories",
        ["workspace_id", "report_date"],
    )
    _add_workspace_rls("research_memories", "research_memories_workspace_isolation")


def downgrade() -> None:
    raise RuntimeError("Structured memory migration is expand-only and must not be downgraded automatically")
