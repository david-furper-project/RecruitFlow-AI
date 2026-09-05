from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from app.db.session import get_session
from app.models import JobOffer, CandidateProfile, User
from app.api.dependencies import require_recruiter
from app.services.ai_service import generate_embedding
from app.services.matching_service import job_offer_text
from pydantic import BaseModel, Field

router = APIRouter()

class JobOfferCreate(BaseModel):
    company_id: int
    title: str
    description: str
    requirements: str
    tech_stack: str
    salary_range: str
    experience_years: int
    seniority: str
    country: Optional[str] = None
    modality: Optional[str] = None
    message: Optional[str] = None
    stages_count: Optional[int] = None

@router.post("/")
def create_offer(offer: JobOfferCreate, session: Session = Depends(get_session)):
    db_offer = JobOffer(
        company_id=offer.company_id,
        title=offer.title,
        description=offer.description,
        requirements=offer.requirements,
        tech_stack=offer.tech_stack,
        salary_range=offer.salary_range,
        experience_years=offer.experience_years,
        seniority=offer.seniority,
        country=offer.country,
        modality=offer.modality,
        message=offer.message,
        embedding=None,
    )
    db_offer.embedding = generate_embedding(job_offer_text(db_offer))
    session.add(db_offer)
    session.commit()
    session.refresh(db_offer)

    from app.models import PipelineStage
    stages_to_add = []
    if offer.stages_count and offer.stages_count >= 1:
        stages_to_add.append(PipelineStage(job_offer_id=db_offer.id, name="Pendiente", order_index=1, kind="inicial"))
        for i in range(1, offer.stages_count + 1):
            stages_to_add.append(PipelineStage(job_offer_id=db_offer.id, name=f"Proceso {i}", order_index=i+1, kind="proceso"))
        stages_to_add.append(PipelineStage(job_offer_id=db_offer.id, name="Finalista", order_index=offer.stages_count + 2, kind="final"))
    else:
        stages_to_add = [
            PipelineStage(job_offer_id=db_offer.id, name="Pendiente", order_index=1, kind="inicial"),
            PipelineStage(job_offer_id=db_offer.id, name="Preselección", order_index=2, kind="proceso"),
            PipelineStage(job_offer_id=db_offer.id, name="Entrevista 1", order_index=3, kind="proceso"),
            PipelineStage(job_offer_id=db_offer.id, name="Entrevista final", order_index=4, kind="proceso"),
            PipelineStage(job_offer_id=db_offer.id, name="Finalista", order_index=5, kind="final")
        ]

    session.add_all(stages_to_add)
    session.commit()

    return {"message": "Job offer created successfully", "id": db_offer.id}

@router.get("/")
def get_offers(session: Session = Depends(get_session)):
    offers = session.exec(select(JobOffer)).all()
    result = []
    for o in offers:
        o_dict = o.dict()
        if o.company:
            o_dict["company"] = o.company.dict()
        result.append(o_dict)
    return result

@router.get("/{offer_id}/match")
def match_candidates(offer_id: int, session: Session = Depends(get_session), limit: int = 10):
    import app.models as app_model
    offer = session.get(JobOffer, offer_id)
    if not offer or not offer.embedding:
        raise HTTPException(status_code=404, detail="Offer not found or missing embedding")

    # Consulta usando la distancia coseno de pgvector
    distance = CandidateProfile.embedding.cosine_distance(offer.embedding)
    statement = (
        select(CandidateProfile, distance.label("distance"))
        .where(
            CandidateProfile.embedding != None,
            CandidateProfile.archived_at.is_(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = session.exec(statement).all()

    results = []
    for cand, dist in rows:
        # Check if there is an application
        app = session.query(app_model.Application).filter(
            app_model.Application.candidate_id == cand.id,
            app_model.Application.job_offer_id == offer_id,
            app_model.Application.archived_at.is_(None),
        ).first()

        status = app.status if app else None

        # Same cosine similarity scale used by sourcing and applications.
        dist_val = float(dist) if dist is not None else 2.0
        match_percentage = max(0, min(100, (1 - dist_val) * 100))

        results.append({
            "candidate_id": cand.id,
            "full_name": cand.full_name,
            "email": cand.user.email if cand.user and not cand.user.email.endswith("@sourcing.internal.invalid") else "No especificado",
            "phone": cand.phone,
            "resume_url": cand.resume_url,
            "tech_stack": cand.tech_stack,
            "years_of_experience": cand.years_of_experience,
            "salary_expectation": getattr(cand, 'salary_expectation', None),
            "courses_and_diplomas": cand.courses_and_diplomas,
            "career_summary": cand.career_summary,
            "source": cand.source,
            "source_url": cand.source_url,
            "status": status,
            "match_percentage": round(match_percentage, 1),
            "created_at": cand.created_at.isoformat() if cand.created_at else None
        })

    return {"offer_id": offer.id, "matches": results}

class ApplicationStatusUpdate(BaseModel):
    status: str
    discrepancy_reason: Optional[str] = None
    feedback: Optional[str] = Field(default=None, max_length=2000)

@router.put("/{offer_id}/application/{candidate_id}/status")
def update_application_status(
    offer_id: int,
    candidate_id: int,
    update: ApplicationStatusUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    import app.models as app_model
    from app.services.scoring_service import register_decision, ensure_final_status_has_decision
    from app.services.notification_service import async_deliver_decision_notification

    offer = session.get(JobOffer, offer_id)
    candidate = session.get(CandidateProfile, candidate_id)

    if not offer or not candidate or candidate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Offer or candidate not found")

    app = session.query(app_model.Application).filter(
        app_model.Application.candidate_id == candidate_id,
        app_model.Application.job_offer_id == offer_id,
        app_model.Application.archived_at.is_(None),
    ).first()

    if not app:
        from app.models import PipelineStage
        first_stage = session.exec(
            select(PipelineStage)
            .where(PipelineStage.job_offer_id == offer_id)
            .order_by(PipelineStage.order_index.asc())
        ).first()
        first_stage_id = first_stage.id if first_stage else None

        app = app_model.Application(
            candidate_id=candidate_id,
            job_offer_id=offer_id,
            status="pending",
            current_stage_id=first_stage_id,
            origin="pri",
        )
        session.add(app)
        session.flush()

    action_map = {
        "advanced": "avanzar",
        "rejected": "descartar",
        "hired": "contratar",
        "pending": "reservar"
    }
    action = action_map.get(update.status, "reservar")

    try:
        decision = register_decision(
            session,
            app.id,
            user_id=recruiter.id,
            action=action,
            discrepancy_reason=update.discrepancy_reason,
            feedback=update.feedback,
        )
        ensure_final_status_has_decision(session, app.id)
        if background_tasks:
            background_tasks.add_task(async_deliver_decision_notification, decision.id)
    except ValueError as e:
        # Si la decisión contradice la IA sin justificación
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()

    return {"status": update.status, "application_id": app.id}

class ExtractTechStackRequest(BaseModel):
    text: str

class GenerateOfferRequest(BaseModel):
    text: str

class CloseOfferRequest(BaseModel):
    finalist_id: Optional[int] = None

@router.post("/extract-tech-stack")
def extract_tech_stack_endpoint(req: ExtractTechStackRequest):
    from app.services.ai_service import extract_job_tech_stack
    return {"tech_stack": extract_job_tech_stack(req.text)}

@router.post("/generate-from-text")
def generate_offer_from_text(req: GenerateOfferRequest):
    from app.services.ai_service import generate_offer_details
    details = generate_offer_details(req.text)
    return details

@router.put("/{offer_id}/close")
def close_offer(
    offer_id: int,
    req: CloseOfferRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    import app.models as app_model
    from app.services.notification_service import async_deliver_decision_notification
    from app.services.scoring_service import ensure_final_status_has_decision, register_finalist_decision

    offer = session.get(JobOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status == "closed_final":
        raise HTTPException(status_code=409, detail="La vacante tiene cierre definitivo y no puede modificarse.")

    if req.finalist_id is not None:
        app = session.query(app_model.Application).filter(
            app_model.Application.candidate_id == req.finalist_id,
            app_model.Application.job_offer_id == offer_id,
            app_model.Application.archived_at.is_(None),
        ).first()
        if app is None:
            raise HTTPException(status_code=404, detail="El finalista no tiene una postulación en esta vacante.")
        try:
            decision = register_finalist_decision(
                session,
                app.id,
                user_id=recruiter.id,
                discrepancy_reason="Seleccionado explícitamente como finalista al cerrar la vacante.",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.refresh(app)
        ensure_final_status_has_decision(session, app.id)
        background_tasks.add_task(async_deliver_decision_notification, decision.id)

    offer.status = "closed"
    session.add(offer)
    session.commit()
    return {"success": True, "offer_id": offer.id, "status": offer.status, "reopen_allowed": True}


@router.put("/{offer_id}/reopen")
def reopen_offer(
    offer_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    offer = session.get(JobOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status == "closed_final":
        raise HTTPException(status_code=409, detail="Una vacante cerrada definitivamente no puede reabrirse.")
    offer.status = "open"
    session.add(offer)
    session.commit()
    return {"success": True, "offer_id": offer.id, "status": offer.status}


@router.put("/{offer_id}/close-final")
def close_offer_definitively(
    offer_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_recruiter),
):
    offer = session.get(JobOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    offer.status = "closed_final"
    session.add(offer)
    session.commit()
    return {"success": True, "offer_id": offer.id, "status": offer.status, "reopen_allowed": False}


class StageUpdateItem(BaseModel):
    id: Optional[int] = None
    name: str
    order_index: int
    kind: str

class StageUpdateRequest(BaseModel):
    stages: List[StageUpdateItem]


@router.get("/{offer_id}/stages")
def get_stages(offer_id: int, session: Session = Depends(get_session)):
    from app.models import PipelineStage
    stages = session.exec(select(PipelineStage).where(PipelineStage.job_offer_id == offer_id).order_by(PipelineStage.order_index)).all()
    return stages


@router.put("/{offer_id}/stages")
def update_stages(offer_id: int, req: StageUpdateRequest, session: Session = Depends(get_session)):
    from app.models import PipelineStage, Application
    new_stages = req.stages

    # Validation 1: One 'inicial', one 'final'
    inicial_count = sum(1 for s in new_stages if s.kind == "inicial")
    final_count = sum(1 for s in new_stages if s.kind == "final")
    if inicial_count != 1 or final_count != 1:
        raise HTTPException(status_code=400, detail="Must have exactly one 'inicial' and one 'final' stage.")

    existing_stages = session.exec(select(PipelineStage).where(PipelineStage.job_offer_id == offer_id)).all()
    existing_map = {s.id: s for s in existing_stages}

    new_ids = {s.id for s in new_stages if s.id is not None}

    # Deletions
    to_delete = []
    for s_id, s in existing_map.items():
        if s_id not in new_ids:
            # Check for candidates
            candidate_count = session.exec(
                select(Application).where(
                    Application.current_stage_id == s_id,
                    Application.archived_at.is_(None),
                )
            ).all()
            if len(candidate_count) > 0:
                raise HTTPException(status_code=409, detail=f"Cannot delete stage '{s.name}' because it has {len(candidate_count)} candidates.")
            session.delete(s)
            to_delete.append(s)

    # We must flush deletes first to free up any unique constraints on order_index
    session.flush()

    # Updates and Additions
    for ns in new_stages:
        if ns.id and ns.id in existing_map:
            es = existing_map[ns.id]
            # Rename is always allowed
            es.name = ns.name

            # Reorder requires no candidates
            if es.order_index != ns.order_index:
                candidate_count = session.exec(
                    select(Application).where(
                        Application.current_stage_id == ns.id,
                        Application.archived_at.is_(None),
                    )
                ).all()
                if len(candidate_count) > 0:
                    raise HTTPException(status_code=409, detail=f"Cannot reorder stage '{es.name}' because it has {len(candidate_count)} candidates.")
                es.order_index = ns.order_index
            es.kind = ns.kind
            session.add(es)
        else:
            # Add
            new_stage = PipelineStage(
                job_offer_id=offer_id,
                name=ns.name,
                order_index=ns.order_index,
                kind=ns.kind
            )
            session.add(new_stage)

    session.commit()
    return {"message": "Stages updated"}
