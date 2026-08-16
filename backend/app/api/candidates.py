import asyncio
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_session
from app.models import Application, CandidateProfile, User
from app.services.ai_service import generate_embedding
from app.services.notification_service import async_deliver_notification
from app.services.parsing_service import (
    EXCLUDED_FIELDS,
    EXTRACTION_PROMPT_VERSION,
    extract_candidate_profile,
    extract_text_from_upload,
    sanitize_text_for_model,
    validate_cv_upload,
    validate_and_merge_profile,
)
from app.services.storage_service import upload_cv_to_storage

router = APIRouter()


async def _create_or_get_user(session: Session, email: str) -> User:
    user = session.exec(select(User).where(User.email == email)).first()
    if user is not None:
        return user
    user = User(email=email, password_hash="mock_hash", role="candidate")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


async def _process_single_application(
    session: Session,
    full_name: str,
    email: str,
    phone: Optional[str],
    file: UploadFile,
    offer_id: Optional[int] = None,
) -> dict:
    if file.filename is None:
        raise HTTPException(400, "El archivo no tiene nombre.")

    file_bytes, extracted_text, safe_name = validate_cv_upload(file)
    if not extracted_text:
        raise HTTPException(400, "No se pudo extraer texto del CV. Probablemente está escaneado o corrupto.")

    filtered_text = sanitize_text_for_model(extracted_text)
    excluded_fields = [field for field in EXCLUDED_FIELDS if field.lower() in filtered_text.lower()]
    profile_data = extract_candidate_profile(filtered_text)

    user = await _create_or_get_user(session, email)
    candidate = session.exec(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).first()
    if candidate is None:
        candidate = CandidateProfile(
            user_id=user.id,
            full_name=full_name,
            resume_url="pending",
            phone=phone,
            extracted_text=extracted_text,
            embedding=generate_embedding(filtered_text),
        )
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
    else:
        candidate.full_name = full_name or candidate.full_name
        candidate.phone = phone or candidate.phone
        candidate.extracted_text = extracted_text
        candidate.embedding = generate_embedding(filtered_text)

    merged = validate_and_merge_profile(profile_data, {
        "full_name": full_name,
        "resume_url": "pending",
        "phone": phone,
    })
    candidate.full_name = merged.get("full_name") or candidate.full_name
    candidate.tech_stack = merged.get("tech_stack") or candidate.tech_stack
    candidate.years_of_experience = merged.get("years_of_experience") if merged.get("years_of_experience") is not None else candidate.years_of_experience
    candidate.courses_and_diplomas = merged.get("courses_and_diplomas") or candidate.courses_and_diplomas
    candidate.career_summary = merged.get("career_summary") or candidate.career_summary

    resume_url = await upload_cv_to_storage(candidate.id, safe_name, file_bytes)
    candidate.resume_url = resume_url
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    app_record = None
    if offer_id is not None:
        app_record = session.exec(
            select(Application).where(
                Application.candidate_id == candidate.id,
                Application.job_offer_id == offer_id,
            )
        ).first()
        if app_record is None:
            app_record = Application(candidate_id=candidate.id, job_offer_id=offer_id, status="pending")
            session.add(app_record)
            session.commit()
            session.refresh(app_record)

    return {
        "status": "processed",
        "candidate_id": candidate.id,
        "application_id": app_record.id if app_record else None,
        "excluded_fields": excluded_fields,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "resume_url": resume_url,
    }


@router.post("/applications")
async def create_application(
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    offer_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    result = await _process_single_application(session, full_name, email, phone, file, offer_id)
    if result.get("application_id"):
        background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
    return {
        "message": "CV cargado y perfil estructurado.",
        **result,
    }


@router.post("/applications/bulk")
async def bulk_upload_applications(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
):
    results = []
    semaphore = asyncio.Semaphore(3)

    async def process_one(file: UploadFile):
        async with semaphore:
            if file.filename is None:
                return {"filename": "unknown", "status": "error", "message": "Archivo sin nombre."}
            if file.filename.lower().endswith(".pdf") is False and file.filename.lower().endswith(".docx") is False:
                return {"filename": file.filename, "status": "error", "message": "Formato inválido. Solo PDF o DOCX."}
            try:
                file_bytes, extracted_text, safe_name = validate_cv_upload(file)
                if not extracted_text:
                    return {"filename": file.filename, "status": "error", "message": "No se pudo extraer texto del CV."}

                email = file.filename.replace(" ", "").split(".")[0] + "@bulk.local"
                found_user = session.exec(select(User).where(User.email == email)).first()
                if found_user is not None:
                    return {"filename": file.filename, "status": "duplicado", "message": "Email duplicado en lote."}
                result = await _process_single_application(session, file.filename.replace(".pdf", "").replace(".docx", ""), email, None, file)
                if result.get("status") == "processed" and result.get("application_id"):
                    background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
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
    session: Session = Depends(get_session),
):
    result = await _process_single_application(session, full_name, email, phone, file, offer_id)
    if result.get("application_id"):
        background_tasks.add_task(async_deliver_notification, result["application_id"], "recepcion")
    return {
        "message": "CV cargado y perfil estructurado.",
        **result,
    }


@router.post("/{candidate_id}/upload-cv")
async def upload_cv_legacy(
    candidate_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if file.filename is None:
        raise HTTPException(400, "El archivo no tiene nombre.")
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate profile not found")

    file_bytes, extracted_text, safe_name = validate_cv_upload(file)
    candidate.extracted_text = extracted_text
    candidate.resume_url = await upload_cv_to_storage(candidate_id, safe_name, file_bytes)
    structured = extract_candidate_profile(extracted_text)
    candidate.tech_stack = structured.get("tech_stack") or candidate.tech_stack
    candidate.years_of_experience = structured.get("years_of_experience") if structured.get("years_of_experience") is not None else candidate.years_of_experience
    candidate.courses_and_diplomas = structured.get("courses_and_diplomas") or candidate.courses_and_diplomas
    candidate.career_summary = structured.get("career_summary") or candidate.career_summary
    candidate.embedding = generate_embedding(extracted_text)
    session.add(candidate)
    session.commit()
    return {"message": "CV updated.", "resume_url": candidate.resume_url}

