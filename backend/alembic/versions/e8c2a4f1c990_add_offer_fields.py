"""add country modality message to joboffer

Revision ID: e8c2a4f1c990
Revises: c7e2a4f1b890
"""
from alembic import op

revision = "e8c2a4f1c990"
down_revision = "c7e2a4f1b890"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE joboffer ADD COLUMN IF NOT EXISTS country VARCHAR(255)")
    op.execute("ALTER TABLE joboffer ADD COLUMN IF NOT EXISTS modality VARCHAR(255)")
    op.execute("ALTER TABLE joboffer ADD COLUMN IF NOT EXISTS message TEXT")

def downgrade() -> None:
    op.execute("ALTER TABLE joboffer DROP COLUMN IF EXISTS country")
    op.execute("ALTER TABLE joboffer DROP COLUMN IF EXISTS modality")
    op.execute("ALTER TABLE joboffer DROP COLUMN IF EXISTS message")
