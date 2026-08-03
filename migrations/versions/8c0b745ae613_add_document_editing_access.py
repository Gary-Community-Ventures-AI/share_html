"""Add document editing access

Revision ID: 8c0b745ae613
Revises: 1bf0babf1614
Create Date: 2026-07-27 19:50:00

"""

from alembic import op
import sqlalchemy as sa


revision = "8c0b745ae613"
down_revision = "1bf0babf1614"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("document_access") as batch_op:
        batch_op.add_column(
            sa.Column("can_edit", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade():
    with op.batch_alter_table("document_access") as batch_op:
        batch_op.drop_column("can_edit")
