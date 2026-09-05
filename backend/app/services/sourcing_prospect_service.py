import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlmodel import Session, select

from app.core.auth import create_access_token, verify_token
from app.models import (
    Application,
    CandidateProfile,
    Evaluation,
    JobOffer,
    PipelineStage,
    SourcingProspect,
    User,
)
from app.services.ai_service import generate_embedding
from app.services.candidate_identity_service import (
    find_candidate_by_email,
    normalize_candidate_email,
)
from app.services.matching_service import (
    affinity_explanation,
    affinity_percentage,
    candidate_profile_text,
    job_offer_text,
    structured_profile_text,
)
from app.services.parsing_service import (
    EXCLUDED_FIELDS,
    extract_candidate_profile,
    sanitize_text_for_model,
    validate_and_merge_profile,
    validate_cv_upload,
)
from app.services.resume_version_service import (
    ensure_legacy_resume_snapshot,
    find_resume_version_by_checksum,
    record_resume_version,
    resume_checksum,
)
from app.services.resume_validation_service import validate_resume_document
from app.services.storage_service import delete_cv_file, upload_cv_to_storage


SOURCING_SOURCES = {"linkedin", "computrabajo", "laborum", "referido", "otro"}
SOURCING_STATUSES = {
    "identificado",
    "contactado",
    "interesado",
    "invitado",
    "no_interesado",
    "sin_respuesta",
    "convertido",
}
CONTACT_CHANNELS = {"linkedin", "correo", "telefono", "otro"}
RESPONSE_STATUSES = {"interesado", "no_interesado", "sin_respuesta"}


def utcnow() -> datetime:
    return datetime.utcnow()


def normalize_source_url(source: str, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip().rstrip(".,;)")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("La URL de origen no es válida.")
    host = parsed.hostname.lower()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    if source == "linkedin":
        if host not in {"linkedin.com", "www.linkedin.com"} or not re.fullmatch(
            r"/in/[^/]+", path, flags=re.IGNORECASE
        ):
            raise ValueError("El PDF debe contener una URL pública linkedin.com/in/... válida.")
        host = "www.linkedin.com"
    return urlunparse(("https", host, path, "", parsed.query, ""))


def find_profile_url(text_value: str, source: str, provided_url: Optional[str] = None) -> Optional[str]:
    if provided_url:
        return normalize_source_url(source, provided_url)
    urls = re.findall(r"(?:https?://|www\.)[^\s<>\]\[\"']+", text_value or "", flags=re.IGNORECASE)
    if source == "linkedin":
        urls = [url for url in urls if "linkedin.com/in/" in url.lower()]
    return normalize_source_url(source, urls[0]) if urls else None


def structure_sourcing_document(extracted_text: str) -> dict:
    professional_text = sanitize_text_for_model(extracted_text)
    if len(professional_text) < 40:
        raise ValueError("El PDF no contiene suficiente información profesional extraíble.")
    try:
        structured = extract_candidate_profile(professional_text, strict=True)
    except Exception as exc:
        raise ValueError(f"Gemini no pudo estructurar el perfil: {exc}") from exc
    return {
        "full_name": structured.get("full_name"),
        "headline": structured.get("headline"),
        "experience": structured.get("experience"),
        "years_of_experience": structured.get("years_of_experience"),
        "education": structured.get("education") or structured.get("courses_and_diplomas"),
        "skills": structured.get("tech_stack"),
        "summary": structured.get("career_summary"),
        "contact_email": structured.get("email"),
        "contact_phone": structured.get("phone"),
        "professional_text": professional_text[:20000],
    }


def professional_embedding_text(structured: dict) -> str:
    # Nunca incluye datos de contacto, RUT ni atributos excluidos del scoring.
    return structured_profile_text(structured)


def preview_affinity(session: Session, structured: dict, offer_id: int) -> tuple[float, str]:
    offer = session.get(JobOffer, offer_id)
    if offer is None:
        raise ValueError("La vacante no existe.")
    candidate_vector = generate_embedding(professional_embedding_text(structured))
    offer_vector = generate_embedding(job_offer_text(offer))
    percentage = affinity_percentage(candidate_vector, offer_vector)
    return percentage, _match_explanation(percentage)


def _match_explanation(percentage: float) -> str:
    return affinity_explanation(percentage)


def create_preview_token(
    *,
    structured: dict,
    source: str,
    source_url: Optional[str],
    job_offer_id: int,
    created_by_user_id: int,
    contact_notes: Optional[str],
    semantic_similarity: Optional[float] = None,
    match_explanation: Optional[str] = None,
) -> str:
    return create_access_token(
        {
            "type": "sourcing_pdf_preview",
            "profile": structured,
            "source": source,
            "source_url": source_url,
            "job_offer_id": job_offer_id,
            "created_by_user_id": created_by_user_id,
            "contact_notes": contact_notes,
            "semantic_similarity": semantic_similarity,
            "match_explanation": match_explanation,
        },
        expires_delta=timedelta(minutes=30),
    )


def decode_preview_token(preview_token: str) -> dict:
    payload = verify_token(preview_token)
    if payload.get("type") != "sourcing_pdf_preview" or not isinstance(payload.get("profile"), dict):
        raise HTTPException(status_code=400, detail="La vista previa de sourcing no es válida.")
    return payload


def _internal_candidate_email(source: str, source_url: Optional[str], structured: dict) -> str:
    stable_key = source_url or professional_embedding_text(structured)
    digest = hashlib.sha256(f"{source}:{stable_key}".encode("utf-8")).hexdigest()[:28]
    return f"prospect-{digest}@sourcing.internal.invalid"


def _find_existing_candidate(session: Session, source_url: Optional[str], structured: dict) -> Optional[CandidateProfile]:
    if source_url:
        prospect = session.exec(
            select(SourcingProspect).where(SourcingProspect.source_url == source_url)
        ).first()
        if prospect:
            candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
            if candidate is not None and candidate.archived_at is None:
                return candidate
        # Compatibilidad con perfiles importados por el flujo anterior.
        candidate = session.exec(
            select(CandidateProfile).where(
                CandidateProfile.source_url == source_url,
                CandidateProfile.archived_at.is_(None),
            )
        ).first()
        if candidate:
            return candidate
    contact_email = normalize_candidate_email(structured.get("contact_email"))
    if contact_email:
        candidate = find_candidate_by_email(session, contact_email)
        if candidate:
            return candidate
    return None


def _pgvector_similarity(session: Session, candidate: CandidateProfile, offer: JobOffer) -> float:
    if candidate.embedding is None:
        raise ValueError("El perfil no tiene embedding profesional.")
    if offer.embedding is None:
        offer.embedding = generate_embedding(job_offer_text(offer))
        session.add(offer)
        session.flush()
    statement = select(
        (1 - CandidateProfile.embedding.cosine_distance(offer.embedding)).label("similarity")
    ).where(CandidateProfile.id == candidate.id)
    similarity = session.exec(statement).one()
    return round(max(0.0, min(1.0, float(similarity or 0.0))) * 100, 2)


def confirm_prospect_import(session: Session, preview_token: str) -> tuple[SourcingProspect, CandidateProfile]:
    payload = decode_preview_token(preview_token)
    source = payload.get("source")
    if source not in SOURCING_SOURCES:
        raise HTTPException(status_code=400, detail="Origen de sourcing inválido.")
    structured = payload["profile"]
    offer = session.get(JobOffer, payload.get("job_offer_id"))
    creator = session.get(User, payload.get("created_by_user_id"))
    if offer is None:
        raise HTTPException(status_code=404, detail="Vacante no encontrada.")
    if creator is None or creator.role not in {"recruiter", "admin"}:
        raise HTTPException(status_code=400, detail="El usuario creador no es un reclutador válido.")

    source_url = payload.get("source_url")
    contact_email = normalize_candidate_email(structured.get("contact_email"))
    if contact_email and session.bind and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:identity_email))"),
            {"identity_email": contact_email},
        )
    candidate = _find_existing_candidate(session, source_url, structured)
    if candidate is None or candidate.archived_at is not None:
        internal_email = _internal_candidate_email(source, source_url, structured)
        user = session.exec(select(User).where(User.email == internal_email)).first()
        if user is None:
            user = User(email=internal_email, role="candidate", password_hash="sourcing-invitation-only")
            session.add(user)
            session.flush()
        candidate = CandidateProfile(
            user_id=user.id,
            full_name=structured.get("full_name") or "Perfil profesional sin nombre",
            resume_url=None,
            extracted_text=structured.get("professional_text"),
            phone=structured.get("contact_phone"),
            tech_stack=structured.get("skills"),
            years_of_experience=structured.get("years_of_experience"),
            courses_and_diplomas=structured.get("education"),
            career_summary=structured.get("summary"),
            professional_headline=structured.get("headline"),
            source=source,
            source_url=source_url,
            contact_email=normalize_candidate_email(structured.get("contact_email")),
            embedding=generate_embedding(professional_embedding_text(structured)),
        )
        session.add(candidate)
        session.flush()
    else:
        candidate.contact_email = candidate.contact_email or normalize_candidate_email(structured.get("contact_email"))
        candidate.phone = candidate.phone or structured.get("contact_phone")
        candidate.source = candidate.source or source
        candidate.source_url = candidate.source_url or source_url
        if candidate.embedding is None:
            candidate.embedding = generate_embedding(professional_embedding_text(structured))
        session.add(candidate)
        session.flush()

    existing = session.exec(
        select(SourcingProspect).where(
            SourcingProspect.candidate_profile_id == candidate.id,
            SourcingProspect.job_offer_id == offer.id,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Este perfil ya existe como prospecto para la vacante seleccionada.",
        )

    token_similarity = payload.get("semantic_similarity")
    similarity = (
        round(float(token_similarity), 2)
        if token_similarity is not None
        else _pgvector_similarity(session, candidate, offer)
    )
    prospect = SourcingProspect(
        candidate_profile_id=candidate.id,
        job_offer_id=offer.id,
        created_by_user_id=creator.id,
        source=source,
        source_url=source_url,
        status="identificado",
        semantic_similarity=similarity,
        match_explanation=payload.get("match_explanation") or _match_explanation(similarity),
        contact_notes=payload.get("contact_notes"),
    )
    session.add(prospect)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(prospect)
    session.refresh(candidate)
    return prospect, candidate


def invitation_token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_invitation(prospect: SourcingProspect, expires_in_days: int = 7) -> tuple[str, datetime]:
    expires_at = utcnow() + timedelta(days=expires_in_days)
    token = create_access_token(
        {"type": "sourcing_prospect_invitation", "prospect_id": prospect.id},
        expires_delta=timedelta(days=expires_in_days),
    )
    prospect.invitation_token_hash = invitation_token_hash(token)
    prospect.invitation_expires_at = expires_at
    prospect.invited_at = utcnow()
    prospect.updated_at = utcnow()
    prospect.status = "invitado"
    return token, expires_at


def invitation_context(session: Session, raw_token: str) -> SourcingProspect:
    token_hash = invitation_token_hash(raw_token)
    prospect = session.exec(
        select(SourcingProspect).where(SourcingProspect.invitation_token_hash == token_hash)
    ).first()
    if prospect is None:
        raise HTTPException(status_code=404, detail="Invitación no encontrada.")
    if prospect.status == "convertido":
        raise HTTPException(status_code=409, detail="Esta invitación ya fue utilizada.")
    if prospect.status != "invitado" or not prospect.invitation_expires_at:
        raise HTTPException(status_code=400, detail="La invitación no está activa.")
    if prospect.invitation_expires_at < utcnow():
        raise HTTPException(status_code=410, detail="La invitación venció.")
    payload = verify_token(raw_token)
    if payload.get("type") != "sourcing_prospect_invitation" or payload.get("prospect_id") != prospect.id:
        raise HTTPException(status_code=400, detail="Invitación inválida.")
    return prospect


async def convert_prospect_to_application(
    *,
    session: Session,
    prospect: SourcingProspect,
    file: UploadFile,
    full_name: str,
    email: str,
    phone: Optional[str],
    consent: bool,
    authorization_channel: str,
    authorization_at: datetime,
    authorization_notes: Optional[str],
) -> Application:
    if prospect.status not in {"interesado", "invitado"}:
        raise HTTPException(status_code=409, detail="El prospecto aún no aceptó continuar con la postulación.")
    if not consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento explícito para crear la postulación.")
    if not authorization_channel.strip() or authorization_at is None:
        raise HTTPException(status_code=400, detail="Falta registrar el canal y fecha de autorización.")
    if not (authorization_notes or "").strip():
        raise HTTPException(status_code=400, detail="Se requiere una nota o referencia de respaldo de la autorización.")
    normalized_email = normalize_candidate_email(email)
    if normalized_email is None:
        raise HTTPException(status_code=400, detail="Se requiere un correo válido del candidato.")

    file_bytes, extracted_text, safe_name = validate_cv_upload(file)
    validate_resume_document(extracted_text)
    checksum = resume_checksum(file_bytes)
    filtered_text = sanitize_text_for_model(extracted_text)
    profile_data = extract_candidate_profile(filtered_text)
    candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Perfil de candidato no encontrado.")
    user = session.get(User, candidate.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario del candidato no encontrado.")
    canonical_candidate = find_candidate_by_email(session, normalized_email)
    if canonical_candidate is not None and canonical_candidate.id != candidate.id:
        duplicate_prospect = session.exec(
            select(SourcingProspect).where(
                SourcingProspect.candidate_profile_id == canonical_candidate.id,
                SourcingProspect.job_offer_id == prospect.job_offer_id,
            )
        ).first()
        if duplicate_prospect is not None:
            raise HTTPException(
                status_code=409,
                detail="Este candidato ya tiene un registro de sourcing para la vacante.",
            )
        prospect.candidate_profile_id = canonical_candidate.id
        candidate = canonical_candidate
        user = session.get(User, candidate.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuario del candidato no encontrado.")

    checksum_version = find_resume_version_by_checksum(session, checksum)
    if checksum_version is not None and checksum_version.candidate_id != candidate.id:
        raise HTTPException(
            status_code=409,
            detail="El CV y el correo corresponden a perfiles distintos. Revisa la identidad antes de continuar.",
        )

    merged = validate_and_merge_profile(
        profile_data,
        {"full_name": full_name, "phone": phone},
    )
    uploaded_resume_url: Optional[str] = None
    try:
        # Bloqueo por candidato-vacante: todas las conversiones pasan por este
        # punto y no pueden crear dos Applications concurrentes.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:candidate_id, :job_offer_id)"),
            {"candidate_id": candidate.id, "job_offer_id": prospect.job_offer_id},
        )
        application = session.exec(
            select(Application).where(
                Application.candidate_id == candidate.id,
                Application.job_offer_id == prospect.job_offer_id,
            )
        ).first()

        user.email = normalized_email
        candidate.contact_email = normalized_email
        if checksum_version is None:
            ensure_legacy_resume_snapshot(session, candidate)
            candidate.full_name = merged.get("full_name") or candidate.full_name
            candidate.phone = merged.get("phone") or candidate.phone
            candidate.extracted_text = extracted_text
            candidate.tech_stack = merged.get("tech_stack") or candidate.tech_stack
            candidate.years_of_experience = (
                merged.get("years_of_experience")
                if merged.get("years_of_experience") is not None
                else candidate.years_of_experience
            )
            candidate.courses_and_diplomas = merged.get("courses_and_diplomas") or candidate.courses_and_diplomas
            candidate.career_summary = merged.get("career_summary") or candidate.career_summary
            candidate.embedding = generate_embedding(candidate_profile_text(candidate))
            uploaded_resume_url = await upload_cv_to_storage(candidate.id, safe_name, file_bytes)
            candidate.resume_url = uploaded_resume_url
            record_resume_version(
                session,
                candidate,
                resume_url=uploaded_resume_url,
                original_filename=safe_name,
                checksum=checksum,
                source="sourcing",
                job_offer_id=prospect.job_offer_id,
                uploaded_by_user_id=prospect.created_by_user_id,
            )
        session.add(user)
        session.add(candidate)

        if application is None:
            first_stage = session.exec(
                select(PipelineStage)
                .where(PipelineStage.job_offer_id == prospect.job_offer_id)
                .order_by(PipelineStage.order_index.asc())
            ).first()
            application = Application(
                candidate_id=candidate.id,
                job_offer_id=prospect.job_offer_id,
                status="pending",
                current_stage_id=first_stage.id if first_stage else None,
                consent_given_at=utcnow(),
                origin="sourcing",
            )
            session.add(application)
            session.flush()
        elif application.consent_given_at is None:
            application.consent_given_at = utcnow()
            session.add(application)

        prospect.status = "convertido"
        prospect.converted_at = utcnow()
        prospect.updated_at = utcnow()
        prospect.authorization_channel = authorization_channel.strip()
        prospect.authorization_at = authorization_at
        prospect.authorization_notes = authorization_notes
        prospect.invitation_token_hash = None
        session.add(prospect)
        session.commit()
        session.refresh(application)
        return application
    except Exception:
        session.rollback()
        if uploaded_resume_url:
            await delete_cv_file(uploaded_resume_url)
        raise


def serialize_prospect(session: Session, prospect: SourcingProspect) -> dict:
    candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
    user = session.get(User, candidate.user_id) if candidate else None
    
    application = session.exec(
        select(Application).where(
            Application.candidate_id == prospect.candidate_profile_id,
            Application.job_offer_id == prospect.job_offer_id,
        )
    ).first()
    # Legacy versions could duplicate the same uploaded document under another
    # CandidateProfile. Reconcile only an exact, unique professional-document
    # fingerprint; never infer identity from a name alone.
    if application is None and candidate is not None and candidate.extracted_text:
        source_fingerprint = hashlib.sha256(
            candidate_profile_text(candidate).encode("utf-8")
        ).digest()
        legacy_matches = []
        candidate_applications = session.exec(
            select(Application, CandidateProfile)
            .join(CandidateProfile, CandidateProfile.id == Application.candidate_id)
            .where(
                Application.job_offer_id == prospect.job_offer_id,
                Application.archived_at.is_(None),
                CandidateProfile.archived_at.is_(None),
            )
        ).all()
        for possible_application, possible_candidate in candidate_applications:
            if possible_candidate.id == candidate.id or not possible_candidate.extracted_text:
                continue
            possible_fingerprint = hashlib.sha256(
                candidate_profile_text(possible_candidate).encode("utf-8")
            ).digest()
            if possible_fingerprint == source_fingerprint:
                legacy_matches.append(possible_application)
        if len(legacy_matches) == 1:
            application = legacy_matches[0]
    latest_evaluation = None
    if application is not None:
        latest_evaluation = session.exec(
            select(Evaluation)
            .where(Evaluation.application_id == application.id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
        ).first()
    effective_similarity = (
        round(float(application.similarity_score) * 100, 2)
        if application is not None and application.similarity_score is not None
        else prospect.semantic_similarity
    )
    effective_explanation = (
        latest_evaluation.explanation
        if latest_evaluation is not None
        else prospect.match_explanation
    )
    return {
        "id": prospect.id,
        "candidate_profile_id": prospect.candidate_profile_id,
        "job_offer_id": prospect.job_offer_id,
        "created_by_user_id": prospect.created_by_user_id,
        "source": prospect.source,
        "source_url": prospect.source_url,
        "status": prospect.status,
        "semantic_similarity": effective_similarity,
        "match_explanation": effective_explanation,
        "contact_channel": prospect.contact_channel,
        "contact_notes": prospect.contact_notes,
        "suggested_email": (user.email if user and not user.email.endswith("@sourcing.internal.invalid") else candidate.contact_email) if candidate else None,
        "suggested_phone": candidate.phone if candidate else None,
        "created_at": prospect.created_at.isoformat() if prospect.created_at else None,
        "contacted_at": prospect.contacted_at.isoformat() if prospect.contacted_at else None,
        "responded_at": prospect.responded_at.isoformat() if prospect.responded_at else None,
        "invited_at": prospect.invited_at.isoformat() if prospect.invited_at else None,
        "converted_at": prospect.converted_at.isoformat() if prospect.converted_at else None,
        "updated_at": prospect.updated_at.isoformat() if prospect.updated_at else None,
        "candidate": {
            "id": candidate.id,
            "full_name": candidate.full_name,
            "professional_headline": candidate.professional_headline,
            "contact_email": (user.email if user and not user.email.endswith("@sourcing.internal.invalid") else candidate.contact_email),
            "phone": candidate.phone,
            "tech_stack": candidate.tech_stack,
            "years_of_experience": candidate.years_of_experience,
            "career_summary": candidate.career_summary,
            "resume_url": candidate.resume_url,
        }
        if candidate
        else None,
        "application_id": application.id if application else None,
    }
