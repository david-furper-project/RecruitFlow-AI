"""add public offer id and application consent audit

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

from alembic import op
import sqlalchemy as sa


revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("joboffer", sa.Column("public_id", sa.String(length=36), nullable=True))
    op.execute("UPDATE joboffer SET public_id = gen_random_uuid()::text WHERE public_id IS NULL")
    op.alter_column("joboffer", "public_id", nullable=False)
    op.create_index("ix_joboffer_public_id", "joboffer", ["public_id"], unique=True)

    op.add_column(
        "application",
        sa.Column("consent_text_version", sa.String(length=50), nullable=True),
    )
    op.add_column("application", sa.Column("consent_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("application", "consent_text")
    op.drop_column("application", "consent_text_version")
    op.drop_index("ix_joboffer_public_id", table_name="joboffer")
    op.drop_column("joboffer", "public_id")
