"""Add pgvector-backed, ACL-filterable knowledge chunks."""

import sqlalchemy as sa
from alembic import op

revision = "20260806_p2_06"
down_revision = "20260806_p2_05"
branch_labels = None
depends_on = None


class Vector1536(sa.types.UserDefinedType):
    def get_col_spec(self, **_kw: object) -> str:
        return "vector(1536)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("principal_acl", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=True),
        sa.Column("table_block_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector1536(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_chunks_workspace_status", "knowledge_chunks", ["workspace_id", "status"])
    op.execute("CREATE INDEX ix_knowledge_chunks_text ON knowledge_chunks USING gin (to_tsvector('simple', text))")
    op.execute("CREATE INDEX ix_knowledge_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_text", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_workspace_status", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
