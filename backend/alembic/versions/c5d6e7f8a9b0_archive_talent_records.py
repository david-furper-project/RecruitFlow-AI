"""archive talent records without deleting audit history

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

from alembic import op
import sqlalchemy as sa


revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidateprofile", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("application", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.create_index("ix_candidateprofile_archived_at", "candidateprofile", ["archived_at"])
    op.create_index("ix_application_archived_at", "application", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_application_archived_at", table_name="application")
    op.drop_index("ix_candidateprofile_archived_at", table_name="candidateprofile")
    op.drop_column("application", "archived_at")
    op.drop_column("candidateprofile", "archived_at")
