import uuid

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.db.session import engine
from app.models import Application, CandidateProfile, Company, Decision, Evaluation, JobOffer, User
from app.services.audit_service import get_application_audit
from app.services.scoring_service import (
    SCORING_PROMPT_VERSION,
    ensure_final_status_has_decision,
    evaluate_application,
    register_decision,
)


@pytest.fixture
def seeded_application():
    with Session(engine) as session:
        candidate_user = User(email=f"candidate-{uuid.uuid4()}@example.com", role="candidate", password_hash="hash")
        recruiter = User(email=f"recruiter-{uuid.uuid4()}@example.com", role="recruiter", password_hash="hash")
        company = Company(name=f"Company-{uuid.uuid4()}", industry="Tech", description="AI company")
        session.add_all([candidate_user, recruiter, company])
        session.commit()
        session.refresh(candidate_user)
        session.refresh(recruiter)
        session.refresh(company)

        candidate = CandidateProfile(
            user_id=candidate_user.id,
            full_name="Ana Developer",
            tech_stack="Python, FastAPI, PostgreSQL",
            career_summary="Senior Python backend engineer with APIs and SQL.",
            embedding=[0.1] * 1536,
        )
        job_offer = JobOffer(
            company_id=company.id,
            title="Backend Engineer",
            description="Senior backend developer for Python APIs and PostgreSQL.",
            requirements="Python, FastAPI, PostgreSQL, refactoring., deployment.",
            tech_stack="Python, FastAPI, PostgreSQL",
            salary_range="120000-150000",
            experience_years=5,
            seniority="senior",
            embedding=[0.1] * 1536,
        )
        session.add_all([candidate, job_offer])
        session.commit()
        session.refresh(candidate)
        session.refresh(job_offer)

        application = Application(candidate_id=candidate.id, job_offer_id=job_offer.id, status="pending")
        session.add(application)
        session.commit()
        session.refresh(application)

        yield session, application, recruiter


def test_evaluate_application_creates_record_and_similarity_score(seeded_application):
    session, application, _ = seeded_application
    result = evaluate_application(session, application.id)
    assert result["similarity_score"] >= 0
    evaluation = session.query(Evaluation).filter(Evaluation.application_id == application.id).first()
    assert evaluation is not None
    assert evaluation.suggested_category in {"apto", "en_revision", "no_apto"}
    assert evaluation.prompt_version == SCORING_PROMPT_VERSION
    assert application.similarity_score is not None


def test_decision_requires_reason_on_conflict(seeded_application):
    session, application, recruiter = seeded_application
    evaluate_application(session, application.id)

    with pytest.raises(ValueError):
        register_decision(session, application.id, recruiter.id, "descartar", "")


def test_final_status_requires_decision(seeded_application):
    session, application, _ = seeded_application
    application.status = "accepted"
    with pytest.raises(ValueError):
        ensure_final_status_has_decision(session, application.id)


def test_audit_returns_decisions_and_evaluation(seeded_application):
    session, application, recruiter = seeded_application
    evaluate_application(session, application.id)
    register_decision(session, application.id, recruiter.id, "avanzar", None)

    audit = get_application_audit(session, application.id)
    assert audit["application_id"] == application.id
    assert "evaluation" in audit
    assert "decisions" in audit
    assert len(audit["decisions"]) >= 1
