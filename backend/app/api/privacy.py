from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Application, CandidateProfile, PrivacyRequestLog, User
from app.services.candidate_identity_service import is_internal_candidate_email
from app.services.resume_version_service import resume_versions_for_candidate
from app.services.storage_service import delete_cv_file

router = APIRouter()


class PrivacyConsentRequest(BaseModel):
    email: str
    consent: bool


@router.post("/candidates/{candidate_id}/consent")
def save_consent(candidate_id: int, payload: PrivacyConsentRequest, session: Session = Depends(get_session)):
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not payload.consent:
        raise HTTPException(status_code=400, detail="Consentimiento obligatorio para la postulación")

    application = session.exec(select(Application).where(Application.candidate_id == candidate_id)).first()
    if application is not None:
        application.consent_given_at = datetime.utcnow()
        session.add(application)

    session.commit()
    return {"candidate_id": candidate_id, "consent_given_at": application.consent_given_at if application else None}


@router.get("/candidates/{candidate_id}/privacy")
def get_candidate_privacy(candidate_id: int, session: Session = Depends(get_session)):
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {
        "candidate_id": candidate_id,
        "full_name": candidate.full_name,
        "resume_url": candidate.resume_url,
        "email": candidate.user.email if candidate.user and not is_internal_candidate_email(candidate.user.email) else None,
    }


@router.patch("/candidates/{candidate_id}/privacy")
def update_candidate_privacy(candidate_id: int, payload: dict, session: Session = Depends(get_session)):
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if "phone" in payload:
        candidate.phone = payload["phone"]
    if "career_summary" in payload:
        candidate.career_summary = payload["career_summary"]
    if "tech_stack" in payload:
        candidate.tech_stack = payload["tech_stack"]

    session.add(candidate)
    session.commit()
    return {"message": "Datos personales actualizados", "candidate_id": candidate_id}


@router.delete("/candidates/{candidate_id}/privacy")
async def delete_candidate_privacy(candidate_id: int, session: Session = Depends(get_session)):
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # A privacy deletion removes every stored CV version, not only the current
    # pointer. History is retained for normal updates but never defeats a valid
    # right-to-erasure request.
    resume_urls = {
        version.resume_url
        for version in resume_versions_for_candidate(session, candidate.id)
        if version.resume_url
    }
    if candidate.resume_url:
        resume_urls.add(candidate.resume_url)
    for resume_url in resume_urls:
        await delete_cv_file(resume_url)

    user = session.get(User, candidate.user_id)
    if user is not None:
        session.delete(user)

    session.delete(candidate)
    session.commit()
    return {"message": "Supresión realizada", "candidate_id": candidate_id}


@router.post("/privacy-requests")
def create_privacy_request(payload: dict, session: Session = Depends(get_session)):
    application_id = payload.get("application_id")
    user_id = payload.get("user_id")
    action = payload.get("action")
    notes = payload.get("notes")
    if not application_id or not action:
        raise HTTPException(status_code=400, detail="application_id y action son obligatorios")

    log = PrivacyRequestLog(
        application_id=application_id,
        requested_by_user_id=user_id,
        action=action,
        requested_at=datetime.utcnow(),
        notes=notes,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return {"message": "Solicitud registrada", "request_id": log.id}
