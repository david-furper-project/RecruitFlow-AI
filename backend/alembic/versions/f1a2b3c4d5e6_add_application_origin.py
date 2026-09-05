"""separate application origin from candidate profile source

Revision ID: f1a2b3c4d5e6
Revises: e8c2a4f1c990
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e8c2a4f1c990"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application",
        sa.Column(
            "origin",
            sa.String(length=30),
            nullable=False,
            server_default="application_link",
        ),
    )
    op.execute(
        """
        UPDATE application AS app
        SET origin = CASE
            WHEN EXISTS (
                SELECT 1
                FROM sourcingprospect AS prospect
                WHERE prospect.candidate_profile_id = app.candidate_id
                  AND prospect.job_offer_id = app.job_offer_id
            ) THEN 'sourcing'
            WHEN app.consent_given_at IS NULL THEN 'application_link'
            ELSE 'pri'
        END
        """
    )
    op.create_check_constraint(
        "ck_application_origin",
        "application",
        "origin IN ('pri', 'application_link', 'sourcing')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_application_origin", "application", type_="check")
    op.drop_column("application", "origin")
