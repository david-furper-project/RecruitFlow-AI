from datetime import datetime
from io import BytesIO

from pypdf import PdfReader

from app.services.report_pdf_service import build_executive_report_pdf


def test_executive_report_pdf_contains_summary_charts_and_offer_detail():
    companies = [
        {"id": 1, "name": "Banco Delta", "total_offers": 3, "active_offers": 2},
        {"id": 2, "name": "Tienda Amistosa", "total_offers": 1, "active_offers": 1},
    ]
    offers = [
        {
            "id": 1,
            "title": "QA Automation Engineer",
            "company_name": "Banco Delta",
            "total_applications": 8,
            "avg_similarity": 76.5,
        },
        {
            "id": 2,
            "title": "Desarrollador Java",
            "company_name": "Tienda Amistosa",
            "total_applications": 3,
            "avg_similarity": 68.0,
        },
    ]

    pdf = build_executive_report_pdf(
        companies,
        offers,
        generated_at=datetime(2026, 9, 2, 10, 30),
    )

    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Reporte gerencial de reclutamiento" in text
    assert "QA Automation Engineer" in text
    assert "76.5%" in text


def test_executive_report_pdf_supports_an_empty_database():
    pdf = build_executive_report_pdf([], [], generated_at=datetime(2026, 9, 2, 10, 30))

    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "No hay vacantes registradas" in text
    assert "0.0%" in text
