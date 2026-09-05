from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.dependencies import require_recruiter
from app.db.session import get_session
from app.models import Application, User
from app.services.audit_service import get_application_audit
from app.services.notification_service import async_deliver_decision_notification, get_notification_completion_rate
from app.services.ai_service import EmbeddingProviderUnavailableError
from app.services.scoring_service import (
    SCORING_PROMPT_VERSION,
    async_evaluate_application,
    evaluate_application,
    ensure_final_status_has_decision,
    get_application_ranking,
    register_decision,
)

router = APIRouter()


class DecisionRequest(BaseModel):
    action: str
    discrepancy_reason: Optional[str] = None
    feedback: Optional[str] = Field(default=None, max_length=2000)


@router.post("/applications/{application_id}/evaluate")
def evaluate_application_endpoint(application_id: int, session: Session = Depends(get_session)):
    try:
        result = evaluate_application(session, application_id)
        return result
    except EmbeddingProviderUnavailableError:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SCORING_UNAVAILABLE",
                "message": "El servicio de scoring no está disponible temporalmente."
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/job-offers/{job_offer_id}/candidates")
def get_candidates_ranking(
    job_offer_id: int,
    stage_id: Optional[int] = None,
    outcome: Optional[str] = None,
    top_percent: Optional[int] = None,
    source: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_session),
):
    try:
        result = get_application_ranking(session, job_offer_id, stage_id, outcome, top_percent, source)

        # ── Auto-heal: disparar re-evaluación para cualquier application que
        # ── no tenga evaluation registrada (score null o 0 sin evidencia de IA)
        if background_tasks is not None:
            candidate_rows = result.get("candidates", [])
            for row in candidate_rows:
                app_id = row.get("application_id")
                score = row.get("similarity_score")
                version = row.get("evaluation_prompt_version")
                evaluation_status = row.get("evaluation_status")
                # También migra, una sola vez, las notas creadas con el criterio LLM anterior.
                needs_eval = evaluation_status != "unavailable" and (
                    (score is None) or (version != SCORING_PROMPT_VERSION)
                )
                if needs_eval and app_id:
                    background_tasks.add_task(async_evaluate_application, app_id)
                    row["pending_evaluation"] = True
                else:
                    row["pending_evaluation"] = evaluation_status == "pending"

        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/job-offers/{job_offer_id}/re-evaluate-all")
def re_evaluate_all_candidates(
    job_offer_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Fuerza re-evaluación de TODAS las applications de una vacante.
    Útil para recuperar scores perdidos tras reinicio de servicios."""
    apps = session.exec(
        select(Application).where(
            Application.job_offer_id == job_offer_id,
            Application.archived_at.is_(None),
        )
    ).all()
    triggered = []
    for app in apps:
        app.evaluation_status = "pending"
        app.evaluation_message = None
        session.add(app)
        background_tasks.add_task(async_evaluate_application, app.id)
        triggered.append(app.id)
    session.commit()
    return {"message": f"Re-evaluación iniciada para {len(triggered)} postulaciones", "application_ids": triggered}


@router.patch("/applications/{application_id}/decision")
def update_application_decision(
    application_id: int,
    payload: DecisionRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    recruiter: User = Depends(require_recruiter),
):
    try:
        decision = register_decision(
            session,
            application_id,
            recruiter.id,
            payload.action,
            payload.discrepancy_reason,
            feedback=payload.feedback,
        )
        ensure_final_status_has_decision(session, application_id)
        background_tasks.add_task(async_deliver_decision_notification, decision.id)
        
        app = session.get(Application, application_id)
        return {
            "message": "Decision recorded successfully",
            "application_id": application_id,
            "decision_id": decision.id,
            "action": decision.action,
            "feedback": decision.feedback,
            "notification_status": "programado",
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
