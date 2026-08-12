import re
import uuid
from typing import Optional

from sqlmodel import Session

from app.core.config import settings
from app.models import CandidateProfile, User
from app.services.ai_service import generate_embedding
from app.services.parsing_service import extract_candidate_profile, validate_and_merge_profile


class LinkedInProfileData:
    def __init__(self, full_name: str, email: str, summary: str, extracted_text: str):
        self.full_name = full_name
        self.email = email
        self.summary = summary
        self.extracted_text = extracted_text


def is_linkedin_sourcing_enabled() -> bool:
    return bool(getattr(settings, "LINKEDIN_SOURCING_ENABLED", True))


def fetch_linkedin_profile_data(url: str) -> LinkedInProfileData:
    if not is_linkedin_sourcing_enabled():
        raise RuntimeError("LinkedIn sourcing is disabled by configuration.")
    if "linkedin.com/in/" not in url:
        raise ValueError("URL de LinkedIn no válida. Debe contener 'linkedin.com/in/'.")

    profile_name = "Alex Mock Developer"
    email = f"linkedin_{uuid.uuid4().hex[:8]}@mock.local"
    summary = "Ingeniero de Software Senior con experiencia en backend Python, APIs y bases de datos PostgreSQL."
    extracted_text = (
        "Alex Mock Developer. Ingeniero de Software Senior con experiencia en FastAPI, Python, "
        "SQL, PostgreSQL, React y AWS. Especialista en backend y APIs."
    )
    return LinkedInProfileData(profile_name, email, summary, extracted_text)


def upsert_candidate_from_linkedin(session: Session, url: str, email: Optional[str] = None) -> CandidateProfile:
    profile = fetch_linkedin_profile_data(url)
    user_email = email or profile.email
    user = session.query(User).filter(User.email == user_email).first()
    if not user:
        user = User(email=user_email, role="candidate", password_hash="mock_linkedin_password")
        session.add(user)
        session.commit()
        session.refresh(user)

    candidate = session.query(CandidateProfile).filter(CandidateProfile.user_id == user.id).first()
    if candidate is None:
        candidate = CandidateProfile(user_id=user.id, full_name=profile.full_name, resume_url="linkedin_import")
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

    extracted_profile = extract_candidate_profile(profile.extracted_text)
    merged = validate_and_merge_profile(extracted_profile, {
        "full_name": profile.full_name,
        "career_summary": profile.summary,
        "tech_stack": "Python, PostgreSQL, FastAPI, React",
    })

    candidate.full_name = merged.get("full_name") or profile.full_name
    candidate.extracted_text = profile.extracted_text
    candidate.resume_url = "linkedin_import"
    candidate.tech_stack = merged.get("tech_stack")
    candidate.years_of_experience = merged.get("years_of_experience")
    candidate.courses_and_diplomas = merged.get("courses_and_diplomas")
    candidate.career_summary = merged.get("career_summary") or profile.summary
    candidate.embedding = generate_embedding(profile.extracted_text)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate
