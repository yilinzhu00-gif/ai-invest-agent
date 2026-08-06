"""Create versioned document blocks and lossless table storage."""

import sqlalchemy as sa
from alembic import op

revision = "20260806_p2_05"
down_revision = "20260806_p2_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_source_sha256", "documents", ["source_sha256"])
    op.create_table(
        "document_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("parser", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_blocks_document_id", "document_blocks", ["document_id"])
    op.create_table(
        "table_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_block_id", sa.Integer(), nullable=False),
        sa.Column("cells", sa.JSON(), nullable=False),
        sa.Column("header_rows", sa.JSON(), nullable=False),
        sa.Column("units", sa.JSON(), nullable=False),
        sa.Column("source_pages", sa.JSON(), nullable=False),
        sa.Column("merge_confidence", sa.Float(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retrieval_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_block_id"], ["document_blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_table_blocks_document_block_id", "table_blocks", ["document_block_id"])


def downgrade() -> None:
    op.drop_index("ix_table_blocks_document_block_id", table_name="table_blocks")
    op.drop_table("table_blocks")
    op.drop_index("ix_document_blocks_document_id", table_name="document_blocks")
    op.drop_table("document_blocks")
    op.drop_index("ix_documents_source_sha256", table_name="documents")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_table("documents")
