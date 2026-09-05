import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Set

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.dependencies import ensure_single_cv_file, require_recruiter
from app.db.session import get_session
from app.models import Application, CandidateProfile, JobOffer, User
from app.services.ai_service import generate_embedding
from app.services.application_origin_service import APPLICATION_ORIGINS
from app.services.candidate_identity_service import (
    find_candidate_by_email,
    find_user_by_email,
    internal_email_for_cv,
    is_internal_candidate_email,
    normalize_candidate_email,
    trusted_email_from_cv,
)
from app.services.matching_service import candidate_profile_text
from app.services.notification_service import async_deliver_notification
from app.services.consent_service import (
    CANDIDATE_APPLICATION_CONSENT_TEXT,
    CANDIDATE_APPLICATION_CONSENT_VERSION,
)
from app.services.parsing_service import (
    EXCLUDED_FIELDS,
    EXTRACTION_PROMPT_VERSION,
    extract_candidate_profile,
    extract_text_from_upload,
    sanitize_text_for_model,
    validate_cv_upload,
    validate_and_merge_profile,
)
from app.services.resume_version_service import (
    ensure_legacy_resume_snapshot,
    find_resume_version_by_checksum,
    record_resume_version,
    resume_checksum,
    resume_versions_for_candidate,
)
from app.services.resume_validation_service import validate_public_resume_document, validate_resume_document
from app.services.storage_service import upload_cv_to_storage

router = APIRouter()

CANDIDATE_CV_MAX_SIZE_BYTES = 3 * 1024 * 1024
CANDIDATE_CV_EXTENSIONS = {".pdf", ".doc", ".docx"}


def _validate_public_application_fields(
    full_name: str,
    email: str,
    salary_expectation: Optional[str],
    consent: Optional[bool],
) -> tuple[str, str, Optional[str]]:
    normalized_name = (full_name or "").strip()
    if not normalized_name:
        raise HTTPException(400, "El nombre es obligatorio.")

    normalized_email = normalize_candidate_email(email)
    if normalized_email is None:
        raise HTTPException(400, "Debes ingresar un correo electrónico válido.")

    if consent is not True:
        raise HTTPException(400, "Debes autorizar el tratamiento de tus datos personales.")

    normalized_salary = None
    if salary_expectation is not None and salary_expectation.strip():
        try:
            salary_value = Decimal(salary_expectation.strip())
        except InvalidOperation as exc:
            raise HTTPException(400, "La pretensión de renta debe ser numérica.") from exc
        if not salary_value.is_finite() or salary_value < 0:
            raise HTTPException(400, "La pretensión de renta debe ser un número igual o mayor que cero.")
        normalized_salary = format(salary_value, "f")

    return normalized_name, normalized_email, normalized_salary


def _find_open_public_offer(session: Session, public_id: str) -> JobOffer:
    offer = session.exec(
        select(JobOffer).where(
            JobOffer.public_id == public_id,
            JobOffer.status == "open",
        )
    ).first()
    if offer is None:
        raise HTTPException(404, "La oferta no existe o ya no está disponible.")
    return offer


def _public_offer_payload(offer: JobOffer) -> dict:
    return {
        "public_id": offer.public_id,
        "title": offer.title,
        "description": offer.description,
        "requirements": offer.requirements,
        "tech_stack": offer.tech_stack,
        "salary_range": offer.salary_range,
        "experience_years": offer.experience_years,
        "seniority": offer.seniority,
        "country": offer.country,
        "modality": offer.modality,
        "company": {"name": offer.company.name} if offer.company else None,
    }


async def _create_or_get_user(session: Session, email: str) -> User:
    user = find_user_by_email(session, email)
    if user is not None:
        if user.role != "candidate":
            raise HTTPException(
                409,
                "Este correo pertenece a una cuenta interna de PRI y no puede usarse como candidato.",
            )
        return user
    user = User(email=email, password_hash="mock_hash", role="candidate")
    session.add(user)
    session.flush()
    return user


async def _process_single_application(
    session: Session,
    full_name: str,
    email: str,
    phone: Optional[str],
    file: UploadFile,
    offer_id: Optional[int] = None,
    existing_candidate: Optional[CandidateProfile] = None,
    consent_given_at: Optional[datetime] = None,
    consent_text_version: Optional[str] = None,
    consent_text: Optional[str] = None,
    salary_expectation: Optional[str] = None,
    application_origin: str = "application_link",
    resume_version_source: Optional[str] = None,
    uploaded_by_user_id: Optional[int] = None,
    cv_allowed_extensions: Optional[Set[str]] = None,
    cv_max_size_bytes: Optional[int] = None,
    validate_public_identity: bool = False,
) -> dict:
    if existing_candidate is not None and existing_candidate.archived_at is not None:
        raise HTTPException(404, "El perfil de candidato no está disponible.")
    if file.filename is None:
        raise HTTPException(400, "El archivo no tiene nombre.")
    if application_origin not in APPLICATION_ORIGINS:
        raise HTTPException(400, "El origen de la postulación no es válido.")

    file_bytes, extracted_text, safe_name = validate_cv_upload(
        file,
        allowed_extensions=cv_allowed_extensions,
        max_size_bytes=cv_max_size_bytes,
    )
    if not extracted_text:
        raise HTTPException(400, "No se pudo extraer texto del CV. Probablemente está escaneado o corrupto.")
    if validate_public_identity:
        validate_public_resume_document(extracted_text, full_name, email)
    else:
        validate_resume_document(extracted_text)

    checksum = resume_checksum(file_bytes)
    if session.bind and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:resume_checksum))"),
            {"resume_checksum": checksum},
        )
    checksum_version = find_resume_version_by_checksum(session, checksum)
    checksum_candidate = (
        session.get(CandidateProfile, checksum_version.candidate_id)
        if checksum_version is not None
        else None
    )

    filtered_text = sanitize_text_for_model(extracted_text)
    excluded_fields = [field for field in EXCLUDED_FIELDS if field.lower() in filtered_text.lower()]
    # An exact file already has a trusted identity and snapshot. Reusing it for
    # another vacancy must not reinterpret or overwrite the current profile.
    profile_data = {} if checksum_candidate is not None else extract_candidate_profile(filtered_text)
    if validate_public_identity:
        # The document passed the CV gate and the identity evidence available in
        # it is consistent with the form. Keep the submitted identity authoritative
        # instead of allowing model output to silently rename the candidate.
        profile_data["full_name"] = full_name
        profile_data["email"] = email

    # The email supplied by the person is authoritative. For recruiter uploads
    # without a form email, identity may only come from a literal address inside
    # the document; an AI-generated value is never trusted for deduplication.
    submitted_email = normalize_candidate_email(email)
    if email and submitted_email is None:
        raise HTTPException(400, "El correo ingresado no es válido.")
    document_email = trusted_email_from_cv(extracted_text)
    known_email = None
    if existing_candidate is not None:
        existing_user = session.get(User, existing_candidate.user_id)
        known_email = normalize_candidate_email(existing_candidate.contact_email)
        if known_email is None and existing_user is not None and not is_internal_candidate_email(existing_user.email):
            known_email = normalize_candidate_email(existing_user.email)
        if submitted_email is None and known_email and document_email and document_email != known_email:
            raise HTTPException(
                409,
                "El CV contiene un correo distinto al perfil seleccionado. Revisa que corresponda a la misma persona.",
            )
    normalized_email = submitted_email or document_email or known_email
    account_email = normalized_email or internal_email_for_cv(file_bytes)

    extracted_phone = profile_data.get("phone")
    if extracted_phone:
        phone = extracted_phone

    extracted_rut = profile_data.get("rut")
    # Normalize RUT: remove dots and dashes, uppercase
    if extracted_rut:
        extracted_rut = re.sub(r'[.\-]', '', extracted_rut).upper().strip()
        if len(extracted_rut) < 7:
            extracted_rut = None  # Too short to be a real RUT
    if existing_candidate is not None and existing_candidate.rut and extracted_rut:
        current_rut = re.sub(r'[.\-]', '', existing_candidate.rut).upper().strip()
        if current_rut != extracted_rut:
            raise HTTPException(
                409,
                "El CV contiene un RUT distinto al perfil seleccionado. Revisa que corresponda a la misma persona.",
            )

    # Deduplicate globally by email and secondarily by RUT. CandidateProfile is
    # the person; Application is only the link to each separate vacancy.
    candidate = existing_candidate
    email_candidate = find_candidate_by_email(session, normalized_email or account_email)
    rut_candidate = None
    if extracted_rut:
        rut_candidate = session.exec(
            select(CandidateProfile).where(
                CandidateProfile.rut == extracted_rut,
                CandidateProfile.archived_at.is_(None),
            )
        ).first()

    resolved_candidates = {
        item.id: item
        for item in (candidate, email_candidate, rut_candidate, checksum_candidate)
        if item is not None and item.id is not None
    }
    if len(resolved_candidates) > 1:
        raise HTTPException(
            409,
            "El archivo, el correo o el RUT corresponden a perfiles distintos. Revisa la identidad antes de continuar.",
        )
    candidate = next(iter(resolved_candidates.values()), None)
    candidate_created = False

    if candidate is None:
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:identity_email))"),
                {"identity_email": account_email},
            )
        candidate = find_candidate_by_email(session, account_email)
        if candidate is None:
            user = await _create_or_get_user(session, account_email)
            candidate = session.exec(
                select(CandidateProfile).where(
                    CandidateProfile.user_id == user.id,
                    CandidateProfile.archived_at.is_(None),
                )
            ).first()
        else:
            user = session.get(User, candidate.user_id)
            if user is None:
                raise HTTPException(404, "El perfil no tiene un usuario asociado.")
            if user.role != "candidate":
                raise HTTPException(409, "El perfil está asociado a una cuenta interna de PRI.")
            if normalized_email:
                candidate.contact_email = normalized_email
                if is_internal_candidate_email(user.email):
                    user.email = normalized_email
                    session.add(user)
            email_candidate = candidate
    else:
        user = session.get(User, candidate.user_id)
        if user is None:
            raise HTTPException(404, "El perfil no tiene un usuario asociado.")
        if user.role != "candidate":
            raise HTTPException(409, "El perfil está asociado a una cuenta interna de PRI.")
        duplicate_user = find_user_by_email(session, normalized_email) if normalized_email else None
        if duplicate_user is not None and duplicate_user.id == user.id:
            duplicate_user = None
        if is_internal_candidate_email(user.email) and normalized_email and duplicate_user is None:
            user.email = normalized_email
            session.add(user)
        if normalized_email:
            candidate.contact_email = normalized_email

    source_val = application_origin
    if application_origin == "application_link":
        source_val = "Link"
    elif application_origin == "pri":
        source_val = "PRI"

    if candidate is None:
        candidate = CandidateProfile(
            user_id=user.id,
            full_name=profile_data.get("full_name") or full_name,
            resume_url="pending",
            phone=phone,
            rut=extracted_rut,
            contact_email=normalized_email,
            extracted_text=extracted_text,
            embedding=None,
            source=source_val,
            salary_expectation=salary_expectation,
        )
        session.add(candidate)
        session.flush()
        candidate_created = True
    else:
        if checksum_version is None:
            ensure_legacy_resume_snapshot(session, candidate)

    resume_updated = checksum_version is None
    resume_version = checksum_version
    if salary_expectation is not None:
        candidate.salary_expectation = salary_expectation
    if resume_updated:
        merged = validate_and_merge_profile(profile_data, {
            "full_name": full_name,
            "resume_url": "pending",
            "phone": phone,
        })
        candidate.full_name = merged.get("full_name") or candidate.full_name
        candidate.phone = merged.get("phone") or phone or candidate.phone
        candidate.rut = extracted_rut or candidate.rut
        candidate.extracted_text = extracted_text
        candidate.tech_stack = merged.get("tech_stack") or candidate.tech_stack
        candidate.years_of_experience = merged.get("years_of_experience") if merged.get("years_of_experience") is not None else candidate.years_of_experience
        candidate.courses_and_diplomas = merged.get("courses_and_diplomas") or candidate.courses_and_diplomas
        candidate.career_summary = merged.get("career_summary") or candidate.career_summary
        candidate.embedding = generate_embedding(candidate_profile_text(candidate))

        resume_url = await upload_cv_to_storage(candidate.id, safe_name, file_bytes)
        candidate.resume_url = resume_url
        resume_version, _ = record_resume_version(
            session,
            candidate,
            resume_url=resume_url,
            original_filename=safe_name,
            checksum=checksum,
            source=resume_version_source or application_origin,
            job_offer_id=offer_id,
            uploaded_by_user_id=uploaded_by_user_id,
        )
    else:
        resume_url = candidate.resume_url or checksum_version.resume_url

    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    app_record = None
    application_created = False
    if offer_id is not None:
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:candidate_id, :job_offer_id)"),
                {"candidate_id": candidate.id, "job_offer_id": offer_id},
            )
        app_record = session.exec(
            select(Application).where(
                Application.candidate_id == candidate.id,
                Application.job_offer_id == offer_id,
            )
        ).first()
        if app_record is None:
            from app.models import PipelineStage
            first_stage = session.exec(
                select(PipelineStage)
                .where(PipelineStage.job_offer_id == offer_id)
                .order_by(PipelineStage.order_index.asc())
            ).first()
            first_stage_id = first_stage.id if first_stage else None
            
            app_record = Application(
                candidate_id=candidate.id,
                job_offer_id=offer_id,
                status="pending",
                current_stage_id=first_stage_id,
                consent_given_at=consent_given_at,
                consent_text_version=consent_text_version,
                consent_text=consent_text,
                origin=application_origin,
            )
            session.add(app_record)
            session.commit()
            session.refresh(app_record)
            application_created = True
        elif consent_given_at is not None and app_record.consent_given_at is None:
            # Preserve the first recorded acceptance; only complete legacy rows
            # that predate the consent audit fields.
            app_record.consent_given_at = consent_given_at
            app_record.consent_text_version = consent_text_version
            app_record.consent_text = consent_text
            session.add(app_record)
            session.commit()
            session.refresh(app_record)
    resume_versions_count = len(resume_versions_for_candidate(session, candidate.id))
    return {
        "status": "processed",
        "candidate_id": candidate.id,
        "application_id": app_record.id if app_record else None,
        "application_created": application_created,
        "candidate_reused": not candidate_created,
        "resume_updated": resume_updated,
        "resume_version_id": resume_version.id if resume_version else None,
        "resume_versions_count": resume_versions_count,
        "excluded_fields": excluded_fields,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "resume_url": resume_url,
    }


@router.get("/offers/{public_id}")
def get_public_offer(public_id: str, session: Session = Depends(get_session)):
    """Return one active offer without exposing the recruiter offer list."""
    return _public_offer_payload(_find_open_public_offer(session, public_id))


@router.post("/offers/{public_id}/applications")
async def create_public_application(
    public_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    salary_expectation: Optional[str] = Form(None),
    consent: Optional[bool] = Form(None),
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
):
    offer = _find_open_public_offer(session, public_id)
    form = await request.form()
    if any(key in form for key in ("offer_id", "job_offer_id", "public_id")):
        raise HTTPException(400, "La oferta se determina exclusivamente mediante la URL pública.")

    normalized_name, normalized_email, normalized_salary = _validate_public_application_fields(
        full_name,
        email,
        salary_expectation,
        consent,
    )
    result = await _process_single_application(
        session=session,
        full_name=normalized_name,
        email=normalized_email,
        phone=(phone or "").strip() or None,
        file=file,
        offer_id=offer.id,
        consent_given_at=datetime.now(timezone.utc),
        consent_text_version=CANDIDATE_APPLICATION_CONSENT_VERSION,
        consent_text=CANDIDATE_APPLICATION_CONSENT_TEXT,
        salary_expectation=normalized_salary,
        application_origin="application_link",
        resume_version_source="application_link",
        cv_allowed_extensions=CANDIDATE_CV_EXTENSIONS,
        cv_max_size_bytes=CANDIDATE_CV_MAX_SIZE_BYTES,
        validate_public_identity=True,
    )
    if result.get("application_created"):
        background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
        from app.services.scoring_service import async_evaluate_application

        background_tasks.add_task(async_evaluate_application, result["application_id"])
    return {"message": "Postulación recibida correctamente.", **result}


@router.post("/applications")
async def create_application(
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    offer_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
):
    if offer_id is not None:
        raise HTTPException(400, "Usa la URL pública de la oferta para registrar una postulación.")
    result = await _process_single_application(session, full_name, email, phone, file, offer_id)
    if result.get("application_created"):
        background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
        from app.services.scoring_service import async_evaluate_application
        background_tasks.add_task(async_evaluate_application, result["application_id"])
    return {
        "message": "CV cargado y perfil estructurado.",
        **result,
    }


@router.post("/applications/bulk")
async def bulk_upload_applications(
    background_tasks: BackgroundTasks,
    offer_id: int = Form(...),
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    if not files or len(files) > 20:
        raise HTTPException(status_code=400, detail="La carga admite entre 1 y 20 CV.")
    results = []
    semaphore = asyncio.Semaphore(3)

    async def process_one(file: UploadFile):
        async with semaphore:
            if file.filename is None:
                return {"filename": "unknown", "status": "error", "message": "Archivo sin nombre."}
            if not file.filename.lower().endswith((".pdf", ".doc", ".docx")):
                return {"filename": file.filename, "status": "error", "message": "Formato inválido. Solo PDF, DOC o DOCX."}
            try:
                result = await _process_single_application(
                    session,
                    file.filename.rsplit(".", 1)[0],
                    "",
                    None,
                    file,
                    offer_id,
                    application_origin="pri",
                    uploaded_by_user_id=recruiter.id,
                )
                if result.get("status") == "processed" and result.get("application_created"):
                    background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
                    from app.services.scoring_service import async_evaluate_application
                    background_tasks.add_task(async_evaluate_application, result["application_id"])
                return {"filename": file.filename, **result}
            except HTTPException as exc:
                return {"filename": file.filename, "status": "error", "message": exc.detail}
            except Exception as exc:
                return {"filename": file.filename, "status": "error", "message": str(exc)}

    for item in files:
        results.append(await process_one(item))
    return {"message": "Lote procesado.", "results": results}


@router.post("/apply")
async def legacy_apply(
    background_tasks: BackgroundTasks,
    offer_id: Optional[int] = Form(None),
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
):
    if offer_id is not None:
        raise HTTPException(400, "Usa la URL pública de la oferta para registrar una postulación.")
    result = await _process_single_application(session, full_name, email, phone, file, offer_id)
    if result.get("application_created"):
        background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
    return {
        "message": "CV cargado y perfil estructurado.",
        **result,
    }


@router.post("/{candidate_id}/upload-cv")
async def upload_cv_legacy(
    candidate_id: int,
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
):
    if file.filename is None:
        raise HTTPException(400, "El archivo no tiene nombre.")
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate profile not found")

    result = await _process_single_application(
        session=session,
        full_name=candidate.full_name,
        email="",
        phone=candidate.phone,
        file=file,
        existing_candidate=candidate,
        application_origin="pri",
        resume_version_source="profile_update",
    )
    return {
        "message": "CV actualizado." if result["resume_updated"] else "Este CV ya estaba registrado; no se duplicó.",
        **result,
    }
