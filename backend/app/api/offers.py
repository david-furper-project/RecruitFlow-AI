from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
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
    
    return db_offer

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

@router.put("/{offer_id}/application/{candidate_id}/status")
def update_application_status(
    offer_id: int, 
    candidate_id: int, 
    update: ApplicationStatusUpdate,
    session: Session = Depends(get_session)
):
    import app.models as app_model
    
    offer = session.get(JobOffer, offer_id)
    candidate = session.get(CandidateProfile, candidate_id)
    
    if not offer or not candidate:
        raise HTTPException(status_code=404, detail="Offer or candidate not found")
        
    app = session.query(app_model.Application).filter(
        app_model.Application.candidate_id == candidate_id,
        app_model.Application.job_offer_id == offer_id
    ).first()
    
    if not app:
        app = app_model.Application(
            candidate_id=candidate_id,
            job_offer_id=offer_id,
            status=update.status
        )
        session.add(app)
    else:
        app.status = update.status
        
    session.commit()
    session.refresh(app)
    
    return app

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
