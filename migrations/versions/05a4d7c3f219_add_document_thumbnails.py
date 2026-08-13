"""Add document thumbnails

Revision ID: 05a4d7c3f219
Revises: 8c0b745ae613
Create Date: 2026-08-12 15:30:00

"""

from alembic import op
import sqlalchemy as sa


revision = "05a4d7c3f219"
down_revision = "8c0b745ae613"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("content_version", sa.Integer(), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("thumbnail_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("thumbnail_object_key", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("thumbnail_status", sa.String(length=16), server_default="pending", nullable=False))

    op.create_table(
        "thumbnail_jobs",
        sa.Column("document_id", sa.String(length=32), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "content_version"),
    )
    op.create_index("ix_thumbnail_jobs_status", "thumbnail_jobs", ["status"])
    op.create_index("ix_thumbnail_jobs_available_at", "thumbnail_jobs", ["available_at"])
    op.create_index("ix_thumbnail_jobs_lease_expires_at", "thumbnail_jobs", ["lease_expires_at"])
    op.execute(
        sa.text(
            "INSERT INTO thumbnail_jobs (document_id, content_version, status, attempts, available_at, created_at, updated_at) "
            "SELECT id, content_version, 'pending', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM documents"
        )
    )


def downgrade():
    op.drop_index("ix_thumbnail_jobs_lease_expires_at", table_name="thumbnail_jobs")
    op.drop_index("ix_thumbnail_jobs_available_at", table_name="thumbnail_jobs")
    op.drop_index("ix_thumbnail_jobs_status", table_name="thumbnail_jobs")
    op.drop_table("thumbnail_jobs")
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("thumbnail_status")
        batch_op.drop_column("thumbnail_object_key")
        batch_op.drop_column("thumbnail_version")
        batch_op.drop_column("content_version")
