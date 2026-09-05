from collections import Counter
from datetime import datetime
from html import escape
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, TypeAdapter
from sqlalchemy import text
from sqlmodel import Session, select

from app.core.config import settings
from app.api.dependencies import ensure_single_cv_file, require_recruiter
from app.db.session import get_session
from app.models import CandidateProfile, Company, JobOffer, SourcingProspect, User
from app.services.candidate_identity_service import find_candidate_by_email
from app.services.parsing_service import validate_cv_upload
from app.services.resume_validation_service import validate_resume_document
from app.services.sourcing_prospect_service import (
    CONTACT_CHANNELS,
    RESPONSE_STATUSES,
    SOURCING_SOURCES,
    confirm_prospect_import,
    convert_prospect_to_application,
    create_preview_token,
    find_profile_url,
    invitation_context,
    issue_invitation,
    preview_affinity,
    serialize_prospect,
    structure_sourcing_document,
    utcnow,
)


router = APIRouter()


def _preview_import_payload(
    *,
    file: UploadFile,
    normalized_source: str,
    job_offer_id: int,
    source_url: Optional[str],
    contact_notes: Optional[str],
    session: Session,
    recruiter: User,
) -> dict:
    _, extracted_text, _ = validate_cv_upload(file)
    validate_resume_document(extracted_text)
    try:
        structured = structure_sourcing_document(extracted_text)
        detected_url = find_profile_url(extracted_text, normalized_source, source_url)
        similarity, explanation = preview_affinity(session, structured, job_offer_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    token = create_preview_token(
        structured=structured,
        source=normalized_source,
        source_url=detected_url,
        job_offer_id=job_offer_id,
        created_by_user_id=recruiter.id,
        contact_notes=contact_notes,
        semantic_similarity=similarity,
        match_explanation=explanation,
    )
    return {
        "preview": {
            "full_name": structured.get("full_name"),
            "headline": structured.get("headline"),
            "experience": structured.get("experience"),
            "years_of_experience": structured.get("years_of_experience"),
            "education": structured.get("education"),
            "skills": structured.get("skills"),
            "summary": structured.get("summary"),
            "source": normalized_source,
            "source_url": detected_url,
            "contact_email": structured.get("contact_email"),
            "contact_phone": structured.get("contact_phone"),
            "semantic_similarity": similarity,
            "match_explanation": explanation,
        },
        "preview_token": token,
        "expires_in_minutes": 30,
        "persisted": False,
    }


@router.post("/prospects/import")
def preview_prospect_import(
    file: UploadFile = File(...),
    source: str = Form(...),
    job_offer_id: int = Form(...),
    source_url: Optional[str] = Form(None),
    contact_notes: Optional[str] = Form(None),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    normalized_source = source.strip().lower()
    if normalized_source not in SOURCING_SOURCES:
        raise HTTPException(status_code=400, detail="Origen de sourcing inválido.")
    return _preview_import_payload(
        file=file,
        normalized_source=normalized_source,
        job_offer_id=job_offer_id,
        source_url=source_url,
        contact_notes=contact_notes,
        session=session,
        recruiter=recruiter,
    )


@router.post("/prospects/import/bulk")
def preview_prospect_import_bulk(
    files: List[UploadFile] = File(...),
    source: str = Form(...),
    job_offer_id: int = Form(...),
    source_url: Optional[str] = Form(None),
    contact_notes: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    """Analyze up to 20 sourced profiles without persisting candidates or applications."""
    normalized_source = source.strip().lower()
    if normalized_source not in SOURCING_SOURCES:
        raise HTTPException(status_code=400, detail="Origen de sourcing inválido.")
    if not files or len(files) > 20:
        raise HTTPException(status_code=400, detail="La carga de sourcing admite entre 1 y 20 perfiles.")
    if len(files) > 1 and (source_url or "").strip():
        raise HTTPException(
            status_code=400,
            detail="En una carga múltiple, la URL de origen debe venir dentro del documento de cada perfil.",
        )

    results = []
    for file in files:
        filename = file.filename or "archivo_sin_nombre"
        try:
            payload = _preview_import_payload(
                file=file,
                normalized_source=normalized_source,
                job_offer_id=job_offer_id,
                source_url=source_url,
                contact_notes=contact_notes,
                session=session,
                recruiter=recruiter,
            )
            results.append({"filename": filename, "status": "ready", **payload})
        except HTTPException as exc:
            results.append({"filename": filename, "status": "error", "detail": exc.detail})
        except Exception:
            session.rollback()
            results.append(
                {
                    "filename": filename,
                    "status": "error",
                    "detail": "No fue posible analizar este perfil.",
                }
            )

    return {
        "message": f"Se analizaron {len(files)} perfiles de sourcing.",
        "results": results,
        "total": len(results),
        "ready": sum(item["status"] == "ready" for item in results),
        "errors": sum(item["status"] == "error" for item in results),
    }


class ConfirmImportRequest(BaseModel):
    preview_token: str


@router.post("/prospects/import/confirm", status_code=201)
def confirm_import(
    request: ConfirmImportRequest,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    prospect, _ = confirm_prospect_import(session, request.preview_token)
    return {
        "message": "Perfil confirmado como prospecto; no se creó una postulación.",
        "prospect": serialize_prospect(session, prospect),
    }


@router.get("/prospects")
def list_prospects(
    job_offer_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    if session.get(JobOffer, job_offer_id) is None:
        raise HTTPException(status_code=404, detail="Vacante no encontrada.")
    prospects = session.exec(
        select(SourcingProspect)
        .where(SourcingProspect.job_offer_id == job_offer_id)
        .order_by(SourcingProspect.created_at.desc())
    ).all()
    counts = Counter(prospect.status for prospect in prospects)
    return {
        "prospects": [serialize_prospect(session, prospect) for prospect in prospects],
        "counters": {status: counts.get(status, 0) for status in sorted(counts)},
        "total": len(prospects),
    }


class ContactRequest(BaseModel):
    channel: str
    value: Optional[str] = None
    notes: Optional[str] = None
    contacted_at: Optional[datetime] = None
    message: Optional[str] = None


def _get_prospect(prospect_id: int, session: Session) -> SourcingProspect:
    prospect = session.get(SourcingProspect, prospect_id)
    if prospect is None:
        raise HTTPException(status_code=404, detail="Prospecto no encontrado.")
    return prospect


@router.post("/prospects/{prospect_id}/contact")
def record_contact(
    prospect_id: int,
    request: ContactRequest,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    prospect = _get_prospect(prospect_id, session)
    channel = request.channel.strip().lower()
    if channel not in CONTACT_CHANNELS:
        raise HTTPException(status_code=400, detail="Canal de contacto inválido.")
    if prospect.status not in {"identificado", "contactado", "sin_respuesta"}:
        raise HTTPException(status_code=409, detail="El estado actual no permite registrar un nuevo contacto.")
    candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
    contact_value = (request.value or "").strip()
    if candidate is None:
        raise HTTPException(status_code=409, detail="El prospecto no tiene un perfil de candidato asociado.")

    delivery = None
    if channel in {"correo", "telefono"} and not contact_value:
        raise HTTPException(status_code=400, detail="Debes indicar el dato de contacto.")
    if channel == "correo":
        try:
            normalized_email = str(TypeAdapter(EmailStr).validate_python(contact_value))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="El correo de contacto no es válido.") from exc

        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:identity_email))"),
                {"identity_email": normalized_email},
            )
        duplicate_candidate = find_candidate_by_email(session, normalized_email)
        if duplicate_candidate is not None and duplicate_candidate.id != candidate.id:
            raise HTTPException(status_code=409, detail="Este correo ya está registrado en el sistema asociado a otro candidato. No puedes contactarlo con este correo.")
        if request.message:
            from app.services.mail import get_mail_provider

            offer = session.get(JobOffer, prospect.job_offer_id)
            offer_title = offer.title if offer else "esta oportunidad"
            email_subject = f"Oportunidad profesional: {offer_title}"
            html_content = f"<p>{escape(request.message).replace(chr(10), '<br>')}</p>"
            try:
                message_id = get_mail_provider().send(
                    normalized_email,
                    email_subject,
                    html_content,
                )
            except Exception as exc:
                reason = str(exc).strip() or "El proveedor de correo rechazó la solicitud."
                raise HTTPException(
                    status_code=502,
                    detail=f"No se pudo enviar el correo. {reason}",
                ) from exc
            provider = settings.MAIL_PROVIDER.strip().lower()
            delivery = {
                "status": "local_preview" if provider == "mailpit" else "accepted",
                "provider": provider,
                "recipient": normalized_email,
                "message_id": message_id,
            }
        candidate.contact_email = normalized_email
        session.add(candidate)
    elif channel == "telefono":
        candidate.phone = contact_value
        session.add(candidate)
    prospect.status = "contactado"
    prospect.contact_channel = channel
    prospect.contact_notes = request.notes
    prospect.contacted_at = request.contacted_at or utcnow()
    prospect.updated_at = utcnow()
    session.add(prospect)
    session.commit()
    if delivery and delivery["status"] == "local_preview":
        response_message = "Correo capturado en el entorno local; no fue enviado a una bandeja real."
    elif delivery:
        response_message = "El proveedor aceptó el correo y el contacto quedó registrado."
    else:
        response_message = "Contacto registrado."
    return {
        "message": response_message,
        "delivery": delivery,
        "prospect": serialize_prospect(session, prospect),
    }


class ResponseRequest(BaseModel):
    response: str
    notes: Optional[str] = None
    responded_at: Optional[datetime] = None


@router.post("/prospects/{prospect_id}/response")
def record_response(
    prospect_id: int,
    request: ResponseRequest,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    prospect = _get_prospect(prospect_id, session)
    response = request.response.strip().lower()
    if response not in RESPONSE_STATUSES:
        raise HTTPException(status_code=400, detail="Respuesta de sourcing inválida.")
    if prospect.status not in {"contactado", "sin_respuesta"}:
        raise HTTPException(status_code=409, detail="Primero debe registrarse el contacto con el prospecto.")
    prospect.status = response
    if request.notes:
        prospect.contact_notes = request.notes
    prospect.responded_at = request.responded_at or utcnow()
    prospect.updated_at = utcnow()
    session.add(prospect)
    session.commit()
    return {"message": "Respuesta registrada.", "prospect": serialize_prospect(session, prospect)}


class InviteRequest(BaseModel):
    email: Optional[EmailStr] = None
    send_email: bool = True
    expires_in_days: int = 7


@router.post("/prospects/{prospect_id}/invite")
def invite_prospect(
    prospect_id: int,
    request: InviteRequest,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    prospect = _get_prospect(prospect_id, session)
    if prospect.status not in {"interesado", "invitado"}:
        raise HTTPException(status_code=409, detail="Sólo se puede invitar a un prospecto que manifestó interés.")
    if request.expires_in_days < 1 or request.expires_in_days > 30:
        raise HTTPException(status_code=400, detail="La vigencia debe estar entre 1 y 30 días.")
    candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
    offer = session.get(JobOffer, prospect.job_offer_id)
    company = session.get(Company, offer.company_id) if offer else None
    token, expires_at = issue_invitation(prospect, request.expires_in_days)
    session.add(prospect)
    session.commit()
    invitation_url = f"{settings.SOURCING_INVITATION_BASE_URL.rstrip('/')}/{token}"
    recipient_email = (
        str(request.email) if request.email else (candidate.contact_email if candidate else None)
    ) if request.send_email else None
    
    company_name = company.name if company else "la empresa"
    candidate_name = candidate.full_name if candidate else ""
    offer_title = offer.title if offer else "esta oportunidad"
    email_subject = f"Una oportunidad que podría interesarte: {offer_title}"
    suggested_message = (
        f"Hola {candidate_name},\n\n"
        "Estuvimos revisando tu perfil profesional y creemos que tu experiencia "
        f"podría tener una excelente afinidad con la vacante de {offer_title} en {company_name}.\n\n"
        "Si te interesa conocer los detalles y participar en el proceso, puedes revisar "
        f"la oferta y completar tu postulación aquí:\n{invitation_url}\n\n"
        "Saludos,\n"
        f"Equipo de Selección de {company_name}"
    )
    delivery_warning = None
    email_delivered = False
    if recipient_email:
        try:
            from app.services.mail import get_mail_provider

            get_mail_provider().send(
                recipient_email,
                email_subject,
                (
                    f"<p>Hola {escape(candidate_name)},</p>"
                    "<p>Estuvimos revisando tu perfil profesional y creemos que tu experiencia "
                    f"podría tener una excelente afinidad con la vacante de <strong>{escape(offer_title)}</strong> "
                    f"en {escape(company_name)}.</p>"
                    "<p>Si te interesa conocer los detalles y participar en el proceso, revisa la oferta "
                    "y completa tu postulación:</p>"
                    f"<p><a href=\"{escape(invitation_url, quote=True)}\" "
                    "style=\"display:inline-block;padding:12px 20px;background:#b91c1c;color:#fff;"
                    "text-decoration:none;border-radius:6px;font-weight:700\">Revisar oferta y postular</a></p>"
                    f"<p>Saludos,<br>Equipo de Selección de {escape(company_name)}</p>"
                ),
            )
            email_delivered = True
        except Exception as exc:
            delivery_warning = f"La invitación quedó activa, pero el correo no pudo enviarse: {exc}"
    return {
        "message": "Invitación privada creada.",
        "invitation_url": invitation_url,
        "expires_at": expires_at.isoformat(),
        "recipient_email": recipient_email,
        "email_subject": email_subject,
        "suggested_message": suggested_message,
        "email_delivered": email_delivered,
        "delivery_warning": delivery_warning,
    }


@router.get("/invitations/{token}")
def get_invitation(token: str, session: Session = Depends(get_session)):
    prospect = invitation_context(session, token)
    candidate = session.get(CandidateProfile, prospect.candidate_profile_id)
    offer = session.get(JobOffer, prospect.job_offer_id)
    company = session.get(Company, offer.company_id) if offer else None
    return {
        "candidate_name": candidate.full_name,
        "candidate_email": candidate.contact_email,
        "candidate_phone": candidate.phone,
        "job_offer_id": offer.id,
        "title": offer.title,
        "company_name": company.name if company else None,
        "description": offer.description,
        "requirements": offer.requirements,
        "expires_at": prospect.invitation_expires_at.isoformat(),
    }


@router.post("/invitations/{token}/apply")
async def accept_invitation(
    token: str,
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    consent: bool = Form(...),
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
):
    prospect = invitation_context(session, token)
    application = await convert_prospect_to_application(
        session=session,
        prospect=prospect,
        file=file,
        full_name=full_name,
        email=email,
        phone=phone,
        consent=consent,
        authorization_channel="invitacion_privada",
        authorization_at=utcnow(),
        authorization_notes="Aceptación registrada mediante enlace privado de sourcing.",
    )
    _schedule_post_conversion(background_tasks, application.id)
    return {"message": "Postulación completada.", "application_id": application.id}


@router.post("/prospects/{prospect_id}/convert")
async def convert_with_external_authorization(
    prospect_id: int,
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    consent: bool = Form(...),
    authorization_confirmed: bool = Form(...),
    authorization_channel: str = Form(...),
    authorization_at: datetime = Form(...),
    authorization_notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    if not authorization_confirmed:
        raise HTTPException(status_code=400, detail="Debe verificarse la autorización externa del candidato.")
    prospect = _get_prospect(prospect_id, session)
    application = await convert_prospect_to_application(
        session=session,
        prospect=prospect,
        file=file,
        full_name=full_name,
        email=email,
        phone=phone,
        consent=consent,
        authorization_channel=authorization_channel,
        authorization_at=authorization_at,
        authorization_notes=authorization_notes,
    )
    _schedule_post_conversion(background_tasks, application.id)
    return {"message": "Prospecto convertido en una única postulación.", "application_id": application.id}


def _schedule_post_conversion(background_tasks: BackgroundTasks, application_id: int) -> None:
    from app.services.notification_service import async_deliver_notification
    from app.services.scoring_service import async_evaluate_application

    background_tasks.add_task(async_deliver_notification, application_id, "recepcion")
    background_tasks.add_task(async_evaluate_application, application_id)
