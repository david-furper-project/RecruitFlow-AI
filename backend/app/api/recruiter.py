from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.dependencies import ensure_single_cv_file, require_recruiter
from app.db.session import get_session
from app.models import Application, CandidateProfile, JobOffer, User
from app.services.application_origin_service import (
    application_origin_label,
    sourcing_origin_labels,
)
from app.services.candidate_identity_service import is_internal_candidate_email
from app.services.resume_version_service import resume_versions_for_candidate

router = APIRouter()


def _global_candidate_status(applications: list[Application]) -> str:
    outcomes = [application.outcome for application in applications if application.outcome]
    if "contratado" in outcomes:
        return "contratado"
    if "reservado" in outcomes:
        return "reservado"
    if outcomes and all(outcome == "descartado" for outcome in outcomes):
        return "descartado"
    return "activo"


def _candidate_email(session: Session, candidate: CandidateProfile) -> str:
    user = session.get(User, candidate.user_id)
    if user and not is_internal_candidate_email(user.email):
        return user.email
    return candidate.contact_email or "No especificado"


def _candidate_origins(
    session: Session,
    candidate: CandidateProfile,
    applications: list[Application],
) -> list[str]:
    labels = [application_origin_label(session, application) for application in applications]
    labels.extend(sourcing_origin_labels(session, candidate.id))
    return list(dict.fromkeys(labels)) or ["Sin postulación"]


@router.get("/talent-bank")
def get_talent_bank(
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    """Return a privacy-minimized index. Sensitive data lives in the detail endpoint."""
    candidates = session.exec(
        select(CandidateProfile).where(CandidateProfile.archived_at.is_(None))
    ).all()
    result = []
    for cand in candidates:
        applications = session.exec(
            select(Application).where(
                Application.candidate_id == cand.id,
                Application.archived_at.is_(None),
            )
        ).all()

        scores = [a.similarity_score for a in applications if a.similarity_score is not None]

        result.append({
            "candidate_id": cand.id,
            "full_name": cand.full_name,
            "global_status": _global_candidate_status(applications),
            "applications_count": len(applications),
            "best_score": max(scores) if scores else None,
            "origins": _candidate_origins(session, cand, applications),
        })

    # Sort: contratados first, then reservados, then activos, then descartados
    status_order = {"contratado": 0, "reservado": 1, "activo": 2, "descartado": 3}
    result.sort(key=lambda x: (status_order.get(x["global_status"], 4), -(x["best_score"] or 0)))
    return {"candidates": result, "total": len(result)}


@router.get("/talent-bank/{candidate_id}")
def get_talent_profile(
    candidate_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None or candidate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Perfil de candidato no encontrado.")
    applications = session.exec(
        select(Application)
        .where(
            Application.candidate_id == candidate.id,
            Application.archived_at.is_(None),
        )
        .order_by(Application.created_at.desc())
    ).all()
    scores = [application.similarity_score for application in applications if application.similarity_score is not None]
    application_details = []
    for application in applications:
        offer = session.get(JobOffer, application.job_offer_id) if application.job_offer_id else None
        application_details.append({
            "application_id": application.id,
            "job_offer_id": application.job_offer_id,
            "job_offer_title": offer.title if offer else "Vacante no disponible",
            "origin": application.origin,
            "origin_label": application_origin_label(session, application),
            "similarity_score": application.similarity_score,
            "status": application.status,
            "outcome": application.outcome,
            "created_at": application.created_at.isoformat() if application.created_at else None,
        })

    resume_source_labels = {
        "pri": "Desde PRI",
        "application_link": "Link de postulación",
        "sourcing": "Sourcing de talento",
        "profile_update": "Actualización manual",
        "legacy": "CV histórico",
    }
    versions = resume_versions_for_candidate(session, candidate.id)
    resume_history = []
    for index, version in enumerate(versions):
        offer = session.get(JobOffer, version.job_offer_id) if version.job_offer_id else None
        resume_history.append({
            "id": version.id,
            "resume_url": version.resume_url,
            "original_filename": version.original_filename,
            "source": version.source,
            "source_label": resume_source_labels.get(version.source, version.source),
            "job_offer_id": version.job_offer_id,
            "job_offer_title": offer.title if offer else None,
            "uploaded_at": version.uploaded_at.isoformat() if version.uploaded_at else None,
            "is_current": index == 0 and version.resume_url == candidate.resume_url,
        })

    return {
        "candidate_id": candidate.id,
        "full_name": candidate.full_name,
        "rut": candidate.rut,
        "email": _candidate_email(session, candidate),
        "phone": candidate.phone,
        "tech_stack": candidate.tech_stack,
        "years_of_experience": candidate.years_of_experience,
        "career_summary": candidate.career_summary,
        "courses_and_diplomas": candidate.courses_and_diplomas,
        "global_status": _global_candidate_status(applications),
        "applications_count": len(applications),
        "best_score": max(scores) if scores else None,
        "resume_url": candidate.resume_url,
        "source_url": candidate.source_url,
        "contact_status": candidate.contact_status,
        "origins": _candidate_origins(session, candidate, applications),
        "applications": application_details,
        "resume_versions": resume_history,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
    }


@router.post("/talent-bank/{candidate_id}/resume")
async def update_talent_resume(
    candidate_id: int,
    file: UploadFile = File(...),
    _single_cv: None = Depends(ensure_single_cv_file),
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    """Add a new immutable CV version without creating an Application."""
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None or candidate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Perfil de candidato no encontrado.")

    from app.api.candidates import _process_single_application

    result = await _process_single_application(
        session=session,
        full_name=candidate.full_name,
        email="",
        phone=candidate.phone,
        file=file,
        existing_candidate=candidate,
        application_origin="pri",
        resume_version_source="profile_update",
        uploaded_by_user_id=recruiter.id,
    )
    return {
        "message": (
            "CV actualizado y versión anterior conservada."
            if result["resume_updated"]
            else "Este mismo CV ya estaba registrado; no se creó un duplicado."
        ),
        **result,
    }

@router.post("/mass-upload")
async def mass_upload_cvs(
    background_tasks: BackgroundTasks,
    offer_id: int = Form(...),
    origin_mode: str = Form("authorized_application"),
    authorization_confirmed: bool = Form(False),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    if origin_mode not in {"authorized_application", "sourcing"}:
        raise HTTPException(status_code=400, detail="Origen de carga inválido.")
    if origin_mode == "sourcing":
        raise HTTPException(
            status_code=409,
            detail=(
                "Un perfil encontrado por sourcing requiere vista previa y confirmación en "
                "/api/sourcing/prospects/import; no se creó ninguna postulación."
            ),
        )
    if not authorization_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Debe confirmarse que cada candidato autorizó esta postulación.",
        )
    if not files or len(files) > 20:
        raise HTTPException(status_code=400, detail="La carga admite entre 1 y 20 CV.")
    from app.api.candidates import _process_single_application
    from app.services.scoring_service import async_evaluate_application
    
    results = []
    for file in files:
        try:
            res = await _process_single_application(
                session=session,
                full_name=(file.filename or "Candidato").rsplit(".", 1)[0],
                email="",
                phone=None,
                file=file,
                offer_id=offer_id,
                consent_given_at=datetime.utcnow(),
                application_origin="pri",
                resume_version_source="pri",
                uploaded_by_user_id=recruiter.id,
            )

            if res.get("application_created"):
                background_tasks.add_task(async_evaluate_application, res["application_id"])

            result_status = "created"
            if res.get("candidate_reused") and res.get("resume_updated"):
                result_status = "updated"
            elif res.get("candidate_reused") and res.get("application_created"):
                result_status = "reused"
            elif not res.get("application_created"):
                result_status = "already_linked"
            results.append({
                "filename": file.filename,
                "status": result_status,
                "data": res,
            })
        except HTTPException as exc:
            session.rollback()
            results.append({"filename": file.filename, "status": "error", "detail": exc.detail})
        except Exception as e:
            session.rollback()
            results.append({"filename": file.filename, "status": "error", "detail": str(e)})
            
    return {"message": f"Procesados {len(files)} CVs", "results": results}


class AssignRequest(BaseModel):
    job_offer_id: int


@router.post("/talent-bank/{candidate_id}/assign")
def assign_candidate_to_vacancy(
    candidate_id: int,
    request: AssignRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    """Assign an existing candidate from the Talent Bank to a vacancy."""
    candidate = session.get(CandidateProfile, candidate_id)
    if candidate is None or candidate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Candidato no encontrado.")
    offer = session.get(JobOffer, request.job_offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Vacante no encontrada.")

    # Check if already assigned
    existing = session.exec(
        select(Application).where(
            Application.candidate_id == candidate_id,
            Application.job_offer_id == request.job_offer_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Este candidato ya está asignado a esta vacante.")

    # Find first pipeline stage
    from app.models import PipelineStage
    first_stage = session.exec(
        select(PipelineStage)
        .where(PipelineStage.job_offer_id == request.job_offer_id)
        .order_by(PipelineStage.order_index.asc())
    ).first()

    app_record = Application(
        candidate_id=candidate_id,
        job_offer_id=request.job_offer_id,
        status="pending",
        current_stage_id=first_stage.id if first_stage else None,
        consent_given_at=datetime.utcnow(),
        origin="pri",
    )
    session.add(app_record)
    session.commit()
    session.refresh(app_record)

    # Trigger scoring in background
    from app.services.scoring_service import async_evaluate_application
    background_tasks.add_task(async_evaluate_application, app_record.id)

    return {
        "message": f"{candidate.full_name} fue asignado a la vacante '{offer.title}'.",
        "application_id": app_record.id,
    }
