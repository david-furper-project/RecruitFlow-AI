from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import text

from app.core.config import settings
import app.models  # Import models to ensure they are registered with SQLModel

engine = create_engine(settings.DATABASE_URL, echo=True)


def _install_pgvector_and_constraints() -> None:
    with Session(engine) as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

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
                    WHERE table_name = 'evaluation' AND column_name = 'interview_questions'
                ) THEN
                    ALTER TABLE evaluation ADD COLUMN interview_questions TEXT;
                END IF;
            END $$;
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

        session.commit()


def _create_default_admin() -> None:
    """Crear usuario admin por defecto si no existe."""
    from app.models import User
    from app.core.auth import hash_password
    
    with Session(engine) as session:
        # Verificar si el admin ya existe
        statement = select(User).where(User.email == "admin@pri.local")
        existing_admin = session.exec(statement).first()
        
        if not existing_admin:
            # Crear admin
            admin_user = User(
                email="admin@pri.local",
                password_hash=hash_password("admin"),
                role="recruiter"
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
