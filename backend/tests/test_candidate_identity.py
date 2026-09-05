import asyncio
import io
import zipfile

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from app.api import candidates as candidates_api
from app.db.session import engine
from app.models import Application, CandidateProfile, CandidateResumeVersion, Company, JobOffer, User
from app.services.candidate_identity_service import trusted_email_from_cv


def _docx(text: str, filename: str = "cv.docx") -> UploadFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as document:
        content_types = zipfile.ZipInfo("[Content_Types].xml", date_time=(2024, 1, 1, 0, 0, 0))
        document.writestr(
            content_types,
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        entry = zipfile.ZipInfo("word/document.xml", date_time=(2024, 1, 1, 0, 0, 0))
        document.writestr(
            entry,
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return UploadFile(filename=filename, file=io.BytesIO(buffer.getvalue()))


def _offer(session: Session, company_id: int, title: str) -> JobOffer:
    offer = JobOffer(
        company_id=company_id,
        title=title,
        description="Descripción",
        requirements="Python",
        tech_stack="Python",
        salary_range="",
        experience_years=1,
        seniority="Junior",
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return offer


def _resume(identity: str = "Ana Pérez", extra: str = "") -> str:
    return (
        f"{identity}. Perfil profesional: Ingeniera de software especializada en calidad. "
        "Experiencia laboral: automatización de pruebas y desarrollo entre 2020-2025. "
        f"Habilidades técnicas: Python, Selenium y PostgreSQL. Educación académica: Ingeniería. {extra}"
    )


def test_same_cv_reuses_candidate_and_new_cv_appends_history(monkeypatch):
    monkeypatch.setattr(
        candidates_api,
        "extract_candidate_profile",
        lambda _text: {
            "full_name": "Ana Pérez",
            "email": "hallucinated-by-ai@example.com",
            "tech_stack": "Python",
            "years_of_experience": 4,
        },
    )
    monkeypatch.setattr(candidates_api, "generate_embedding", lambda _text: [0.0] * 1536)

    async def fake_upload(candidate_id, safe_name, _file_bytes):
        return f"/uploads/{candidate_id}/{safe_name}"

    monkeypatch.setattr(candidates_api, "upload_cv_to_storage", fake_upload)

    with Session(engine) as session:
        company = Company(name="Empresa identidad")
        session.add(company)
        session.commit()
        session.refresh(company)
        offer_one = _offer(session, company.id, "Vacante uno")
        offer_two = _offer(session, company.id, "Vacante dos")

        first = asyncio.run(
            candidates_api._process_single_application(
                session,
                "Ana Pérez",
                "  ANA.PEREZ@EXAMPLE.COM ",
                None,
                _docx(_resume()),
                offer_one.id,
            )
        )
        second = asyncio.run(
            candidates_api._process_single_application(
                session,
                "Ana Pérez",
                "ana.perez@example.com",
                None,
                _docx(_resume()),
                offer_two.id,
            )
        )
        updated = asyncio.run(
            candidates_api._process_single_application(
                session,
                "Ana Pérez",
                "ana.perez@example.com",
                None,
                _docx(_resume(extra="Python actualizado"), "cv-actualizado.docx"),
                offer_two.id,
            )
        )
        repeated = asyncio.run(
            candidates_api._process_single_application(
                session,
                "Ana Pérez",
                "ana.perez@example.com",
                None,
                _docx(_resume(extra="Python actualizado"), "cv-actualizado.docx"),
                offer_two.id,
            )
        )
        selected_profile = session.get(CandidateProfile, first["candidate_id"])
        with pytest.raises(HTTPException) as wrong_person:
            asyncio.run(
                candidates_api._process_single_application(
                    session,
                    selected_profile.full_name,
                    "",
                    selected_profile.phone,
                    _docx(
                        _resume("Otra Persona", "Correo: otra.persona@example.com"),
                        "cv-equivocado.docx",
                    ),
                    existing_candidate=selected_profile,
                    application_origin="pri",
                    resume_version_source="profile_update",
                )
            )
        assert wrong_person.value.status_code == 409

        profiles = session.exec(select(CandidateProfile)).all()
        applications = session.exec(select(Application)).all()
        users = session.exec(select(User).where(User.role == "candidate")).all()
        versions = session.exec(
            select(CandidateResumeVersion).order_by(CandidateResumeVersion.uploaded_at.asc())
        ).all()

        assert len(profiles) == 1
        assert len(users) == 1
        assert users[0].email == "ana.perez@example.com"
        assert profiles[0].contact_email == "ana.perez@example.com"
        assert len(applications) == 2
        assert {application.job_offer_id for application in applications} == {offer_one.id, offer_two.id}
        assert first["candidate_id"] == second["candidate_id"] == updated["candidate_id"] == repeated["candidate_id"]
        assert first["application_created"] is True
        assert first["resume_updated"] is True
        assert second["application_created"] is True
        assert second["candidate_reused"] is True
        assert second["resume_updated"] is False
        assert updated["application_created"] is False
        assert updated["resume_updated"] is True
        assert repeated["application_created"] is False
        assert repeated["resume_updated"] is False
        assert len(versions) == 2
        assert "Python actualizado" not in (versions[0].extracted_text or "")
        assert "Python actualizado" in (versions[1].extracted_text or "")
        assert versions[0].file_sha256 != versions[1].file_sha256

        with pytest.raises(DBAPIError):
            session.execute(
                text("UPDATE candidateresumeversion SET source = 'legacy' WHERE id = :version_id"),
                {"version_id": versions[0].id},
            )
            session.commit()
        session.rollback()


def test_cv_email_must_be_literal_and_unambiguous():
    assert trusted_email_from_cv("Correo: PERSONA@Example.com") == "persona@example.com"
    assert trusted_email_from_cv("Sin correo en el documento") is None
    assert trusted_email_from_cv("uno@example.com y referencia@example.com") is None
