from typing import Any, Dict, List

from sqlmodel import Session, select

from app.models import Application, Decision, Evaluation, User


def get_application_audit(session: Session, application_id: int) -> Dict[str, Any]:
    application = session.get(Application, application_id)
    if application is None:
        raise ValueError("Application not found")

    evaluation = session.exec(
        select(Evaluation).where(Evaluation.application_id == application_id).order_by(Evaluation.created_at.desc())
    ).first()

    decisions = session.exec(
        select(Decision, User)
        .join(User, User.id == Decision.user_id)
        .where(Decision.application_id == application_id)
        .order_by(Decision.decided_at.desc())
    ).all()

    decision_rows = []
    for decision, user in decisions:
        decision_rows.append({
            "id": decision.id,
            "user_id": decision.user_id,
            "user_email": user.email,
            "action": decision.action,
            "discrepancy_reason": decision.discrepancy_reason,
            "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
        })

    return {
        "application_id": application.id,
        "status": application.status,
        "similarity_score": application.similarity_score,
        "evaluation": {
            "id": evaluation.id if evaluation else None,
            "suggested_category": evaluation.suggested_category if evaluation else None,
            "explanation": evaluation.explanation if evaluation else None,
            "model_version": evaluation.model_version if evaluation else None,
            "prompt_version": evaluation.prompt_version if evaluation else None,
            "excluded_fields": evaluation.excluded_fields if evaluation else None,
            "created_at": evaluation.created_at.isoformat() if evaluation else None,
        },
        "decisions": decision_rows,
    }
