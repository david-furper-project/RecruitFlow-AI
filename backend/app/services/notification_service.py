from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import Application, Decision, Notification, User

ALLOWED_NOTIFICATION_TYPES = {"recepcion", "avance", "descarte"}


def sendgrid_mailer(to_email: str, subject: str, body: str) -> bool:
    from app.core.config import settings
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    if settings.SENDGRID_API_KEY == "mock_sendgrid_key":
        print(f"[MOCK SENDGRID] To: {to_email} | Subject: {subject} | Body: {body}")
        return True

    message = Mail(
        from_email=settings.SENDER_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body,
    )
    try:
        client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = client.send(message)
        return response.status_code in (200, 201, 202)
    except Exception:
        return False


def _notification_type_for_action(action: str) -> str:
    mapping = {
        "avanzar": "avance",
        "descartar": "descarte",
        "reservar": "avance",
    }
    return mapping.get(action, "recepcion")


def _build_notification_message(action: str, candidate_name: str) -> tuple[str, str]:
    status_text = {
        "avanzar": "ha avanzado en el proceso",
        "descartar": "ha sido descartado en esta etapa",
        "reservar": "ha quedado en reserva",
    }.get(action, "ha sido actualizado")
    subject = f"Actualización de tu postulación - PRI"
    body = (
        f"Hola {candidate_name},\n\n"
        f"Tu postulación {status_text}.\n\n"
        "Gracias por confiar en nosotros.\n\n"
        "Equipo PRI"
    )
    return subject, body


def ensure_notification_record(session: Session, application_id: int, notification_type: str, retry_count: int = 0) -> Notification:
    existing = session.exec(
        select(Notification)
        .where(Notification.application_id == application_id, Notification.type == notification_type)
        .order_by(Notification.created_at.desc())
    ).first()
    if existing is not None:
        return existing

    notification = Notification(
        application_id=application_id,
        type=notification_type,
        send_status="pendiente",
        retry_count=retry_count,
    )
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification


def deliver_decision_notification(session: Session, decision_id: int) -> Notification:
    decision = session.get(Decision, decision_id)
    if decision is None:
        raise ValueError("Decision not found")

    application = session.get(Application, decision.application_id)
    if application is None:
        raise ValueError("Application not found")

    candidate = application.candidate
    candidate_email = candidate.user.email if candidate and candidate.user else None
    candidate_name = candidate.full_name if candidate else "Candidato"

    notification_type = _notification_type_for_action(decision.action)
    notification = ensure_notification_record(session, application.id, notification_type)

    if candidate_email is None:
        notification.send_status = "fallido"
        notification.retry_count = 3
        session.add(notification)
        session.commit()
        session.refresh(notification)
        return notification

    subject, body = _build_notification_message(decision.action, candidate_name)
    sent = False
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            sent = sendgrid_mailer(candidate_email, subject, body)
            if sent:
                notification.send_status = "enviado"
                notification.sent_at = datetime.utcnow()
                notification.retry_count = attempt
                session.add(notification)
                session.commit()
                session.refresh(notification)
                return notification
        except Exception:
            pass

        notification.retry_count = attempt
        session.add(notification)
        session.commit()

    notification.send_status = "fallido"
    notification.retry_count = max_retries
    notification.sent_at = None
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification


def get_notification_completion_rate(session: Session) -> float:
    total = session.exec(select(Notification)).all()
    if not total:
        return 0.0
    sent = sum(1 for n in total if n.send_status == "enviado" and n.sent_at is not None)
    return sent / len(total)


def get_notifications_for_application(session: Session, application_id: int):
    return session.exec(
        select(Notification)
        .where(Notification.application_id == application_id)
        .order_by(Notification.created_at.desc())
    ).all()


def get_decision_without_notification_jobs(session: Session):
    return session.exec(
        select(Decision)
        .where(~Decision.id.in_(
            session.exec(
                select(Notification.application_id).where(Notification.send_status == "enviado")
            ).all()
        ))
    ).all()
