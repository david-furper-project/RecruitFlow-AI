"""separate sourcing prospects from applications

Revision ID: c7e2a4f1b890
Revises: 9c1a7d2f4b30
"""

from alembic import op
import sqlalchemy as sa


revision = "c7e2a4f1b890"
down_revision = "9c1a7d2f4b30"
branch_labels = None
depends_on = None


SOURCES = "'linkedin', 'computrabajo', 'laborum', 'referido', 'otro'"
STATUSES = (
    "'identificado', 'contactado', 'interesado', 'invitado', "
    "'no_interesado', 'sin_respuesta', 'convertido'"
)


def upgrade() -> None:
    op.create_table(
        "sourcingprospect",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_profile_id", sa.Integer(), nullable=False),
        sa.Column("job_offer_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="identificado", nullable=False),
        sa.Column("semantic_similarity", sa.Float(), nullable=True),
        sa.Column("match_explanation", sa.Text(), nullable=True),
        sa.Column("contact_channel", sa.String(length=30), nullable=True),
        sa.Column("contact_notes", sa.Text(), nullable=True),
        sa.Column("invitation_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invitation_expires_at", sa.DateTime(), nullable=True),
        sa.Column("authorization_channel", sa.String(length=50), nullable=True),
        sa.Column("authorization_at", sa.DateTime(), nullable=True),
        sa.Column("authorization_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("contacted_at", sa.DateTime(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("invited_at", sa.DateTime(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(f"source IN ({SOURCES})", name="ck_sourcingprospect_source"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_sourcingprospect_status"),
        sa.CheckConstraint(
            "semantic_similarity IS NULL OR (semantic_similarity >= 0 AND semantic_similarity <= 100)",
            name="ck_sourcingprospect_similarity",
        ),
        sa.ForeignKeyConstraint(["candidate_profile_id"], ["candidateprofile.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["job_offer_id"], ["joboffer.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_profile_id",
            "job_offer_id",
            name="uq_sourcingprospect_candidate_job",
        ),
    )
    op.create_index("ix_sourcingprospect_candidate_profile_id", "sourcingprospect", ["candidate_profile_id"])
    op.create_index("ix_sourcingprospect_created_by_user_id", "sourcingprospect", ["created_by_user_id"])
    op.create_index("ix_sourcingprospect_invitation_token_hash", "sourcingprospect", ["invitation_token_hash"])
    op.create_index("ix_sourcingprospect_job_offer_id", "sourcingprospect", ["job_offer_id"])
    op.create_index("ix_sourcingprospect_status", "sourcingprospect", ["status"])

    # Conserva las invitaciones creadas por la versión anterior cuando existe
    # una vacante asociada. Los perfiles aún no asignados siguen intactos en
    # CandidateProfile y podrán vincularse manualmente sin pérdida de datos.
    op.execute(
        sa.text(
            """
            INSERT INTO sourcingprospect (
                candidate_profile_id, job_offer_id, created_by_user_id,
                source, source_url, status, contact_channel, contact_notes,
                invitation_expires_at, invited_at, converted_at,
                created_at, updated_at
            )
            SELECT
                cp.id,
                cp.invited_job_offer_id,
                COALESCE((SELECT MIN(u.id) FROM "user" u WHERE u.role IN ('recruiter', 'admin')), cp.user_id),
                CASE WHEN cp.source IN ('linkedin', 'computrabajo', 'laborum', 'referido', 'otro')
                     THEN cp.source ELSE 'otro' END,
                cp.source_url,
                CASE
                    WHEN cp.contact_status = 'applied' THEN 'convertido'
                    WHEN cp.contact_status = 'invited' THEN 'invitado'
                    WHEN cp.contact_status = 'contacted' THEN 'contactado'
                    ELSE 'identificado'
                END,
                CASE WHEN cp.contact_email IS NOT NULL THEN 'correo' ELSE NULL END,
                CASE WHEN cp.contact_email IS NOT NULL THEN 'Contacto histórico: ' || cp.contact_email ELSE NULL END,
                cp.invitation_expires_at,
                CASE WHEN cp.contact_status IN ('invited', 'applied') THEN CURRENT_TIMESTAMP ELSE NULL END,
                CASE WHEN cp.contact_status = 'applied' THEN CURRENT_TIMESTAMP ELSE NULL END,
                cp.created_at,
                CURRENT_TIMESTAMP
            FROM candidateprofile cp
            WHERE cp.invited_job_offer_id IS NOT NULL
            ON CONFLICT (candidate_profile_id, job_offer_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_sourcingprospect_status", table_name="sourcingprospect")
    op.drop_index("ix_sourcingprospect_job_offer_id", table_name="sourcingprospect")
    op.drop_index("ix_sourcingprospect_invitation_token_hash", table_name="sourcingprospect")
    op.drop_index("ix_sourcingprospect_created_by_user_id", table_name="sourcingprospect")
    op.drop_index("ix_sourcingprospect_candidate_profile_id", table_name="sourcingprospect")
    op.drop_table("sourcingprospect")
