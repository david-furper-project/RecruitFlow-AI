"""enforce one candidate identity across vacancies

Revision ID: a3d4e5f6b7c8
Revises: f1a2b3c4d5e6
"""

from alembic import op


revision = "a3d4e5f6b7c8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('UPDATE "user" SET email = lower(trim(email))')
    op.execute(
        "UPDATE candidateprofile SET contact_email = lower(trim(contact_email)) "
        "WHERE contact_email IS NOT NULL"
    )
    op.create_unique_constraint(
        "uq_candidateprofile_user_id",
        "candidateprofile",
        ["user_id"],
    )
    op.create_unique_constraint(
        "uq_application_candidate_job",
        "application",
        ["candidate_id", "job_offer_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_application_candidate_job",
        "application",
        type_="unique",
    )
    op.drop_constraint(
        "uq_candidateprofile_user_id",
        "candidateprofile",
        type_="unique",
    )
