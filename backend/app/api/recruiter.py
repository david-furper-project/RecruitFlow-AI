from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.config import settings
from app.db.session import get_session
from app.models import CandidateProfile, User
from app.services.sourcing_service import is_linkedin_sourcing_enabled, upsert_candidate_from_linkedin

router = APIRouter()


class LinkedInScrapeRequest(BaseModel):
    url: str
    email: Optional[str] = None


@router.post("/scrape-linkedin")
def mock_scrape_linkedin(request: LinkedInScrapeRequest, session: Session = Depends(get_session)):
    if not is_linkedin_sourcing_enabled():
        raise HTTPException(status_code=503, detail="LinkedIn sourcing is disabled by configuration.")

    candidate = upsert_candidate_from_linkedin(session, request.url, request.email)
    return {
        "message": "Perfil de LinkedIn importado exitosamente.",
        "candidate_id": candidate.id,
        "full_name": candidate.full_name,
        "resume_url": candidate.resume_url,
    }


@router.post("/sourcing/linkedin")
def sourcing_linkedin(request: LinkedInScrapeRequest, session: Session = Depends(get_session)):
    return mock_scrape_linkedin(request, session)


@router.post("/save-candidate")
def save_scraped_candidate(request: LinkedInScrapeRequest, session: Session = Depends(get_session)):
    if request.url and "linkedin.com/in/" in request.url:
        return mock_scrape_linkedin(request, session)

    user = session.query(User).filter(User.email == request.email).first()
    if user is None:
        user = User(email=request.email, password_hash="mock_password", role="candidate")
        session.add(user)
        session.commit()
        session.refresh(user)

    candidate = session.query(CandidateProfile).filter(CandidateProfile.user_id == user.id).first()
    if candidate is not None:
        raise HTTPException(status_code=400, detail="El candidato ya existe en la base de datos.")

    new_candidate = CandidateProfile(
        user_id=user.id,
        full_name=request.url or "Candidato importado",
        resume_url="linkedin_import",
        extracted_text=request.url,
    )
    session.add(new_candidate)
    session.commit()
    return {"message": "Candidato guardado exitosamente.", "candidate_id": new_candidate.id}

