from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from app.db.session import get_session
from app.models import JobOffer, CandidateProfile
from app.services.ai_service import generate_embedding
from pydantic import BaseModel

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

@router.post("/")
def create_offer(offer: JobOfferCreate, session: Session = Depends(get_session)):
    # 1. Generar embedding combinando la información clave
    full_text = (
        f"Título: {offer.title}\n"
        f"Descripción: {offer.description}\n"
        f"Requerimientos: {offer.requirements}\n"
        f"Stack Tecnológico: {offer.tech_stack}\n"
        f"Seniority: {offer.seniority}\n"
        f"Experiencia Mínima: {offer.experience_years} años\n"
        f"Rango Salarial: {offer.salary_range}"
    )
    embedding_vector = generate_embedding(full_text)
    
    # 2. Guardar en DB
    db_offer = JobOffer(
        company_id=offer.company_id,
        title=offer.title,
        description=offer.description,
        requirements=offer.requirements,
        tech_stack=offer.tech_stack,
        salary_range=offer.salary_range,
        experience_years=offer.experience_years,
        seniority=offer.seniority,
        embedding=embedding_vector
    )
    session.add(db_offer)
    session.commit()
    session.refresh(db_offer)
    
    from app.models import PipelineStage
    default_stages = [
        PipelineStage(job_offer_id=db_offer.id, name="Pendiente", order_index=1, kind="inicial"),
        PipelineStage(job_offer_id=db_offer.id, name="Preselección", order_index=2, kind="proceso"),
        PipelineStage(job_offer_id=db_offer.id, name="Entrevista 1", order_index=3, kind="proceso"),
        PipelineStage(job_offer_id=db_offer.id, name="Entrevista final", order_index=4, kind="proceso"),
        PipelineStage(job_offer_id=db_offer.id, name="Finalista", order_index=5, kind="final")
    ]
    session.add_all(default_stages)
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
        .where(CandidateProfile.embedding != None)
        .order_by(distance)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    
    results = []
    for cand, dist in rows:
        # Check if there is an application
        app = session.query(app_model.Application).filter(
            app_model.Application.candidate_id == cand.id,
            app_model.Application.job_offer_id == offer_id
        ).first()
        
        status = app.status if app else None
        
        # Calculate percentage: distance 0 -> 100%, distance 2 -> 0%
        # However, typically cosine distance ranges 0 to 2. Let's make it friendly:
        # (1 - distance/2) * 100
        dist_val = float(dist) if dist is not None else 2.0
        match_percentage = max(0, min(100, (1 - (dist_val / 2.0)) * 100))
        
        results.append({
            "candidate_id": cand.id,
            "full_name": cand.full_name,
            "email": cand.user.email if cand.user else "No especificado",
            "phone": cand.phone,
            "resume_url": cand.resume_url,
            "tech_stack": cand.tech_stack,
            "years_of_experience": cand.years_of_experience,
            "salary_expectation": getattr(cand, 'salary_expectation', None),
            "courses_and_diplomas": cand.courses_and_diplomas,
            "career_summary": cand.career_summary,
            "status": status,
            "match_percentage": round(match_percentage, 1),
            "created_at": cand.created_at.isoformat() if cand.created_at else None
        })
        
    return {"offer_id": offer.id, "matches": results}

class ApplicationStatusUpdate(BaseModel):
    status: str
    discrepancy_reason: Optional[str] = None

@router.put("/{offer_id}/application/{candidate_id}/status")
def update_application_status(
    offer_id: int, 
    candidate_id: int, 
    update: ApplicationStatusUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    import app.models as app_model
    from app.services.scoring_service import register_decision, ensure_final_status_has_decision
    from app.services.notification_service import async_deliver_notification
    
    offer = session.get(JobOffer, offer_id)
    candidate = session.get(CandidateProfile, candidate_id)
    
    if not offer or not candidate:
        raise HTTPException(status_code=404, detail="Offer or candidate not found")
        
    app = session.query(app_model.Application).filter(
        app_model.Application.candidate_id == candidate_id,
        app_model.Application.job_offer_id == offer_id
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
            current_stage_id=first_stage_id
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
        decision = register_decision(session, app.id, user_id=1, action=action, discrepancy_reason=update.discrepancy_reason)
        ensure_final_status_has_decision(session, app.id)
        if background_tasks:
            background_tasks.add_task(async_deliver_notification, app.id, action)
    except ValueError as e:
        # Si la decisión contradice la IA sin justificación
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()
        
    return {"status": update.status, "application_id": app.id}

class ExtractTechStackRequest(BaseModel):
    text: str

class CloseOfferRequest(BaseModel):
    finalist_id: Optional[int] = None

@router.post("/extract-tech-stack")
def extract_tech_stack_endpoint(req: ExtractTechStackRequest):
    from app.services.ai_service import extract_job_tech_stack
    return {"tech_stack": extract_job_tech_stack(req.text)}

@router.put("/{offer_id}/close")
def close_offer(
    offer_id: int,
    req: CloseOfferRequest,
    session: Session = Depends(get_session)
):
    import app.models as app_model
    offer = session.get(JobOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
        
    offer.status = "closed"
    
    if req.finalist_id:
        app = session.query(app_model.Application).filter(
            app_model.Application.candidate_id == req.finalist_id,
            app_model.Application.job_offer_id == offer_id
        ).first()
        if app:
            app.status = "accepted"
            
    session.commit()
    return {"success": True, "offer_id": offer.id}


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
            candidate_count = session.exec(select(Application).where(Application.current_stage_id == s_id)).all()
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
                candidate_count = session.exec(select(Application).where(Application.current_stage_id == ns.id)).all()
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
