import asyncio
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.session import engine, init_db
from app.main import app
from app.core.auth import create_access_token
from app.models import (
    Application,
    CandidateProfile,
    Company,
    Decision,
    Evaluation,
    JobOffer,
    PipelineStage,
    SourcingProspect,
    User,
)
from app.services.sourcing_prospect_service import (
    convert_prospect_to_application,
    create_preview_token,
    find_profile_url,
    invitation_token_hash,
    issue_invitation,
    professional_embedding_text,
    serialize_prospect,
)
from app.services.matching_service import candidate_profile_text


client = TestClient(app)


def _headers(recruiter: User) -> dict[str, str]:
    token = create_access_token(
        {"sub": recruiter.email, "user_id": recruiter.id, "role": recruiter.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def sourcing_schema():
    init_db()


@pytest.fixture(autouse=True)
def deterministic_ai(monkeypatch):
    vector = [0.1] * 1536
    monkeypatch.setattr("app.services.sourcing_prospect_service.generate_embedding", lambda _: vector)
    monkeypatch.setattr("app.api.sourcing.preview_affinity", lambda *_: (88.5, "Coincidencia profesional de prueba."))
    monkeypatch.setattr("app.services.notification_service.async_deliver_notification", lambda *args: None)
    monkeypatch.setattr("app.services.scoring_service.async_evaluate_application", lambda *args: None)
    monkeypatch.setattr(
        "app.services.sourcing_prospect_service.validate_cv_upload",
        lambda file: (
            b"pdf-test",
            "Ana Pérez Backend Engineer Python FastAPI PostgreSQL con cinco años de experiencia profesional.",
            file.filename or "cv.pdf",
        ),
    )


def _recruiter(session: Session) -> User:
    user = User(email="recruiter@sourcing.test", password_hash="hash", role="recruiter")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _offer(session: Session, title: str = "Backend") -> JobOffer:
    company = session.exec(select(Company).where(Company.name == "Sourcing Test")).first()
    if company is None:
        company = Company(name="Sourcing Test", industry="Tech")
        session.add(company)
        session.commit()
        session.refresh(company)
    offer = JobOffer(
        company_id=company.id,
        title=title,
        description="Construcción de APIs",
        requirements="Python, FastAPI y PostgreSQL",
        tech_stack="Python, PostgreSQL",
        salary_range="1",
        experience_years=2,
        seniority="mid",
        embedding=[0.1] * 1536,
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    session.add(PipelineStage(job_offer_id=offer.id, name="Pendiente", order_index=1, kind="inicial"))
    session.commit()
    return offer


def _structured(name: str = "Ana Pérez") -> dict:
    return {
        "full_name": name,
        "headline": "Backend Engineer",
        "experience": "APIs con Python y FastAPI",
        "years_of_experience": 5,
        "education": "Ingeniería y cursos técnicos",
        "skills": "Python, FastAPI, PostgreSQL",
        "summary": "Especialista backend",
        "contact_email": None,
        "contact_phone": None,
        "professional_text": (
            "Ana Pérez. Perfil profesional: Backend Engineer. Experiencia laboral: cinco años creando APIs. "
            "Habilidades técnicas: Python, FastAPI y PostgreSQL. Educación académica: Ingeniería."
        ),
    }


def _preview_token(*, offer: JobOffer, recruiter: User, url: str) -> str:
    return create_preview_token(
        structured=_structured(),
        source="linkedin",
        source_url=url,
        job_offer_id=offer.id,
        created_by_user_id=recruiter.id,
        contact_notes="Perfil público exportado a PDF.",
    )


def _confirm(*, offer: JobOffer, recruiter: User, url: str) -> dict:
    response = client.post(
        "/api/sourcing/prospects/import/confirm",
        json={"preview_token": _preview_token(offer=offer, recruiter=recruiter, url=url)},
        headers=_headers(recruiter),
    )
    assert response.status_code == 201, response.text
    return response.json()["prospect"]


def _interested_prospect(session: Session, url: str) -> tuple[SourcingProspect, JobOffer, User]:
    recruiter = _recruiter(session)
    offer = _offer(session)
    prospect_data = _confirm(offer=offer, recruiter=recruiter, url=url)
    prospect = session.get(SourcingProspect, prospect_data["id"])
    prospect.status = "interesado"
    prospect.contacted_at = datetime.utcnow()
    prospect.responded_at = datetime.utcnow()
    session.add(prospect)
    session.commit()
    session.refresh(prospect)
    return prospect, offer, recruiter


def test_pdf_preview_does_not_persist(monkeypatch):
    monkeypatch.setattr("app.api.sourcing.structure_sourcing_document", lambda _: _structured())
    monkeypatch.setattr(
        "app.api.sourcing.validate_cv_upload",
        lambda file: (b"pdf-test", _structured()["professional_text"], file.filename or "perfil.pdf"),
    )
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        offer_id = offer.id
        headers = _headers(recruiter)
        before = (
            len(session.exec(select(CandidateProfile)).all()),
            len(session.exec(select(SourcingProspect)).all()),
            len(session.exec(select(Application)).all()),
        )
    with open("test.pdf", "rb") as pdf:
        response = client.post(
            "/api/sourcing/prospects/import",
            data={
                "source": "linkedin",
                "source_url": "https://www.linkedin.com/in/ana-preview",
                "job_offer_id": offer_id,
            },
            files={"file": ("perfil.pdf", pdf, "application/pdf")},
            headers=headers,
        )
    assert response.status_code == 200, response.text
    assert response.json()["persisted"] is False
    with Session(engine) as session:
        after = (
            len(session.exec(select(CandidateProfile)).all()),
            len(session.exec(select(SourcingProspect)).all()),
            len(session.exec(select(Application)).all()),
        )
    assert after == before


def test_profile_url_is_detected_from_pdf_text():
    text = "Perfil profesional exportado desde https://www.linkedin.com/in/ana-detectada/ con experiencia backend."
    assert find_profile_url(text, "linkedin") == "https://www.linkedin.com/in/ana-detectada"


def test_import_creates_candidate_and_prospect_but_no_application():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        result = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/ana-import")
        prospect = session.get(SourcingProspect, result["id"])
        candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
        assert prospect.status == "identificado"
        assert prospect.created_by_user_id == recruiter.id
        assert prospect.semantic_similarity == pytest.approx(100.0)
        assert candidate.resume_url is None
        assert session.exec(select(Application)).all() == []


def test_sourcing_and_application_use_the_same_professional_embedding_input():
    structured = _structured()
    candidate = CandidateProfile(
        user_id=1,
        full_name=structured["full_name"],
        professional_headline=structured["headline"],
        years_of_experience=structured["years_of_experience"],
        career_summary=structured["summary"],
        tech_stack=structured["skills"],
        courses_and_diplomas=structured["education"],
        extracted_text=structured["professional_text"],
    )
    assert professional_embedding_text(structured) == candidate_profile_text(candidate)


def test_confirmed_prospect_preserves_the_exact_preview_score():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        token = create_preview_token(
            structured=_structured(),
            source="linkedin",
            source_url="https://www.linkedin.com/in/exact-preview-score",
            job_offer_id=offer.id,
            created_by_user_id=recruiter.id,
            contact_notes=None,
            semantic_similarity=75.69,
            match_explanation="Afinidad calculada en la vista previa.",
        )
        headers = _headers(recruiter)
    response = client.post(
        "/api/sourcing/prospects/import/confirm",
        json={"preview_token": token},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["prospect"]["semantic_similarity"] == pytest.approx(75.69)


def test_legacy_duplicate_document_uses_the_application_affinity():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect_data = _confirm(
            offer=offer,
            recruiter=recruiter,
            url="https://www.linkedin.com/in/legacy-document-match",
        )
        prospect = session.get(SourcingProspect, prospect_data["id"])
        source_candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
        applicant_user = User(
            email="legacy-applicant@example.com",
            password_hash="hash",
            role="candidate",
        )
        session.add(applicant_user)
        session.flush()
        applicant_candidate = CandidateProfile(
            user_id=applicant_user.id,
            full_name=source_candidate.full_name,
            extracted_text=source_candidate.extracted_text,
            embedding=[0.1] * 1536,
        )
        session.add(applicant_candidate)
        session.flush()
        application = Application(
            candidate_id=applicant_candidate.id,
            job_offer_id=offer.id,
            status="pending",
            similarity_score=0.7351,
        )
        session.add(application)
        session.flush()
        session.add(Evaluation(
            application_id=application.id,
            suggested_category="en_revision",
            explanation="Afinidad unificada: 73.51%.",
            model_version="gemini-embedding-2-1536",
            prompt_version="semantic-affinity-v2.1",
            excluded_fields="nacionalidad",
        ))
        session.commit()

        serialized = serialize_prospect(session, prospect)
        assert serialized["semantic_similarity"] == pytest.approx(73.51)
        assert serialized["match_explanation"] == "Afinidad unificada: 73.51%."
        assert serialized["application_id"] == application.id


def test_extracted_contact_is_preserved_as_suggestion_and_can_be_corrected():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        structured = {
            **_structured(),
            "contact_email": "ana.linkedin@example.com",
            "contact_phone": "+56 9 2222 3333",
        }
        token = create_preview_token(
            structured=structured,
            source="linkedin",
            source_url="https://www.linkedin.com/in/contacto-extraido",
            job_offer_id=offer.id,
            created_by_user_id=recruiter.id,
            contact_notes=None,
        )
        headers = _headers(recruiter)
    response = client.post(
        "/api/sourcing/prospects/import/confirm",
        json={"preview_token": token},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    prospect = response.json()["prospect"]
    assert prospect["suggested_email"] == "ana.linkedin@example.com"
    assert prospect["suggested_phone"] == "+56 9 2222 3333"
    assert prospect["candidate"]["contact_email"] == "ana.linkedin@example.com"
    assert prospect["candidate"]["phone"] == "+56 9 2222 3333"

    contact = client.post(
        f"/api/sourcing/prospects/{prospect['id']}/contact",
        json={"channel": "correo", "value": "ana.actualizada@example.com"},
        headers=headers,
    )
    assert contact.status_code == 200, contact.text
    assert contact.json()["prospect"]["suggested_email"] == "ana.actualizada@example.com"
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_duplicate_candidate_offer_is_rejected():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        token = _preview_token(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/ana-duplicate")
        headers = _headers(recruiter)
    assert client.post("/api/sourcing/prospects/import/confirm", json={"preview_token": token}, headers=headers).status_code == 201
    duplicate = client.post("/api/sourcing/prospects/import/confirm", json={"preview_token": token}, headers=headers)
    assert duplicate.status_code == 409
    with Session(engine) as session:
        assert len(session.exec(select(SourcingProspect)).all()) == 1
        assert session.exec(select(Application)).all() == []


def test_same_candidate_can_have_independent_prospects_for_two_offers():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        first_offer = _offer(session, "Backend")
        second_offer = _offer(session, "Platform")
        first = _confirm(offer=first_offer, recruiter=recruiter, url="https://www.linkedin.com/in/shared-profile")
        second = _confirm(offer=second_offer, recruiter=recruiter, url="https://www.linkedin.com/in/shared-profile")
        assert first["candidate_profile_id"] == second["candidate_profile_id"]
        assert first["id"] != second["id"]
        assert len(session.exec(select(Application)).all()) == 0


def test_contact_interest_and_invitation_never_create_application(monkeypatch):
    class MailRecorder:
        def send(self, *args):
            return "message-id"

    monkeypatch.setattr("app.services.mail.get_mail_provider", lambda: MailRecorder())
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/contact-flow")
    assert client.post(
        f"/api/sourcing/prospects/{prospect['id']}/contact",
        json={"channel": "linkedin", "notes": "Mensaje enviado"},
        headers=_headers(recruiter),
    ).status_code == 200
    assert client.post(
        f"/api/sourcing/prospects/{prospect['id']}/response",
        json={"response": "interesado"},
        headers=_headers(recruiter),
    ).status_code == 200
    invitation = client.post(
        f"/api/sourcing/prospects/{prospect['id']}/invite",
        json={"email": "ana@example.com"},
        headers=_headers(recruiter),
    )
    assert invitation.status_code == 200, invitation.text
    raw_token = invitation.json()["invitation_url"].rsplit("/", 1)[-1]
    with Session(engine) as session:
        stored = session.get(SourcingProspect, prospect["id"])
        assert stored.status == "invitado"
        assert stored.invitation_token_hash == invitation_token_hash(raw_token)
        assert raw_token not in stored.invitation_token_hash
        assert session.exec(select(Application)).all() == []


def test_first_contact_reports_delivery_and_only_then_marks_contacted(monkeypatch):
    sent_messages = []

    class MailRecorder:
        def send(self, to, subject, html):
            sent_messages.append((to, subject, html))
            return "brevo-message-id"

    monkeypatch.setattr("app.services.mail.get_mail_provider", lambda: MailRecorder())
    monkeypatch.setattr("app.api.sourcing.settings.MAIL_PROVIDER", "brevo")
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/correo-ok")
        prospect_id = prospect["id"]
        headers = _headers(recruiter)

    response = client.post(
        f"/api/sourcing/prospects/{prospect_id}/contact",
        json={
            "channel": "correo",
            "value": "ana@example.com",
            "message": "Hola Ana, tenemos una oportunidad para ti.",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["delivery"] == {
        "status": "accepted",
        "provider": "brevo",
        "recipient": "ana@example.com",
        "message_id": "brevo-message-id",
    }
    assert sent_messages and sent_messages[0][0] == "ana@example.com"
    with Session(engine) as session:
        assert session.get(SourcingProspect, prospect_id).status == "contactado"


def test_contact_email_cannot_belong_to_another_candidate():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/correo-duplicado")
        existing_user = User(
            email="existing@candidate.internal.invalid",
            password_hash="hash",
            role="candidate",
        )
        session.add(existing_user)
        session.flush()
        session.add(CandidateProfile(
            user_id=existing_user.id,
            full_name="Candidata existente",
            resume_url="pending",
            contact_email="correo.compartido@example.com",
        ))
        session.commit()
        prospect_id = prospect["id"]
        headers = _headers(recruiter)

    response = client.post(
        f"/api/sourcing/prospects/{prospect_id}/contact",
        json={
            "channel": "correo",
            "value": "correo.compartido@example.com",
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert "otro candidato" in response.json()["detail"]
    with Session(engine) as session:
        stored = session.get(SourcingProspect, prospect_id)
        candidate = session.get(CandidateProfile, stored.candidate_profile_id)
        assert stored.status == "identificado"
        assert candidate.contact_email is None


def test_first_contact_mail_failure_does_not_mark_contacted(monkeypatch):
    class FailingMailProvider:
        def send(self, *_):
            raise RuntimeError("Brevo rechazó el mensaje de prueba.")

    monkeypatch.setattr("app.services.mail.get_mail_provider", lambda: FailingMailProvider())
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/correo-error")
        prospect_id = prospect["id"]
        headers = _headers(recruiter)

    response = client.post(
        f"/api/sourcing/prospects/{prospect_id}/contact",
        json={
            "channel": "correo",
            "value": "ana@example.com",
            "message": "Hola Ana, tenemos una oportunidad para ti.",
        },
        headers=headers,
    )

    assert response.status_code == 502
    assert "Brevo rechazó" in response.json()["detail"]
    with Session(engine) as session:
        stored = session.get(SourcingProspect, prospect_id)
        candidate = session.get(CandidateProfile, stored.candidate_profile_id)
        assert stored.status == "identificado"
        assert candidate.contact_email is None
        assert session.exec(select(Application)).all() == []


def test_invitation_uses_suggested_email_and_professional_message(monkeypatch):
    sent_messages = []

    class MailRecorder:
        def send(self, to, subject, html):
            sent_messages.append((to, subject, html))
            return "message-id"

    monkeypatch.setattr("app.services.mail.get_mail_provider", lambda: MailRecorder())
    with Session(engine) as session:
        prospect, offer, recruiter = _interested_prospect(session, "https://www.linkedin.com/in/invitacion-profesional")
        candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
        candidate.contact_email = "ana.sugerida@example.com"
        session.add(candidate)
        session.commit()
        prospect_id = prospect.id
        offer_title = offer.title
        headers = _headers(recruiter)
    invitation = client.post(
        f"/api/sourcing/prospects/{prospect_id}/invite",
        json={},
        headers=headers,
    )
    assert invitation.status_code == 200, invitation.text
    payload = invitation.json()
    assert payload["recipient_email"] == "ana.sugerida@example.com"
    assert payload["email_delivered"] is True
    assert payload["invitation_url"] in payload["suggested_message"]
    assert "Estuvimos revisando tu perfil profesional" in payload["suggested_message"]
    assert "completar tu postulación aquí" in payload["suggested_message"]
    assert sent_messages[0][0] == "ana.sugerida@example.com"
    assert offer_title in sent_messages[0][1]
    assert payload["invitation_url"] in sent_messages[0][2]
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_no_interesado_never_creates_application():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/no-quiere")
    headers = _headers(recruiter)
    assert client.post(f"/api/sourcing/prospects/{prospect['id']}/contact", json={"channel": "linkedin"}, headers=headers).status_code == 200
    response = client.post(f"/api/sourcing/prospects/{prospect['id']}/response", json={"response": "no_interesado"}, headers=headers)
    assert response.status_code == 200
    with Session(engine) as session:
        assert session.get(SourcingProspect, prospect["id"]).status == "no_interesado"
        assert session.exec(select(Application)).all() == []


def test_sin_respuesta_allows_another_contact():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/reintento")
    headers = _headers(recruiter)
    assert client.post(f"/api/sourcing/prospects/{prospect['id']}/contact", json={"channel": "linkedin"}, headers=headers).status_code == 200
    assert client.post(f"/api/sourcing/prospects/{prospect['id']}/response", json={"response": "sin_respuesta"}, headers=headers).status_code == 200
    retry = client.post(
        f"/api/sourcing/prospects/{prospect['id']}/contact",
        json={"channel": "correo", "value": "ana@example.com", "notes": "Segundo intento"},
        headers=headers,
    )
    assert retry.status_code == 200
    assert retry.json()["prospect"]["status"] == "contactado"
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_invitation_requires_prior_interest():
    with Session(engine) as session:
        recruiter = _recruiter(session)
        offer = _offer(session)
        prospect = _confirm(offer=offer, recruiter=recruiter, url="https://www.linkedin.com/in/no-interest")
    assert client.post(f"/api/sourcing/prospects/{prospect['id']}/invite", json={}, headers=_headers(recruiter)).status_code == 409
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_expired_invitation_is_rejected():
    with Session(engine) as session:
        prospect, _, _ = _interested_prospect(session, "https://www.linkedin.com/in/expired")
        raw_token, _ = issue_invitation(prospect)
        prospect.invitation_expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.add(prospect)
        session.commit()
    assert client.get(f"/api/sourcing/invitations/{raw_token}").status_code == 410
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_missing_cv_and_missing_consent_do_not_convert():
    with Session(engine) as session:
        prospect, _, _ = _interested_prospect(session, "https://www.linkedin.com/in/required-fields")
        raw_token, _ = issue_invitation(prospect)
        session.add(prospect)
        session.commit()
    missing_cv = client.post(
        f"/api/sourcing/invitations/{raw_token}/apply",
        data={"full_name": "Ana Pérez", "email": "ana@example.com", "consent": "true"},
    )
    assert missing_cv.status_code == 422
    with open("test.pdf", "rb") as pdf:
        missing_consent = client.post(
            f"/api/sourcing/invitations/{raw_token}/apply",
            data={"full_name": "Ana Pérez", "email": "ana@example.com", "consent": "false"},
            files={"file": ("cv.pdf", pdf, "application/pdf")},
        )
    assert missing_consent.status_code == 400
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_acceptance_creates_exactly_one_application(monkeypatch):
    evaluation_calls = []
    notification_calls = []
    monkeypatch.setattr("app.services.scoring_service.async_evaluate_application", lambda application_id: evaluation_calls.append(application_id))
    monkeypatch.setattr("app.services.notification_service.async_deliver_notification", lambda application_id, kind: notification_calls.append((application_id, kind)))
    monkeypatch.setattr(
        "app.services.sourcing_prospect_service.extract_candidate_profile",
        lambda _: {
            "full_name": "Ana Pérez",
            "tech_stack": "Python, FastAPI",
            "years_of_experience": 5,
            "career_summary": "Backend Engineer",
        },
    )

    async def fake_upload(*_):
        return "http://localhost:8000/uploads/cvs/1/current.pdf"

    monkeypatch.setattr("app.services.sourcing_prospect_service.upload_cv_to_storage", fake_upload)
    with Session(engine) as session:
        prospect, _, _ = _interested_prospect(session, "https://www.linkedin.com/in/convert")
        prospect_id = prospect.id
        raw_token, _ = issue_invitation(prospect)
        session.add(prospect)
        session.commit()
    with open("test.pdf", "rb") as pdf:
        response = client.post(
            f"/api/sourcing/invitations/{raw_token}/apply",
            data={
                "full_name": "Ana Pérez",
                "email": "ana.convertida@example.com",
                "phone": "+56911111111",
                "consent": "true",
            },
            files={"file": ("cv-actualizado.pdf", pdf, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    with Session(engine) as session:
        applications = session.exec(select(Application)).all()
        stored = session.get(SourcingProspect, prospect_id)
        assert len(applications) == 1
        assert applications[0].consent_given_at is not None
        assert applications[0].current_stage_id is not None
        assert stored.status == "convertido"
        assert stored.converted_at is not None
        assert stored.invitation_token_hash is None
        assert session.exec(select(Decision)).all() == []
        assert evaluation_calls == [applications[0].id]
        assert notification_calls == [(applications[0].id, "recepcion")]
    assert client.post(f"/api/sourcing/invitations/{raw_token}/apply").status_code in {404, 409, 422}
    with Session(engine) as session:
        assert len(session.exec(select(Application)).all()) == 1


def test_external_conversion_requires_verified_authorization():
    with Session(engine) as session:
        prospect, _, recruiter = _interested_prospect(session, "https://www.linkedin.com/in/external")
        prospect_id = prospect.id
        headers = _headers(recruiter)
    with open("test.pdf", "rb") as pdf:
        response = client.post(
            f"/api/sourcing/prospects/{prospect_id}/convert",
            data={
                "full_name": "Ana Pérez",
                "email": "ana@example.com",
                "consent": "true",
                "authorization_confirmed": "false",
                "authorization_channel": "correo",
                "authorization_at": datetime.utcnow().isoformat(),
            },
            files={"file": ("cv.pdf", pdf, "application/pdf")},
            headers=headers,
        )
    assert response.status_code == 400
    with Session(engine) as session:
        assert session.exec(select(Application)).all() == []


def test_conversion_rollback_does_not_mark_prospect_converted(monkeypatch):
    async def fake_upload(*_):
        return "https://storage.invalid/current.pdf"

    monkeypatch.setattr("app.services.sourcing_prospect_service.upload_cv_to_storage", fake_upload)
    monkeypatch.setattr(
        "app.services.sourcing_prospect_service.extract_candidate_profile",
        lambda _: {"full_name": "Ana Pérez", "tech_stack": "Python", "career_summary": "Backend"},
    )
    with Session(engine) as session:
        prospect, _, _ = _interested_prospect(session, "https://www.linkedin.com/in/rollback")
        prospect_id = prospect.id
    with Session(engine) as session:
        prospect = session.get(SourcingProspect, prospect_id)
        original_commit = session.commit

        def fail_commit():
            raise RuntimeError("fallo transaccional simulado")

        session.commit = fail_commit
        with pytest.raises(RuntimeError, match="fallo transaccional"):
            asyncio.run(
                convert_prospect_to_application(
                    session=session,
                    prospect=prospect,
                    file=UploadFile(filename="cv.pdf", file=BytesIO(b"pdf")),
                    full_name="Ana Pérez",
                    email="ana.rollback@example.com",
                    phone=None,
                    consent=True,
                    authorization_channel="correo",
                    authorization_at=datetime.utcnow(),
                    authorization_notes="Correo archivado",
                )
            )
        session.commit = original_commit
    with Session(engine) as session:
        assert session.get(SourcingProspect, prospect_id).status == "interesado"
        assert session.exec(select(Application)).all() == []


def test_sensitive_attributes_are_excluded_from_matching_text():
    matching_text = professional_embedding_text(
        {
            "headline": "Backend Engineer",
            "summary": "Nacionalidad: chilena. Ubicación: Santiago. Edad: 31. Género: mujer. Python y FastAPI.",
            "skills": "PostgreSQL",
        }
    ).lower()
    for forbidden in ("nacionalidad", "chilena", "ubicación", "santiago", "edad", "género", "mujer"):
        assert forbidden not in matching_text
    assert "python" in matching_text


def test_source_status_and_uniqueness_constraints_are_declared():
    constraints = {constraint.name for constraint in SourcingProspect.__table__.constraints}
    assert "ck_sourcingprospect_source" in constraints
    assert "ck_sourcingprospect_status" in constraints
    assert "uq_sourcingprospect_candidate_job" in constraints
    assert "nationality" not in SourcingProspect.model_fields


def test_recruiter_actions_require_authentication():
    assert client.get("/api/sourcing/prospects?job_offer_id=1").status_code == 401
