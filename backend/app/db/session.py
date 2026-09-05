from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import text

from app.core.config import settings
import app.models  # Import models to ensure they are registered with SQLModel

engine = create_engine(settings.DATABASE_URL, echo=True)


def _install_pgvector_and_constraints() -> None:
    with Session(engine) as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

        # ===== BLOQUE 6: Actualizar tabla user =====
        session.execute(text("""
            DO $$
            BEGIN
                -- Cambiar default de role a 'recruiter'
                ALTER TABLE "user" ALTER COLUMN role SET DEFAULT 'recruiter';
                
                -- Agregar columnas de control de acceso y sesión
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'user' AND column_name = 'is_active'
                ) THEN
                    ALTER TABLE "user" ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'user' AND column_name = 'last_login_at'
                ) THEN
                    ALTER TABLE "user" ADD COLUMN last_login_at TIMESTAMP;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'user' AND column_name = 'failed_attempts'
                ) THEN
                    ALTER TABLE "user" ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'user' AND column_name = 'locked_until'
                ) THEN
                    ALTER TABLE "user" ADD COLUMN locked_until TIMESTAMP;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'user' AND column_name = 'password_changed_at'
                ) THEN
                    ALTER TABLE "user" ADD COLUMN password_changed_at TIMESTAMP;
                END IF;
            END $$;
        """))

        # Crear índice case-insensitive en email
        session.execute(text("""
            DROP INDEX IF EXISTS idx_user_email;
            CREATE UNIQUE INDEX idx_user_email ON "user" (lower(email));
        """))

        # ===== Resto de migraciones =====
        session.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'candidateprofile' AND column_name = 'nationality'
                ) THEN
                    ALTER TABLE candidateprofile DROP COLUMN nationality;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'application' AND column_name = 'consent_given_at'
                ) THEN
                    ALTER TABLE application ADD COLUMN consent_given_at TIMESTAMPTZ;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'application' AND column_name = 'consent_text_version'
                ) THEN
                    ALTER TABLE application ADD COLUMN consent_text_version VARCHAR(50);
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'application' AND column_name = 'consent_text'
                ) THEN
                    ALTER TABLE application ADD COLUMN consent_text TEXT;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'joboffer' AND column_name = 'public_id'
                ) THEN
                    ALTER TABLE joboffer ADD COLUMN public_id VARCHAR(36);
                END IF;

                UPDATE joboffer SET public_id = gen_random_uuid()::text WHERE public_id IS NULL;
                ALTER TABLE joboffer ALTER COLUMN public_id SET NOT NULL;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'application' AND column_name = 'origin'
                ) THEN
                    ALTER TABLE application
                    ADD COLUMN origin VARCHAR(30) NOT NULL DEFAULT 'application_link';

                    UPDATE application AS app
                    SET origin = CASE
                        WHEN EXISTS (
                            SELECT 1 FROM sourcingprospect AS prospect
                            WHERE prospect.candidate_profile_id = app.candidate_id
                              AND prospect.job_offer_id = app.job_offer_id
                        ) THEN 'sourcing'
                        WHEN app.consent_given_at IS NULL THEN 'application_link'
                        ELSE 'pri'
                    END;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_application_origin'
                ) THEN
                    ALTER TABLE application
                    ADD CONSTRAINT ck_application_origin
                    CHECK (origin IN ('pri', 'application_link', 'sourcing'));
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'notification' AND column_name = 'created_at'
                ) THEN
                    ALTER TABLE notification ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'notification' AND column_name = 'retry_count'
                ) THEN
                    ALTER TABLE notification ADD COLUMN retry_count INTEGER DEFAULT 0;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'notification' AND column_name = 'message_id'
                ) THEN
                    ALTER TABLE notification ADD COLUMN message_id VARCHAR;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'decision' AND column_name = 'feedback'
                ) THEN
                    ALTER TABLE decision ADD COLUMN feedback TEXT;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'notification' AND column_name = 'decision_id'
                ) THEN
                    ALTER TABLE notification
                    ADD COLUMN decision_id INTEGER REFERENCES decision(id);
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'evaluation' AND column_name = 'interview_questions'
                ) THEN
                    ALTER TABLE evaluation ADD COLUMN interview_questions TEXT;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'candidateprofile' AND column_name = 'rut'
                ) THEN
                    ALTER TABLE candidateprofile ADD COLUMN rut VARCHAR(15);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='professional_headline') THEN
                    ALTER TABLE candidateprofile ADD COLUMN professional_headline TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='source') THEN
                    ALTER TABLE candidateprofile ADD COLUMN source VARCHAR(30);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='source_url') THEN
                    ALTER TABLE candidateprofile ADD COLUMN source_url VARCHAR(500);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='contact_status') THEN
                    ALTER TABLE candidateprofile ADD COLUMN contact_status VARCHAR(30) NOT NULL DEFAULT 'not_contacted';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='contact_email') THEN
                    ALTER TABLE candidateprofile ADD COLUMN contact_email VARCHAR(255);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='invited_job_offer_id') THEN
                    ALTER TABLE candidateprofile ADD COLUMN invited_job_offer_id INTEGER REFERENCES joboffer(id);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='invitation_expires_at') THEN
                    ALTER TABLE candidateprofile ADD COLUMN invitation_expires_at TIMESTAMP;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='candidateprofile' AND column_name='archived_at') THEN
                    ALTER TABLE candidateprofile ADD COLUMN archived_at TIMESTAMP;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='application' AND column_name='archived_at') THEN
                    ALTER TABLE application ADD COLUMN archived_at TIMESTAMP;
                END IF;

                UPDATE candidateprofile
                SET contact_email = lower(trim(contact_email))
                WHERE contact_email IS NOT NULL;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_candidateprofile_user_id'
                ) THEN
                    ALTER TABLE candidateprofile
                    ADD CONSTRAINT uq_candidateprofile_user_id UNIQUE (user_id);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_application_candidate_job'
                ) THEN
                    ALTER TABLE application
                    ADD CONSTRAINT uq_application_candidate_job UNIQUE (candidate_id, job_offer_id);
                END IF;
            END $$;
        """))

        session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_joboffer_public_id
            ON joboffer (public_id);
        """))

        session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_decision_id
            ON notification (decision_id)
            WHERE decision_id IS NOT NULL;
        """))

        session.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_append_only_update()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '% is append-only and cannot be updated', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
        """))

        session.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_append_only_delete()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '% is append-only and cannot be deleted', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
        """))

        session.execute(text("""
            DROP TRIGGER IF EXISTS trg_evaluation_no_update ON evaluation;
            CREATE TRIGGER trg_evaluation_no_update
            BEFORE UPDATE OR DELETE ON evaluation
            FOR EACH ROW EXECUTE FUNCTION prevent_append_only_update();
        """))

        session.execute(text("""
            DROP TRIGGER IF EXISTS trg_decision_no_update ON decision;
            CREATE TRIGGER trg_decision_no_update
            BEFORE UPDATE OR DELETE ON decision
            FOR EACH ROW EXECUTE FUNCTION prevent_append_only_delete();
        """))

        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_candidateprofile_embedding_hnsw
            ON candidateprofile USING hnsw (embedding vector_cosine_ops);
        """))

        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_joboffer_embedding_hnsw
            ON joboffer USING hnsw (embedding vector_cosine_ops);
        """))

        session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_candidateprofile_rut
            ON candidateprofile (rut)
            WHERE rut IS NOT NULL;
        """))

        session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_candidateprofile_source_url
            ON candidateprofile (source_url)
            WHERE source_url IS NOT NULL;
        """))

        session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_candidateprofile_archived_at
            ON candidateprofile (archived_at);
        """))

        session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_application_archived_at
            ON application (archived_at);
        """))

        # Existing candidates predate CV versioning. Preserve their current CV
        # once as a legacy snapshot; subsequent uploads only append versions.
        session.execute(text("""
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
              AND NOT EXISTS (
                  SELECT 1
                  FROM candidateresumeversion AS version
                  WHERE version.candidate_id = candidate.id
              );
        """))

        session.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_resume_version_update()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'candidateresumeversion is append-only and cannot be updated';
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_candidateresumeversion_no_update ON candidateresumeversion;
            CREATE TRIGGER trg_candidateresumeversion_no_update
            BEFORE UPDATE ON candidateresumeversion
            FOR EACH ROW EXECUTE FUNCTION prevent_resume_version_update();
        """))

        session.commit()


def _create_default_admin() -> None:
    """
    Crear usuario admin por defecto si no existe.
    Contraseña: Admin123456 (cumple política Bloque 6)
    """
    from app.models import User
    from app.core.auth import hash_password
    from datetime import datetime, timezone

    with Session(engine) as session:
        # Verificar si el admin ya existe (case-insensitive)
        statement = select(User).where(User.email == "admin@ejemplo.com")
        existing_admin = session.exec(statement).first()

        if not existing_admin:
            # Crear admin
            admin_user = User(
                email="admin@ejemplo.com",
                password_hash=hash_password("Admin123456"),
                role="recruiter",
                is_active=True,
                password_changed_at=datetime.now(timezone.utc),
            )
            session.add(admin_user)
            session.commit()


def init_db():
    with Session(engine) as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        session.commit()

    SQLModel.metadata.create_all(engine)
    _install_pgvector_and_constraints()
    _create_default_admin()


def get_session():
    with Session(engine) as session:
        yield session
