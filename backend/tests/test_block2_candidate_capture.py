import io
import zipfile
from fastapi.testclient import TestClient
from fastapi import UploadFile

from app.main import app
from app.services.parsing_service import EXCLUDED_FIELDS, sanitize_text_for_model, validate_cv_upload

client = TestClient(app)


def test_excluded_fields_are_removed_before_model_call():
    raw = "Juan Perez, nacionalidad chilena, edad 31, experiencia en Python y PostgreSQL"
    filtered = sanitize_text_for_model(raw)

    assert "nacionalidad" not in filtered.lower()
    assert "edad" not in filtered.lower()
    assert all(term not in filtered.lower() for term in ["nacionalidad", "edad", "genero", "direccion"])
    assert "Python" in filtered
    assert "PostgreSQL" in filtered


def test_invalid_cv_type_returns_400():
    response = client.post(
        "/api/candidates/applications",
        files={"file": ("bad.txt", b"not-a-cv", "text/plain")},
        data={"full_name": "Ana", "email": "ana@example.com", "phone": "+56912345678"},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"] or "DOCX" in response.json()["detail"]


def test_large_cv_returns_400():
    huge = b"a" * (3 * 1024 * 1024 + 1)
    response = client.post(
        "/api/candidates/applications",
        files={"file": ("large.pdf", huge, "application/pdf")},
        data={"full_name": "Ana", "email": "ana@example.com", "phone": "+56912345678"},
    )
    assert response.status_code == 400
    assert "3 MB" in response.json()["detail"]


def test_individual_application_rejects_more_than_one_cv():
    response = client.post(
        "/api/candidates/applications",
        files=[
            ("file", ("first.pdf", b"%PDF-first", "application/pdf")),
            ("file", ("second.pdf", b"%PDF-second", "application/pdf")),
        ],
        data={"full_name": "Ana", "email": "ana@example.com"},
    )
    assert response.status_code == 400
    assert "un CV" in response.json()["detail"]


def test_renamed_non_pdf_is_rejected():
    response = client.post(
        "/api/candidates/applications",
        files={"file": ("renamed.pdf", b"plain text", "application/pdf")},
        data={"full_name": "Ana", "email": "ana@example.com"},
    )
    assert response.status_code == 400
    assert "no corresponde" in response.json()["detail"]


def test_word_docx_is_accepted_by_cv_validator():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as document:
        document.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>""",
        )
        document.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Experiencia profesional en Python</w:t></w:r></w:p></w:body></w:document>""",
        )
    upload = UploadFile(filename="curriculum.docx", file=io.BytesIO(buffer.getvalue()))
    _, extracted_text, safe_name = validate_cv_upload(upload)
    assert extracted_text == "Experiencia profesional en Python"
    assert safe_name == "curriculum.docx"


def test_excluded_fields_constant_is_defined():
    assert isinstance(EXCLUDED_FIELDS, list)
    assert "nacionalidad" in EXCLUDED_FIELDS
    assert "edad" in EXCLUDED_FIELDS
