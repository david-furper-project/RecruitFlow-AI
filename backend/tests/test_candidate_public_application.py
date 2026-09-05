import io
import uuid
import zipfile

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.api import candidates as candidates_api
from app.db.session import get_session
from app.main import app
from app.models import Application, JobOffer
from app.services.consent_service import (
    CANDIDATE_APPLICATION_CONSENT_TEXT,
    CANDIDATE_APPLICATION_CONSENT_VERSION,
)
from app.services.parsing_service import normalize_extracted_text, validate_cv_upload
from app.services.resume_validation_service import validate_public_resume_document, validate_resume_document


PUBLIC_ID = "d4752db8-fadc-4da7-9fd8-47c89f7e6b34"


def _offer() -> JobOffer:
    return JobOffer(
        id=17,
        public_id=PUBLIC_ID,
        company_id=3,
        title="QA Engineer",
        description="Automatización de pruebas",
        requirements="Experiencia en QA",
        tech_stack="Python, Selenium",
        salary_range="Confidencial",
        experience_years=2,
        seniority="Semi Senior",
        status="open",
    )


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _OfferSession:
    def __init__(self, value=None):
        self.value = _offer() if value is None else value

    def exec(self, _statement):
        return _FakeResult(self.value)


@pytest.fixture
def public_client():
    app.dependency_overrides[get_session] = lambda: _OfferSession()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _minimal_form(**overrides):
    data = {
        "full_name": "Ana Pérez",
        "email": "ana@example.com",
        "consent": "true",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def _fake_file(filename="cv.pdf", content=b"not parsed", mime="application/pdf"):
    return {"file": (filename, content, mime)}


def _docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as document:
        document.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        document.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buffer.getvalue()


def test_public_application_rejects_missing_consent(public_client):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(consent=None),
        files=_fake_file(),
    )
    assert response.status_code == 400
    assert "autorizar" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    ("field_overrides", "expected"),
    [
        ({"full_name": "   "}, "nombre"),
        ({"email": "correo-invalido"}, "correo"),
        ({"salary_expectation": "mucho"}, "numérica"),
    ],
)
def test_public_application_rejects_invalid_fields(public_client, field_overrides, expected):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(**field_overrides),
        files=_fake_file(),
    )
    assert response.status_code == 400
    assert expected.lower() in response.json()["detail"].lower()


def test_salary_is_optional_and_consent_metadata_is_server_owned(public_client, monkeypatch):
    captured = {}

    async def fake_process(**kwargs):
        captured.update(kwargs)
        return {"application_created": False, "application_id": None}

    monkeypatch.setattr(candidates_api, "_process_single_application", fake_process)
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=_fake_file(),
    )

    assert response.status_code == 200
    assert captured["offer_id"] == 17
    assert captured["salary_expectation"] is None
    assert captured["consent_given_at"] is not None
    assert captured["consent_text_version"] == CANDIDATE_APPLICATION_CONSENT_VERSION
    assert captured["consent_text"] == CANDIDATE_APPLICATION_CONSENT_TEXT
    assert captured["cv_max_size_bytes"] == 3 * 1024 * 1024


def test_offer_id_cannot_be_injected_in_form(public_client):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(offer_id="999"),
        files=_fake_file(),
    )
    assert response.status_code == 400
    assert "exclusivamente" in response.json()["detail"]


@pytest.mark.parametrize("filename", ["cv.jpg", "cv.exe", "cv.txt"])
def test_public_application_rejects_disallowed_extensions(public_client, filename):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=_fake_file(filename=filename, mime="application/octet-stream"),
    )
    assert response.status_code == 400
    assert "formato inválido" in response.json()["detail"].lower()


def test_public_application_rejects_renamed_non_pdf(public_client):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=_fake_file(content=b"plain text"),
    )
    assert response.status_code == 400
    assert "no corresponde" in response.json()["detail"].lower()


def test_public_application_rejects_mime_mismatch(public_client):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=_fake_file(content=b"%PDF-1.4", mime="text/plain"),
    )
    assert response.status_code == 400
    assert "mime" in response.json()["detail"].lower()


def test_public_application_rejects_more_than_one_cv(public_client):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=[
            ("file", ("one.pdf", b"%PDF-1.4", "application/pdf")),
            ("file", ("two.pdf", b"%PDF-1.4", "application/pdf")),
        ],
    )
    assert response.status_code == 400
    assert "exactamente un cv" in response.json()["detail"].lower()


def test_public_application_enforces_three_megabyte_limit(public_client):
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=_fake_file(content=b"%PDF-" + b"x" * (3 * 1024 * 1024)),
    )
    assert response.status_code == 400
    assert "3 mb" in response.json()["detail"].lower()


def test_academic_assignment_is_rejected_as_not_a_resume(public_client, monkeypatch):
    def extraction_must_not_run(_text):
        raise AssertionError("La extracción de perfil no debe ejecutarse para un documento que no es CV")

    monkeypatch.setattr(candidates_api, "extract_candidate_profile", extraction_must_not_run)
    academic_assignment = (
        "Curso AINC421 Informe 3 ESTRUCTURA DE INFORME. La aplicación del UML. "
        "Diseño y construcción del producto de software de su proyecto de título. "
        "Diseño del software. Diseño de la base de datos. Diseño de la plataforma de operación. "
        "Mockups. Manual de usuario. Manual de instalación. Planes de pruebas."
    )
    response = public_client.post(
        f"/api/candidates/offers/{PUBLIC_ID}/applications",
        data=_minimal_form(),
        files=_fake_file(
            filename="entregable.docx",
            content=_docx_bytes(academic_assignment),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    )
    assert response.status_code == 400
    assert "no parece ser un currículum" in response.json()["detail"].lower()


def test_resume_identity_must_match_form_name_and_email():
    valid_resume = (
        "Ana Pérez ana@example.com +56 9 1111 2222. Perfil profesional: Ingeniera de software. "
        "Experiencia laboral: QA Automation 2020-2024. Habilidades técnicas: Python y Selenium."
    )
    result = validate_public_resume_document(valid_resume, "Ana Pérez", "ana@example.com")
    assert "experience" in result.detected_sections

    with pytest.raises(HTTPException) as wrong_name:
        validate_public_resume_document(valid_resume, "María López", "ana@example.com")
    assert "nombre" in str(wrong_name.value.detail).lower()

    with pytest.raises(HTTPException) as wrong_email:
        validate_public_resume_document(valid_resume, "Ana Pérez", "otra@example.com")
    assert "correo" in str(wrong_email.value.detail).lower()


def test_resume_without_literal_email_uses_validated_form_email():
    resume_without_email = (
        "Ana Pérez. Perfil profesional: Ingeniera de software. Experiencia laboral: QA 2020-2024. "
        "Habilidades técnicas: Python y Selenium. Educación académica: Ingeniería Informática."
    )
    result = validate_public_resume_document(resume_without_email, "Ana Pérez", "ana@example.com")
    assert result.document_emails == ()
    assert "experience" in result.detected_sections


def test_letter_spaced_pdf_text_is_repaired_and_validates_as_resume():
    def spaced(line: str) -> str:
        return "  ".join(" ".join(word) for word in line.split(" "))

    extracted = "\n".join(
        spaced(line)
        for line in (
            "DAVID FURNIEL PEREIRA",
            "Perfil Personal",
            "Especialista en automatización de QA con más de 8 años de experiencia.",
            "Formación",
            "Ingeniero en computación e informática 2026",
            "Experiencia Laboral",
            "Analista QA Inmetrics Junio 2020 - Actualidad",
            "Habilidades",
            "Java Python Selenium Playwright SQL",
            "davidfurper@gmail.com",
        )
    )

    readable = normalize_extracted_text(extracted)
    assert "DAVID FURNIEL PEREIRA" in readable
    assert "Experiencia Laboral" in readable
    assert "davidfurper@gmail.com" in readable

    result = validate_public_resume_document(readable, "David Furniel", "davidfurper@gmail.com")
    assert {"education", "experience", "skills"}.issubset(result.detected_sections)


def test_a_failed_document_does_not_affect_the_next_resume_validation():
    with pytest.raises(HTTPException):
        validate_public_resume_document(
            "Informe académico sobre diseño de software y pruebas.",
            "Ana Pérez",
            "ana@example.com",
        )

    valid_resume = (
        "Ana Pérez. Perfil profesional: Ingeniera de software. Experiencia laboral: QA 2020-2024. "
        "Habilidades técnicas: Python y Selenium. Educación académica: Ingeniería Informática."
    )
    result = validate_public_resume_document(valid_resume, "Ana Pérez", "ana@example.com")
    assert "experience" in result.detected_sections


def test_recruiter_resume_validation_checks_content_without_requiring_identity():
    result = validate_resume_document(
        "Perfil profesional de ingeniería de software. Experiencia laboral: desarrollo de APIs entre "
        "2020-2025. Habilidades técnicas: Python, FastAPI y PostgreSQL. Educación académica: Ingeniería."
    )
    assert {"education", "experience", "skills"}.issubset(result.detected_sections)
    assert result.document_emails == ()

    with pytest.raises(HTTPException) as invalid_document:
        validate_resume_document(
            "Informe académico de arquitectura empresarial. Este documento desarrolla un marco teórico "
            "y conclusiones para una asignatura universitaria, pero no describe una trayectoria laboral."
        )
    assert invalid_document.value.status_code == 400
    assert "no parece ser un currículum" in invalid_document.value.detail.lower()


def test_legacy_doc_requires_word_ole_signature_and_is_accepted():
    valid_doc = (
        bytes.fromhex("D0CF11E0A1B11AE1")
        + b"\x00" * 64
        + "WordDocument".encode("utf-16le")
        + b"\x00" * 32
        + "Experiencia profesional en Python".encode("utf-16le")
    )
    upload = UploadFile(
        filename="curriculum.doc",
        file=io.BytesIO(valid_doc),
        headers={"content-type": "application/msword"},
    )
    _, text, safe_name = validate_cv_upload(
        upload,
        allowed_extensions={".pdf", ".doc", ".docx"},
        max_size_bytes=3 * 1024 * 1024,
    )
    assert "Experiencia profesional en Python" in text
    assert safe_name == "curriculum.doc"


def test_offer_public_ids_are_opaque_and_consent_columns_exist():
    offer = JobOffer(
        company_id=1,
        title="Developer",
        description="Description",
        requirements="Requirements",
        tech_stack="Python",
        salary_range="Confidencial",
        experience_years=1,
        seniority="Junior",
    )
    uuid.UUID(offer.public_id)
    assert "consent_text_version" in Application.model_fields
    assert "consent_text" in Application.model_fields
