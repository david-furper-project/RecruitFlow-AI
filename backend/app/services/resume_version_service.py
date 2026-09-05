import hashlib
from pathlib import PurePosixPath
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import CandidateProfile, CandidateResumeVersion


RESUME_VERSION_SOURCES = {
    "pri",
    "application_link",
    "sourcing",
    "profile_update",
    "legacy",
}


def resume_checksum(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def find_resume_version_by_checksum(
    session: Session,
    checksum: str,
) -> Optional[CandidateResumeVersion]:
    return session.exec(
        select(CandidateResumeVersion).where(
            CandidateResumeVersion.file_sha256 == checksum
        )
    ).first()


def ensure_legacy_resume_snapshot(
    session: Session,
    candidate: CandidateProfile,
) -> Optional[CandidateResumeVersion]:
    """Preserve a pre-versioning CV before replacing the current profile."""
    existing = session.exec(
        select(CandidateResumeVersion)
        .where(CandidateResumeVersion.candidate_id == candidate.id)
        .order_by(CandidateResumeVersion.uploaded_at.desc())
    ).first()
    if existing is not None or not candidate.resume_url or candidate.resume_url == "pending":
        return existing

    filename = PurePosixPath(candidate.resume_url).name or "cv-historico"
    version = CandidateResumeVersion(
        candidate_id=candidate.id,
        resume_url=candidate.resume_url,
        original_filename=filename,
        file_sha256=None,
        source="legacy",
        extracted_text=candidate.extracted_text,
        tech_stack=candidate.tech_stack,
        years_of_experience=candidate.years_of_experience,
        courses_and_diplomas=candidate.courses_and_diplomas,
        career_summary=candidate.career_summary,
        uploaded_at=candidate.created_at,
    )
    session.add(version)
    session.flush()
    return version


def record_resume_version(
    session: Session,
    candidate: CandidateProfile,
    *,
    resume_url: str,
    original_filename: str,
    checksum: str,
    source: str,
    job_offer_id: Optional[int] = None,
    uploaded_by_user_id: Optional[int] = None,
) -> tuple[CandidateResumeVersion, bool]:
    if source not in RESUME_VERSION_SOURCES:
        raise HTTPException(status_code=400, detail="El origen de la versión del CV no es válido.")

    existing = find_resume_version_by_checksum(session, checksum)
    if existing is not None:
        if existing.candidate_id != candidate.id:
            raise HTTPException(
                status_code=409,
                detail="Este mismo archivo ya pertenece a otro perfil. Revisa la identidad antes de continuar.",
            )
        return existing, False

    version = CandidateResumeVersion(
        candidate_id=candidate.id,
        job_offer_id=job_offer_id,
        uploaded_by_user_id=uploaded_by_user_id,
        resume_url=resume_url,
        original_filename=original_filename,
        file_sha256=checksum,
        source=source,
        extracted_text=candidate.extracted_text,
        tech_stack=candidate.tech_stack,
        years_of_experience=candidate.years_of_experience,
        courses_and_diplomas=candidate.courses_and_diplomas,
        career_summary=candidate.career_summary,
    )
    session.add(version)
    session.flush()
    return version, True


def resume_versions_for_candidate(
    session: Session,
    candidate_id: int,
) -> list[CandidateResumeVersion]:
    return list(
        session.exec(
            select(CandidateResumeVersion)
            .where(CandidateResumeVersion.candidate_id == candidate_id)
            .order_by(CandidateResumeVersion.uploaded_at.desc(), CandidateResumeVersion.id.desc())
        ).all()
    )
