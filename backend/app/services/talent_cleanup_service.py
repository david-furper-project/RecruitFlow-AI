from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Session, select

from app.models import (
    Application,
    CandidateProfile,
    CandidateResumeVersion,
    PrivacyRequestLog,
    SourcingProspect,
    User,
)


@dataclass(frozen=True)
class TalentCleanupResult:
    archived_candidates: int
    archived_applications: int
    deleted_sourcing_prospects: int
    deleted_resume_versions: int
    privacy_logs_created: int
    resume_urls: tuple[str, ...]


def archive_operational_talent_data(
    session: Session,
    *,
    requested_by_user_id: Optional[int],
    archived_at: Optional[datetime] = None,
) -> TalentCleanupResult:
    """Remove talent data from operational use while preserving required audits.

    Evaluation, Decision and Notification are intentionally untouched. Their
    Application rows remain as immutable audit anchors, but both the Application
    and its anonymized CandidateProfile are hidden through ``archived_at``.
    """
    cleanup_time = archived_at or datetime.utcnow()
    candidates = list(
        session.exec(
            select(CandidateProfile)
            .where(CandidateProfile.archived_at.is_(None))
            .order_by(CandidateProfile.id.asc())
        ).all()
    )
    candidate_ids = [candidate.id for candidate in candidates if candidate.id is not None]

    candidate_users: dict[int, User] = {}
    for candidate in candidates:
        user = session.get(User, candidate.user_id)
        if user is None:
            raise RuntimeError(f"El perfil {candidate.id} no tiene usuario asociado.")
        if user.role != "candidate":
            raise RuntimeError(
                f"El perfil {candidate.id} apunta al usuario interno {user.id}; se canceló la limpieza."
            )
        candidate_users[candidate.id] = user

    applications = []
    resume_versions = []
    if candidate_ids:
        applications = list(
            session.exec(
                select(Application).where(
                    Application.candidate_id.in_(candidate_ids),
                    Application.archived_at.is_(None),
                )
            ).all()
        )
        resume_versions = list(
            session.exec(
                select(CandidateResumeVersion).where(
                    CandidateResumeVersion.candidate_id.in_(candidate_ids)
                )
            ).all()
        )

    sourcing_prospects = list(session.exec(select(SourcingProspect)).all())
    resume_urls = {
        version.resume_url
        for version in resume_versions
        if version.resume_url
    }
    resume_urls.update(
        candidate.resume_url
        for candidate in candidates
        if candidate.resume_url and candidate.resume_url not in {"pending", "linkedin_import"}
    )

    try:
        for application in applications:
            application.archived_at = cleanup_time
            session.add(application)
            session.add(
                PrivacyRequestLog(
                    application_id=application.id,
                    requested_by_user_id=requested_by_user_id,
                    action="administrative_talent_cleanup",
                    requested_at=cleanup_time,
                    closed_at=cleanup_time,
                    notes=(
                        "Limpieza operativa confirmada: perfil y postulación archivados; "
                        "evaluaciones, decisiones y notificaciones conservadas por auditoría."
                    ),
                )
            )

        for prospect in sourcing_prospects:
            session.delete(prospect)
        for version in resume_versions:
            session.delete(version)

        for candidate in candidates:
            user = candidate_users[candidate.id]
            anonymous_suffix = uuid4().hex[:12]
            user.email = (
                f"archived-candidate-{candidate.id}-{user.id}-{anonymous_suffix}"
                "@candidate.internal.invalid"
            )
            user.password_hash = f"!archived-{uuid4().hex}"
            user.is_active = False
            user.last_login_at = None
            user.failed_attempts = 0
            user.locked_until = cleanup_time
            session.add(user)

            candidate.full_name = f"Perfil archivado {candidate.id}"
            candidate.resume_url = None
            candidate.extracted_text = None
            candidate.phone = None
            candidate.rut = None
            candidate.tech_stack = None
            candidate.years_of_experience = None
            candidate.courses_and_diplomas = None
            candidate.career_summary = None
            candidate.salary_expectation = None
            candidate.professional_headline = None
            candidate.source = None
            candidate.source_url = None
            candidate.contact_status = "archived"
            candidate.contact_email = None
            candidate.invited_job_offer_id = None
            candidate.invitation_expires_at = None
            candidate.embedding = None
            candidate.archived_at = cleanup_time
            session.add(candidate)

        session.commit()
    except Exception:
        session.rollback()
        raise

    return TalentCleanupResult(
        archived_candidates=len(candidates),
        archived_applications=len(applications),
        deleted_sourcing_prospects=len(sourcing_prospects),
        deleted_resume_versions=len(resume_versions),
        privacy_logs_created=len(applications),
        resume_urls=tuple(sorted(resume_urls)),
    )
