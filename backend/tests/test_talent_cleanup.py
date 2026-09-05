from datetime import datetime

from sqlmodel import Session, select

from app.api.recruiter import get_talent_bank
from app.db.session import engine
from app.models import (
    Application,
    CandidateProfile,
    CandidateResumeVersion,
    Company,
    Decision,
    Evaluation,
    JobOffer,
    Notification,
    PrivacyRequestLog,
    SourcingProspect,
    User,
)
from app.services.scoring_service import get_application_ranking
from app.services.talent_cleanup_service import archive_operational_talent_data


def test_talent_cleanup_anonymizes_and_hides_but_preserves_audit():
    with Session(engine) as session:
        recruiter = User(
            email="recruiter-cleanup@example.com",
            role="recruiter",
            password_hash="hash",
        )
        candidate_user = User(
            email="juan.perez@example.com",
            role="candidate",
            password_hash="hash",
        )
        company = Company(name="Empresa de prueba")
        session.add(recruiter)
        session.add(candidate_user)
        session.add(company)
        session.flush()

        offer = JobOffer(
            company_id=company.id,
            title="Backend Engineer",
            description="Desarrollo de servicios",
            requirements="Python",
            tech_stack="Python, PostgreSQL",
            salary_range="Confidencial",
            experience_years=3,
            seniority="Semi Senior",
        )
        candidate = CandidateProfile(
            user_id=candidate_user.id,
            full_name="Juan Pérez",
            resume_url="http://localhost:8000/uploads/cvs/1/cv.pdf",
            extracted_text="CV privado",
            phone="+56911111111",
            rut="111111111",
            tech_stack="Python",
            contact_email="juan.perez@example.com",
            source="linkedin",
            source_url="https://www.linkedin.com/in/juan-perez",
        )
        session.add(offer)
        session.add(candidate)
        session.flush()

        application = Application(
            candidate_id=candidate.id,
            job_offer_id=offer.id,
            status="pending",
            origin="sourcing",
        )
        session.add(application)
        session.flush()
        session.add(
            Evaluation(
                application_id=application.id,
                suggested_category="apto",
                explanation="Coincidencia profesional",
                model_version="test-model",
                prompt_version="test-prompt",
                excluded_fields="nacionalidad",
            )
        )
        session.add(
            Decision(
                application_id=application.id,
                user_id=recruiter.id,
                action="avanzar",
            )
        )
        session.add(
            Notification(
                application_id=application.id,
                type="avance",
                send_status="enviado",
            )
        )
        session.add(
            CandidateResumeVersion(
                candidate_id=candidate.id,
                job_offer_id=offer.id,
                uploaded_by_user_id=recruiter.id,
                resume_url=candidate.resume_url,
                original_filename="cv.pdf",
                file_sha256="a" * 64,
                source="sourcing",
            )
        )
        session.add(
            SourcingProspect(
                candidate_profile_id=candidate.id,
                job_offer_id=offer.id,
                created_by_user_id=recruiter.id,
                source="linkedin",
                source_url=candidate.source_url,
            )
        )
        session.commit()

        result = archive_operational_talent_data(
            session,
            requested_by_user_id=recruiter.id,
            archived_at=datetime(2026, 9, 2, 12, 0, 0),
        )

        assert result.archived_candidates == 1
        assert result.archived_applications == 1
        assert result.deleted_sourcing_prospects == 1
        assert result.deleted_resume_versions == 1
        assert result.privacy_logs_created == 1
        assert result.resume_urls == ("http://localhost:8000/uploads/cvs/1/cv.pdf",)

        session.refresh(candidate)
        session.refresh(candidate_user)
        session.refresh(application)
        assert candidate.archived_at == datetime(2026, 9, 2, 12, 0, 0)
        assert candidate.full_name == f"Perfil archivado {candidate.id}"
        assert candidate.resume_url is None
        assert candidate.extracted_text is None
        assert candidate.contact_email is None
        assert candidate.embedding is None
        assert candidate_user.is_active is False
        assert candidate_user.email.endswith("@candidate.internal.invalid")
        assert application.archived_at == datetime(2026, 9, 2, 12, 0, 0)

        assert len(session.exec(select(Evaluation)).all()) == 1
        assert len(session.exec(select(Decision)).all()) == 1
        assert len(session.exec(select(Notification)).all()) == 1
        assert len(session.exec(select(PrivacyRequestLog)).all()) == 1
        assert session.exec(select(SourcingProspect)).all() == []
        assert session.exec(select(CandidateResumeVersion)).all() == []

        talent_bank = get_talent_bank(session=session, _=recruiter)
        assert talent_bank == {"candidates": [], "total": 0}
        ranking = get_application_ranking(session, offer.id)
        assert ranking["candidates"] == []
        assert ranking["counts"] == {"all_active": 0, "discarded": 0, "hired": 0}
