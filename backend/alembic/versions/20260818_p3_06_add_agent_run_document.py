"""Pin the selected evidence document to each durable research run."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_p3_06"
down_revision: str | None = "20260818_p3_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agent_runs_document_id", "agent_runs", "documents", ["document_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_agent_runs_document_id", "agent_runs", ["document_id"])


def downgrade() -> None:
    raise RuntimeError("Agent Run evidence linkage is expand-only and must not be downgraded automatically")
