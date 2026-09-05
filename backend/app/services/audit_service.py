from typing import Any, Dict, List

from sqlmodel import Session, select

from app.models import Application, Decision, Evaluation, Notification, User


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

    decision_ids = [decision.id for decision, _ in decisions if decision.id is not None]
    notifications_by_decision = {}
    if decision_ids:
        notifications = session.exec(
            select(Notification).where(Notification.decision_id.in_(decision_ids))
        ).all()
        notifications_by_decision = {
            notification.decision_id: notification for notification in notifications
        }

    decision_rows = []
    for decision, user in decisions:
        notification = notifications_by_decision.get(decision.id)
        decision_rows.append({
            "id": decision.id,
            "user_id": decision.user_id,
            "user_email": user.email,
            "action": decision.action,
            "discrepancy_reason": decision.discrepancy_reason,
            "feedback": decision.feedback,
            "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
            "notification": {
                "id": notification.id,
                "send_status": notification.send_status,
                "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
                "message_id": notification.message_id,
                "retry_count": notification.retry_count,
            } if notification else None,
        })

    return {
        "application_id": application.id,
        "status": application.status,
        "similarity_score": application.similarity_score,
        "evaluation": {
            "id": evaluation.id if evaluation else None,
            "suggested_category": evaluation.suggested_category if evaluation else None,
            "explanation": evaluation.explanation if evaluation else None,
            "interview_questions": evaluation.interview_questions if evaluation else None,
            "model_version": evaluation.model_version if evaluation else None,
            "prompt_version": evaluation.prompt_version if evaluation else None,
            "excluded_fields": evaluation.excluded_fields if evaluation else None,
            "created_at": evaluation.created_at.isoformat() if evaluation else None,
        },
        "decisions": decision_rows,
    }
