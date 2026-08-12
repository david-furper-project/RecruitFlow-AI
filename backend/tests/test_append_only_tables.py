import uuid

import pytest
from sqlmodel import Session, text

from app.db.session import engine, init_db
from app.models import Application, CandidateProfile, Company, Decision, Evaluation, JobOffer, Notification, User


@pytest.fixture(scope="module", autouse=True)
def ensure_schema():
    init_db()


def _make_user(email: str):
    return User(email=email, role="candidate", password_hash="hash")


def _make_company(name: str):
    return Company(name=name, industry="Tech", description="Test company")


def _make_candidate(user_id: int):
    return CandidateProfile(
        user_id=user_id,
        full_name="Test User",
        tech_stack="Python, SQL",
        years_of_experience=3,
        extracted_text="Candidate for testing",
    )


def _make_job_offer(company_id: int):
    return JobOffer(
        company_id=company_id,
        title="Backend Engineer",
        description="Build APIs",
        requirements="Python, FastAPI",
        tech_stack="Python, SQL",
        salary_range="100k-120k",
        experience_years=3,
        seniority="mid",
        status="open",
        embedding=[0.1] * 1536,
    )


def test_evaluation_update_is_rejected():
    with Session(engine) as session:
        user = _make_user(f"candidate-{uuid.uuid4()}@example.com")
        company = _make_company(f"Company-{uuid.uuid4()}")
        session.add_all([user, company])
        session.commit()
        session.refresh(user)
        session.refresh(company)

        candidate = _make_candidate(user.id)
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        job_offer = _make_job_offer(company.id)
        session.add(job_offer)
        session.commit()
        session.refresh(job_offer)

        application = Application(
            candidate_id=candidate.id,
            job_offer_id=job_offer.id,
            status="pending",
        )
        session.add(application)
        session.commit()
        session.refresh(application)

        evaluation = Evaluation(
            application_id=application.id,
            suggested_category="apto",
            explanation="Matches the role",
            model_version="gpt-4o-mini-2024-07-18",
            prompt_version="scoring-v1.0",
            excluded_fields="nationality",
        )
        session.add(evaluation)
        session.commit()
        session.refresh(evaluation)

        with pytest.raises(Exception):
            session.exec(
                text("UPDATE evaluation SET suggested_category = 'no_apto' WHERE id = :id"),
                {"id": evaluation.id},
            )
            session.commit()


def test_decision_update_is_rejected():
    with Session(engine) as session:
        user = _make_user(f"recruiter-{uuid.uuid4()}@example.com")
        company = _make_company(f"Company-Decision-{uuid.uuid4()}")
        session.add_all([user, company])
        session.commit()
        session.refresh(user)
        session.refresh(company)

        candidate = _make_candidate(user.id)
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

        job_offer = _make_job_offer(company.id)
        session.add(job_offer)
        session.commit()
        session.refresh(job_offer)

        application = Application(
            candidate_id=candidate.id,
            job_offer_id=job_offer.id,
            status="pending",
        )
        session.add(application)
        session.commit()
        session.refresh(application)

        decision = Decision(
            application_id=application.id,
            user_id=user.id,
            action="avanzar",
            discrepancy_reason="Cliente quiere avanzar",
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)

        with pytest.raises(Exception):
            session.exec(
                text("UPDATE decision SET action = 'descartar' WHERE id = :id"),
                {"id": decision.id},
            )
            session.commit()
