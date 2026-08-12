import io
from fastapi.testclient import TestClient

from app.main import app
from app.services.parsing_service import EXCLUDED_FIELDS, sanitize_text_for_model

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
    huge = b"a" * (6 * 1024 * 1024)
    response = client.post(
        "/api/candidates/applications",
        files={"file": ("large.pdf", huge, "application/pdf")},
        data={"full_name": "Ana", "email": "ana@example.com", "phone": "+56912345678"},
    )
    assert response.status_code == 400
    assert "5 MB" in response.json()["detail"]


def test_excluded_fields_constant_is_defined():
    assert isinstance(EXCLUDED_FIELDS, list)
    assert "nacionalidad" in EXCLUDED_FIELDS
    assert "edad" in EXCLUDED_FIELDS
