from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.auth import create_access_token
from app.db.session import engine, init_db
from app.main import app
from app.models import (
    Application,
    CandidateProfile,
    Company,
    Decision,
    JobOffer,
    PipelineStage,
    User,
)
from app.services.scoring_service import register_decision


client = TestClient(app)


def _seed_process() -> tuple[int, int, int, dict[str, str]]:
    init_db()
    with Session(engine) as session:
        recruiter = User(email="recruiter.lifecycle@test.local", role="recruiter", password_hash="hash")
        candidate_user = User(email="candidate.lifecycle@test.local", role="candidate", password_hash="hash")
        company = Company(name="Lifecycle Company")
        session.add_all([recruiter, candidate_user, company])
        session.commit()
        candidate = CandidateProfile(
            user_id=candidate_user.id,
            full_name="Finalista Prueba",
            tech_stack="Python",
            embedding=[0.1] * 1536,
        )
        offer = JobOffer(
            company_id=company.id,
            title="Backend Lifecycle",
            description="APIs",
            requirements="Python",
            tech_stack="Python",
            salary_range="100",
            experience_years=2,
            seniority="mid",
            status="open",
            embedding=[0.1] * 1536,
        )
        session.add_all([candidate, offer])
        session.commit()
        initial = PipelineStage(job_offer_id=offer.id, name="Pendiente", order_index=1, kind="inicial")
        final = PipelineStage(job_offer_id=offer.id, name="Finalista", order_index=2, kind="final")
        session.add_all([initial, final])
        session.commit()
        application = Application(
            candidate_id=candidate.id,
            job_offer_id=offer.id,
            status="pending",
            current_stage_id=initial.id,
        )
        session.add(application)
        session.commit()
        token = create_access_token(
            {"sub": recruiter.email, "user_id": recruiter.id, "role": recruiter.role}
        )
        return offer.id, candidate.id, application.id, {"Authorization": f"Bearer {token}"}


def test_reaching_final_stage_closes_offer_but_allows_reopening():
    offer_id, _, application_id, headers = _seed_process()
    with Session(engine) as session:
        recruiter = session.exec(select(User).where(User.email == "recruiter.lifecycle@test.local")).one()
        register_decision(session, application_id, recruiter.id, "avanzar", None)
        session.expire_all()
        assert session.get(JobOffer, offer_id).status == "closed"
        assert session.get(Application, application_id).outcome == "contratado"
        assert len(session.exec(select(Decision).where(Decision.application_id == application_id)).all()) == 1

    reopened = client.put(f"/api/offers/{offer_id}/reopen", headers=headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "open"

    closed_final = client.put(f"/api/offers/{offer_id}/close-final", headers=headers)
    assert closed_final.status_code == 200, closed_final.text
    assert closed_final.json()["status"] == "closed_final"
    assert closed_final.json()["reopen_allowed"] is False
    rejected_reopen = client.put(f"/api/offers/{offer_id}/reopen", headers=headers)
    assert rejected_reopen.status_code == 409


def test_closing_with_finalist_records_append_only_decision(monkeypatch):
    monkeypatch.setattr(
        "app.services.notification_service.async_deliver_decision_notification",
        lambda *_: None,
    )
    offer_id, candidate_id, application_id, headers = _seed_process()
    response = client.put(
        f"/api/offers/{offer_id}/close",
        json={"finalist_id": candidate_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"
    assert response.json()["reopen_allowed"] is True
    with Session(engine) as session:
        application = session.get(Application, application_id)
        decisions = session.exec(
            select(Decision).where(Decision.application_id == application_id)
        ).all()
        assert application.status == "pending"
        assert application.outcome == "contratado"
        assert len(decisions) == 1
        assert decisions[0].action == "avanzar"
        assert session.get(JobOffer, offer_id).status == "closed"
