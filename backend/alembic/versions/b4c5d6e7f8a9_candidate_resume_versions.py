"""keep immutable candidate resume versions

Revision ID: b4c5d6e7f8a9
Revises: a3d4e5f6b7c8
"""

from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "a3d4e5f6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidateresumeversion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("job_offer_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resume_url", sa.String(length=1000), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("tech_stack", sa.Text(), nullable=True),
        sa.Column("years_of_experience", sa.Integer(), nullable=True),
        sa.Column("courses_and_diplomas", sa.Text(), nullable=True),
        sa.Column("career_summary", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source IN ('pri', 'application_link', 'sourcing', 'profile_update', 'legacy')",
            name="ck_candidateresumeversion_source",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidateprofile.id"]),
        sa.ForeignKeyConstraint(["job_offer_id"], ["joboffer.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_sha256", name="uq_candidateresumeversion_file_sha256"),
    )
    op.create_index(
        "ix_candidateresumeversion_candidate_id",
        "candidateresumeversion",
        ["candidate_id"],
    )
    op.create_index(
        "ix_candidateresumeversion_job_offer_id",
        "candidateresumeversion",
        ["job_offer_id"],
    )
    op.create_index(
        "ix_candidateresumeversion_uploaded_by_user_id",
        "candidateresumeversion",
        ["uploaded_by_user_id"],
    )
    op.create_index(
        "ix_candidateresumeversion_file_sha256",
        "candidateresumeversion",
        ["file_sha256"],
    )
    op.create_index(
        "ix_candidateresumeversion_uploaded_at",
        "candidateresumeversion",
        ["uploaded_at"],
    )

    op.execute(
        """
        INSERT INTO candidateresumeversion (
            candidate_id,
            resume_url,
            original_filename,
            source,
            extracted_text,
            tech_stack,
            years_of_experience,
            courses_and_diplomas,
            career_summary,
            uploaded_at
        )
        SELECT
            candidate.id,
            left(candidate.resume_url, 1000),
            left(
                COALESCE(
                    NULLIF(regexp_replace(candidate.resume_url, '^.*/', ''), ''),
                    'cv-historico'
                ),
                255
            ),
            'legacy',
            candidate.extracted_text,
            candidate.tech_stack,
            candidate.years_of_experience,
            candidate.courses_and_diplomas,
            candidate.career_summary,
            candidate.created_at
        FROM candidateprofile AS candidate
        WHERE candidate.resume_url IS NOT NULL
          AND candidate.resume_url NOT IN ('pending', 'linkedin_import')
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_resume_version_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'candidateresumeversion is append-only and cannot be updated';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_candidateresumeversion_no_update
        BEFORE UPDATE ON candidateresumeversion
        FOR EACH ROW EXECUTE FUNCTION prevent_resume_version_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_candidateresumeversion_no_update ON candidateresumeversion")
    op.execute("DROP FUNCTION IF EXISTS prevent_resume_version_update()")
    op.drop_index("ix_candidateresumeversion_uploaded_at", table_name="candidateresumeversion")
    op.drop_index("ix_candidateresumeversion_file_sha256", table_name="candidateresumeversion")
    op.drop_index("ix_candidateresumeversion_uploaded_by_user_id", table_name="candidateresumeversion")
    op.drop_index("ix_candidateresumeversion_job_offer_id", table_name="candidateresumeversion")
    op.drop_index("ix_candidateresumeversion_candidate_id", table_name="candidateresumeversion")
    op.drop_table("candidateresumeversion")
