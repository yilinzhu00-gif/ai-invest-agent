"""Add workspace identity/ACL tables and row-level isolation policies."""

from alembic import op
import sqlalchemy as sa

revision = "20260806_p3_01"
down_revision = "20260806_p2_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("is_human", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership"),
    )
    op.create_table(
        "object_acls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("permission", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_object_acls_lookup", "object_acls", ["workspace_id", "object_type", "object_id", "principal_id"])
    for table in ("agent_runs", "documents", "object_acls"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace_isolation ON {table} USING "
            "(workspace_id = current_setting('app.current_workspace_id', true)) "
            "WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true))"
        )


def downgrade() -> None:
    raise RuntimeError("P3 identity/RLS migration is expand-only and must not be downgraded automatically")
