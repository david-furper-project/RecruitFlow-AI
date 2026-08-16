from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.models import Application, CandidateProfile, User
from app.services.audit_service import get_application_audit
from app.services.notification_service import async_deliver_notification, get_notification_completion_rate
from app.services.scoring_service import evaluate_application, ensure_final_status_has_decision, get_application_ranking, register_decision

router = APIRouter()


class DecisionRequest(BaseModel):
    action: str
    user_id: int
    discrepancy_reason: Optional[str] = None


@router.post("/applications/{application_id}/evaluate")
def evaluate_application_endpoint(application_id: int, session: Session = Depends(get_session)):
    try:
        result = evaluate_application(session, application_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/job-offers/{job_offer_id}/candidates")
def get_candidates_ranking(
    job_offer_id: int, 
    stage_id: Optional[int] = None,
    outcome: Optional[str] = None,
    top_percent: Optional[int] = None,
    source: Optional[str] = None,
    session: Session = Depends(get_session)
):
    try:
        return get_application_ranking(session, job_offer_id, stage_id, outcome, top_percent, source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/applications/{application_id}/decision")
def update_application_decision(application_id: int, payload: DecisionRequest, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    try:
        decision = register_decision(session, application_id, payload.user_id, payload.action, payload.discrepancy_reason)
        ensure_final_status_has_decision(session, application_id)
        
        # Disparar envío asíncrono
        background_tasks.add_task(async_deliver_notification, application_id, payload.action)
        
        app = session.get(Application, application_id)
        return {
            "message": "Decision recorded successfully",
            "application_id": application_id,
            "decision_id": decision.id,
            "action": decision.action,
            "current_stage_id": app.current_stage_id,
            "outcome": app.outcome,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422 if "requerida" in str(exc) or "Ninguna postulación" in str(exc) else 400, detail=str(exc))


@router.get("/applications/{application_id}/audit")
def application_audit(application_id: int, session: Session = Depends(get_session)):
    try:
        return get_application_audit(session, application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/notifications/completion-rate")
def notification_completion_rate(session: Session = Depends(get_session)):
    return {
        "metric_name": "notification_completion_rate",
        "rate": get_notification_completion_rate(session),
        "threshold": 95.0,
    }

