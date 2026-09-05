import asyncio
import uuid

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Application,
    CandidateProfile,
    Company,
    Decision,
    JobOffer,
    Notification,
    PipelineStage,
    User,
)
from app.services import notification_service
from app.services.audit_service import get_application_audit
from app.services.scoring_service import register_decision


@pytest.fixture
def seeded_application():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        candidate_user = User(
            email=f"candidate-{uuid.uuid4()}@example.com",
            role="candidate",
            password_hash="hash",
        )
        recruiter = User(
            email=f"recruiter-{uuid.uuid4()}@example.com",
            role="recruiter",
            password_hash="hash",
        )
        company = Company(name="Feedback Test")
        session.add_all([candidate_user, recruiter, company])
        session.commit()

        candidate = CandidateProfile(user_id=candidate_user.id, full_name="Ana Pérez")
        offer = JobOffer(
            company_id=company.id,
            title="QA Automation Engineer",
            description="Automatización",
            requirements="Pruebas automatizadas",
            tech_stack="Playwright",
            salary_range="Confidencial",
            experience_years=2,
            seniority="Semi Senior",
        )
        session.add_all([candidate, offer])
        session.commit()
        stage = PipelineStage(
            job_offer_id=offer.id,
            name="Pendiente",
            order_index=1,
            kind="inicial",
        )
        session.add(stage)
        session.commit()
        application = Application(
            candidate_id=candidate.id,
            job_offer_id=offer.id,
            current_stage_id=stage.id,
            status="pending",
        )
        session.add(application)
        session.commit()
        yield session, application, recruiter


def test_discard_requires_candidate_facing_feedback(seeded_application):
    session, application, recruiter = seeded_application

    with pytest.raises(ValueError, match="feedback para el candidato es obligatorio"):
        register_decision(session, application.id, recruiter.id, "descartar", None)

    session.refresh(application)
    assert application.outcome is None
    assert session.exec(select(Decision)).all() == []


def test_discard_requires_a_deliverable_candidate_email(seeded_application):
    session, application, recruiter = seeded_application
    candidate = application.candidate
    candidate.user.email = f"cv-{uuid.uuid4()}@candidate.internal.invalid"
    candidate.contact_email = None
    session.add(candidate.user)
    session.add(candidate)
    session.commit()

    with pytest.raises(ValueError, match="no tiene un correo válido"):
        register_decision(
            session,
            application.id,
            recruiter.id,
            "descartar",
            None,
            feedback="Necesitamos mayor experiencia para esta vacante.",
        )

    assert session.exec(select(Decision)).all() == []
    assert session.exec(select(Notification)).all() == []


def test_each_discard_records_and_emails_its_own_feedback(seeded_application, monkeypatch):
    session, application, recruiter = seeded_application
    sent_messages = []

    class MailRecorder:
        def send(self, to, subject, html):
            sent_messages.append({"to": to, "subject": subject, "html": html})
            return f"message-{len(sent_messages)}"

    monkeypatch.setattr("app.services.mail.get_mail_provider", lambda: MailRecorder())

    first_feedback = "Fortalece tu experiencia práctica con <Playwright> y automatización web."
    first = register_decision(
        session,
        application.id,
        recruiter.id,
        "descartar",
        None,
        feedback=first_feedback,
    )
    pending_notification = session.exec(
        select(Notification).where(Notification.decision_id == first.id)
    ).one()
    assert pending_notification.send_status == "reintento"
    monkeypatch.setattr(notification_service, "engine", session.bind)
    asyncio.run(notification_service.async_deliver_decision_notification(first.id))
    asyncio.run(notification_service.async_deliver_decision_notification(first.id))
    assert len(sent_messages) == 1

    second_feedback = "Profundiza en diseño de pruebas de integración y documentación técnica."
    second = register_decision(
        session,
        application.id,
        recruiter.id,
        "descartar",
        None,
        feedback=second_feedback,
    )
    asyncio.run(notification_service.async_deliver_decision_notification(second.id))

    session.expire_all()
    decisions = session.exec(select(Decision).order_by(Decision.id)).all()
    notifications = session.exec(select(Notification).order_by(Notification.id)).all()
    first_notification = next(item for item in notifications if item.decision_id == first.id)
    second_notification = next(item for item in notifications if item.decision_id == second.id)

    assert [decision.feedback for decision in decisions] == [first_feedback, second_feedback]
    assert first_notification.decision_id == first.id
    assert second_notification.decision_id == second.id
    assert first_notification.id != second_notification.id
    assert len(notifications) == 2
    assert all(notification.type == "descarte" for notification in notifications)
    assert all(notification.send_status == "enviado" for notification in notifications)
    assert len(sent_messages) == 2
    assert "QA Automation Engineer" in sent_messages[0]["subject"]
    assert "&lt;Playwright&gt;" in sent_messages[0]["html"]
    assert second_feedback in sent_messages[1]["html"]

    audit = get_application_audit(session, application.id)
    audit_by_id = {item["id"]: item for item in audit["decisions"]}
    assert audit_by_id[first.id]["feedback"] == first_feedback
    assert audit_by_id[first.id]["notification"]["send_status"] == "enviado"
    assert audit_by_id[second.id]["feedback"] == second_feedback
    assert audit_by_id[second.id]["notification"]["send_status"] == "enviado"
