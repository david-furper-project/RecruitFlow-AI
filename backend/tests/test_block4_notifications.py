import uuid

import pytest
from sqlmodel import Session

from app.db.session import engine
from app.models import Application, CandidateProfile, Company, Decision, JobOffer, Notification, User
from app.services.notification_service import (
    deliver_decision_notification,
    get_notification_completion_rate,
)


@pytest.fixture
def seeded_decision():
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
            career_summary="Senior Python backend engineer.",
            embedding=[0.1] * 1536,
        )
        job_offer = JobOffer(
            company_id=company.id,
            title="Backend Engineer",
            description="Senior backend developer for Python APIs and PostgreSQL.",
            requirements="Python, FastAPI, PostgreSQL",
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

        decision = Decision(
            application_id=application.id,
            user_id=recruiter.id,
            action="avanzar",
            discrepancy_reason=None,
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)

        yield session, application, decision


def test_decision_notification_is_logged_and_sent(seeded_decision, monkeypatch):
    session, _, decision = seeded_decision

    monkeypatch.setattr("app.services.notification_service.sendgrid_mailer", lambda *args, **kwargs: True)

    notification = deliver_decision_notification(session, decision.id)

    assert notification is not None
    assert notification.type == "avance"
    assert notification.send_status == "enviado"
    assert session.get(Notification, notification.id) is not None


def test_decision_notification_retries_and_fails_after_three_attempts(seeded_decision, monkeypatch):
    session, _, decision = seeded_decision

    def failing_send(*args, **kwargs):
        raise RuntimeError("SendGrid unavailable")

    monkeypatch.setattr("app.services.notification_service.sendgrid_mailer", failing_send)

    notification = deliver_decision_notification(session, decision.id)

    assert notification.send_status == "fallido"
    assert notification.retry_count == 3


def test_notification_completion_rate_is_calculated(seeded_decision, monkeypatch):
    session, _, decision = seeded_decision

    monkeypatch.setattr("app.services.notification_service.sendgrid_mailer", lambda *args, **kwargs: True)
    send_ok = deliver_decision_notification(session, decision.id)
    send_ok.sent_at = send_ok.sent_at or send_ok.created_at

    stale = Notification(
        application_id=decision.application_id,
        type="descarte",
        send_status="enviado",
        sent_at=send_ok.sent_at,
        created_at=send_ok.created_at,
        retry_count=0,
    )
    session.add(stale)
    session.commit()

    rate = get_notification_completion_rate(session)
    assert 0.0 <= rate <= 1.0
