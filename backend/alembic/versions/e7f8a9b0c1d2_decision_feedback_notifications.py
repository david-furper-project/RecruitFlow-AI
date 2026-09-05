"""add candidate-facing feedback and decision-scoped notifications

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from alembic import op
import sqlalchemy as sa


revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decision", sa.Column("feedback", sa.Text(), nullable=True))
    op.add_column("notification", sa.Column("decision_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_notification_decision_id",
        "notification",
        "decision",
        ["decision_id"],
        ["id"],
    )
    op.create_index(
        "uq_notification_decision_id",
        "notification",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("decision_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_notification_decision_id", table_name="notification")
    op.drop_constraint("fk_notification_decision_id", "notification", type_="foreignkey")
    op.drop_column("notification", "decision_id")
    op.drop_column("decision", "feedback")
