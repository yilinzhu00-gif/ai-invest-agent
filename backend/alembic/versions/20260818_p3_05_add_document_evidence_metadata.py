"""Add document metadata needed by the researcher-facing evidence library."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_p3_05"
down_revision: str | None = "20260818_p3_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("symbol", sa.String(length=6), nullable=True))
    op.add_column(
        "documents",
        sa.Column("document_type", sa.String(length=32), nullable=False, server_default="other"),
    )
    op.add_column("documents", sa.Column("source_url", sa.String(length=2048), nullable=True))
    op.add_column(
        "documents", sa.Column("status", sa.String(length=32), nullable=False, server_default="ready")
    )
    op.add_column(
        "documents", sa.Column("page_count", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    raise RuntimeError("Document evidence metadata is expand-only and must not be downgraded automatically")
