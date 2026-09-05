from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select, func
from typing import List, Dict, Any

from app.db.session import get_session
from app.models import Company, JobOffer, Application, User
from app.api.dependencies import require_recruiter
from app.services.report_pdf_service import build_executive_report_pdf

router = APIRouter()


def _companies_report(session: Session) -> List[Dict[str, Any]]:
    statement_offers = select(JobOffer.company_id, func.count(JobOffer.id).label("total_offers")).group_by(JobOffer.company_id)
    offers_result = session.exec(statement_offers).all()
    offers_map = {row.company_id: row.total_offers for row in offers_result}

    statement_active_offers = select(JobOffer.company_id, func.count(JobOffer.id).label("active_offers")).where(JobOffer.status == "open").group_by(JobOffer.company_id)
    active_offers_result = session.exec(statement_active_offers).all()
    active_offers_map = {row.company_id: row.active_offers for row in active_offers_result}

    companies = session.exec(select(Company)).all()
    return [
        {
            "id": company.id,
            "name": company.name,
            "total_offers": offers_map.get(company.id, 0),
            "active_offers": active_offers_map.get(company.id, 0),
        }
        for company in companies
    ]


def _offers_report(session: Session) -> List[Dict[str, Any]]:
    statement = select(
        JobOffer.id,
        JobOffer.title,
        Company.name.label("company_name"),
        func.count(Application.id).label("total_applications"),
        func.avg(Application.similarity_score).label("avg_similarity")
    ).join(Company, Company.id == JobOffer.company_id).outerjoin(
        Application,
        (Application.job_offer_id == JobOffer.id) & (Application.archived_at.is_(None)),
    ).group_by(JobOffer.id, JobOffer.title, Company.name)

    results = session.exec(statement).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "company_name": row.company_name,
            "total_applications": row.total_applications,
            "avg_similarity": round(row.avg_similarity, 2) if row.avg_similarity else None,
        }
        for row in results
    ]


@router.get("/companies")
def get_companies_report(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_recruiter)
) -> List[Dict[str, Any]]:
    return _companies_report(session)


@router.get("/offers")
def get_offers_report(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_recruiter)
) -> List[Dict[str, Any]]:
    return _offers_report(session)


@router.get("/executive.pdf")
def download_executive_report(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_recruiter),
) -> Response:
    generated_at = datetime.now()
    pdf = build_executive_report_pdf(
        _companies_report(session),
        _offers_report(session),
        generated_at=generated_at,
    )
    filename = quote(f"reporte-gerencial-pri-{generated_at.strftime('%Y-%m-%d')}.pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
