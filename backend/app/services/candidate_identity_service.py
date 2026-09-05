import hashlib
import re
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import CandidateProfile, User


EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+\-])",
    re.IGNORECASE,
)
INTERNAL_EMAIL_SUFFIXES = (
    "@candidate.internal.invalid",
    "@sourcing.internal.invalid",
)


def normalize_candidate_email(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    if not EMAIL_PATTERN.fullmatch(normalized):
        return None
    return normalized


def is_internal_candidate_email(value: Optional[str]) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.endswith(INTERNAL_EMAIL_SUFFIXES)


def trusted_email_from_cv(text: str) -> Optional[str]:
    """Extract identity only from literal CV text, never from an AI guess."""
    matches = {
        normalized
        for match in EMAIL_PATTERN.findall(text or "")
        if (normalized := normalize_candidate_email(match)) is not None
    }
    return next(iter(matches)) if len(matches) == 1 else None


def internal_email_for_cv(file_bytes: bytes) -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()[:32]
    return f"cv-{digest}@candidate.internal.invalid"


def find_candidate_by_email(
    session: Session,
    email: Optional[str],
) -> Optional[CandidateProfile]:
    normalized = normalize_candidate_email(email)
    if normalized is None:
        return None

    candidates = session.exec(
        select(CandidateProfile)
        .join(User, User.id == CandidateProfile.user_id)
        .where(
            CandidateProfile.archived_at.is_(None),
            (
                (func.lower(func.trim(CandidateProfile.contact_email)) == normalized)
                | (func.lower(func.trim(User.email)) == normalized)
            ),
        )
        .order_by(CandidateProfile.id.asc())
    ).all()
    if not candidates:
        return None

    # Prefer the profile whose account already owns the real address. This also
    # gives old duplicated development data one stable canonical profile.
    for candidate in candidates:
        user = session.get(User, candidate.user_id)
        if user and normalize_candidate_email(user.email) == normalized and not is_internal_candidate_email(user.email):
            return candidate
    return candidates[0]


def find_user_by_email(session: Session, email: str) -> Optional[User]:
    normalized = normalize_candidate_email(email)
    if normalized is None:
        return None
    return session.exec(
        select(User).where(func.lower(func.trim(User.email)) == normalized)
    ).first()
