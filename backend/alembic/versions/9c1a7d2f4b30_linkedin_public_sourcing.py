"""linkedin public sourcing metadata

Revision ID: 9c1a7d2f4b30
Revises: 3d968145ad71
"""
from alembic import op

revision = "9c1a7d2f4b30"
down_revision = "3d968145ad71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # El inicializador histórico también añadía estas columnas fuera de Alembic.
    # IF NOT EXISTS permite adoptar ese esquema sin borrar ni reescribir datos.
    op.execute("ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS professional_headline TEXT")
    op.execute("ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS source VARCHAR(30)")
    op.execute("ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS source_url VARCHAR(500)")
    op.execute(
        "ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS "
        "contact_status VARCHAR(30) NOT NULL DEFAULT 'not_contacted'"
    )
    op.execute("ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255)")
    op.execute("ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS invited_job_offer_id INTEGER")
    op.execute("ALTER TABLE candidateprofile ADD COLUMN IF NOT EXISTS invitation_expires_at TIMESTAMP")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'candidateprofile'::regclass
                  AND contype = 'f'
                  AND pg_get_constraintdef(oid) LIKE 'FOREIGN KEY (invited_job_offer_id)%'
            ) THEN
                ALTER TABLE candidateprofile
                ADD CONSTRAINT fk_candidate_invited_offer
                FOREIGN KEY (invited_job_offer_id) REFERENCES joboffer(id);
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_candidateprofile_source_url "
        "ON candidateprofile (source_url) WHERE source_url IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_candidateprofile_source_url")
    op.execute("ALTER TABLE candidateprofile DROP CONSTRAINT IF EXISTS fk_candidate_invited_offer")
    for column in ("invitation_expires_at", "invited_job_offer_id", "contact_email", "contact_status", "source_url", "source", "professional_headline"):
        op.drop_column("candidateprofile", column)
