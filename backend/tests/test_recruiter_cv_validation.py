import asyncio
import io
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

from app.api import candidates as candidates_api
from app.api import recruiter as recruiter_api
from app.api import sourcing as sourcing_api
from app.services import sourcing_prospect_service


NON_RESUME_TEXT = (
    "Informe académico de arquitectura empresarial preparado para una asignatura. "
    "El documento presenta introducción, marco teórico, análisis de resultados, conclusiones y bibliografía, "
    "pero no describe la trayectoria laboral ni las competencias de una persona candidata."
)


def _upload(filename: str = "documento.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(b"%PDF-test"))


class _SessionBeforePersistence:
    bind = None

    def __init__(self, candidate=None):
        self.candidate = candidate
        self.rollbacks = 0

    def get(self, _model, _record_id):
        return self.candidate

    def rollback(self):
        self.rollbacks += 1


def _return_non_resume(file, **_kwargs):
    return b"document", NON_RESUME_TEXT, file.filename or "documento.pdf"


def test_recruiter_mass_upload_rejects_non_resume_before_persisting(monkeypatch):
    monkeypatch.setattr(candidates_api, "validate_cv_upload", _return_non_resume)
    session = _SessionBeforePersistence()

    response = asyncio.run(
        recruiter_api.mass_upload_cvs(
            background_tasks=BackgroundTasks(),
            offer_id=7,
            origin_mode="authorized_application",
            authorization_confirmed=True,
            files=[_upload()],
            session=session,
            recruiter=SimpleNamespace(id=11),
        )
    )

    assert response["results"][0]["status"] == "error"
    assert "no parece ser un currículum" in response["results"][0]["detail"].lower()
    assert session.rollbacks == 1


def test_talent_bank_resume_update_rejects_non_resume(monkeypatch):
    monkeypatch.setattr(candidates_api, "validate_cv_upload", _return_non_resume)
    candidate = SimpleNamespace(archived_at=None, full_name="Ana Pérez", phone=None)
    session = _SessionBeforePersistence(candidate=candidate)

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            recruiter_api.update_talent_resume(
                candidate_id=3,
                file=_upload(),
                _single_cv=None,
                session=session,
                recruiter=SimpleNamespace(id=11),
            )
        )

    assert rejected.value.status_code == 400
    assert "no parece ser un currículum" in rejected.value.detail.lower()


def test_sourcing_preview_rejects_document_without_resume_content(monkeypatch):
    monkeypatch.setattr(sourcing_api, "validate_cv_upload", _return_non_resume)

    with pytest.raises(HTTPException) as rejected:
        sourcing_api.preview_prospect_import(
            file=_upload(),
            source="linkedin",
            job_offer_id=7,
            source_url=None,
            contact_notes=None,
            _single_cv=None,
            session=_SessionBeforePersistence(),
            recruiter=SimpleNamespace(id=11),
        )

    assert rejected.value.status_code == 400
    assert "no parece ser un currículum" in rejected.value.detail.lower()


def test_sourcing_bulk_accepts_up_to_twenty_profiles_without_persisting(monkeypatch):
    seen_filenames = []

    def fake_preview(**kwargs):
        filename = kwargs["file"].filename
        seen_filenames.append(filename)
        return {
            "preview": {"full_name": filename, "semantic_similarity": 80.0},
            "preview_token": f"token-{filename}",
            "expires_in_minutes": 30,
            "persisted": False,
        }

    monkeypatch.setattr(sourcing_api, "_preview_import_payload", fake_preview)
    files = [
        _upload(f"perfil-{index}{('.pdf', '.doc', '.docx')[index % 3]}")
        for index in range(20)
    ]

    response = sourcing_api.preview_prospect_import_bulk(
        files=files,
        source="linkedin",
        job_offer_id=7,
        source_url=None,
        contact_notes=None,
        session=_SessionBeforePersistence(),
        recruiter=SimpleNamespace(id=11),
    )

    assert response["total"] == 20
    assert response["ready"] == 20
    assert response["errors"] == 0
    assert len(seen_filenames) == 20
    assert all(result["persisted"] is False for result in response["results"])


def test_sourcing_bulk_keeps_valid_previews_when_one_file_fails(monkeypatch):
    def fake_preview(**kwargs):
        filename = kwargs["file"].filename
        if filename == "invalido.pdf":
            raise HTTPException(status_code=400, detail="El archivo no parece ser un currículum.")
        return {
            "preview": {"full_name": filename},
            "preview_token": f"token-{filename}",
            "expires_in_minutes": 30,
            "persisted": False,
        }

    monkeypatch.setattr(sourcing_api, "_preview_import_payload", fake_preview)
    response = sourcing_api.preview_prospect_import_bulk(
        files=[_upload("valido.docx"), _upload("invalido.pdf")],
        source="linkedin",
        job_offer_id=7,
        source_url=None,
        contact_notes=None,
        session=_SessionBeforePersistence(),
        recruiter=SimpleNamespace(id=11),
    )

    assert response["ready"] == 1
    assert response["errors"] == 1
    assert response["results"][0]["status"] == "ready"
    assert response["results"][1]["status"] == "error"


def test_sourcing_bulk_rejects_more_than_twenty_profiles():
    with pytest.raises(HTTPException) as rejected:
        sourcing_api.preview_prospect_import_bulk(
            files=[_upload(f"perfil-{index}.pdf") for index in range(21)],
            source="linkedin",
            job_offer_id=7,
            source_url=None,
            contact_notes=None,
            session=_SessionBeforePersistence(),
            recruiter=SimpleNamespace(id=11),
        )

    assert rejected.value.status_code == 400
    assert "1 y 20" in rejected.value.detail


def test_sourcing_conversion_rejects_document_without_resume_content(monkeypatch):
    monkeypatch.setattr(sourcing_prospect_service, "validate_cv_upload", _return_non_resume)

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            sourcing_prospect_service.convert_prospect_to_application(
                session=_SessionBeforePersistence(),
                prospect=SimpleNamespace(status="interesado"),
                file=_upload(),
                full_name="Ana Pérez",
                email="ana@example.com",
                phone=None,
                consent=True,
                authorization_channel="correo",
                authorization_at=datetime.now(),
                authorization_notes="Autorización verificable.",
            )
        )

    assert rejected.value.status_code == 400
    assert "no parece ser un currículum" in rejected.value.detail.lower()
