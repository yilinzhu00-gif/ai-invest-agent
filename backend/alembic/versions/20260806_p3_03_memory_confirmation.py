"""Add human-confirmed Agent memory and review-gate statuses.

Revision ID: 20260806_p3_03
Revises: 20260806_p3_02
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_p3_03"
down_revision: str | None = "20260806_p3_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["source_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_memories_workspace_id", "agent_memories", ["workspace_id"])
    op.create_index("ix_agent_memories_principal_id", "agent_memories", ["principal_id"])
    op.create_index("ix_agent_memories_source_run_id", "agent_memories", ["source_run_id"])
    op.execute("ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_memories FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_memories_workspace_isolation ON agent_memories USING "
        "(workspace_id = current_setting('app.current_workspace_id', true)) "
        "WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true))"
    )


def downgrade() -> None:
    raise RuntimeError("Agent memory migration is expand-only and must not be downgraded automatically")
