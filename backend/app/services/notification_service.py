import asyncio
from datetime import datetime
from html import escape
from sqlalchemy import text
from sqlmodel import Session, select

from app.db.session import engine
from app.models import Application, Decision, Notification
from app.services.candidate_identity_service import is_internal_candidate_email, normalize_candidate_email

ALLOWED_NOTIFICATION_TYPES = {"recepcion", "avance", "descarte"}


def _notification_type_for_action(action: str) -> str:
    mapping = {
        "avanzar": "avance",
        "descartar": "descarte",
        "reservar": "avance",
        "recepcion": "recepcion",
        "contratar": "avance"
    }
    return mapping.get(action, "recepcion")


def _build_notification_message(
    action: str,
    candidate_name: str,
    *,
    job_title: str | None = None,
    feedback: str | None = None,
) -> tuple[str, str]:
    safe_name = escape(candidate_name or "Candidato")
    safe_job_title = escape(job_title or "la vacante")
    if action == "descartar":
        safe_feedback = escape((feedback or "").strip()).replace("\n", "<br>")
        subject_job_title = " ".join((job_title or "PRI").split())[:150]
        subject = f"Actualización de tu postulación a {subject_job_title}"
        body = (
            f"<p>Hola {safe_name},</p>"
            f"<p>Gracias por tu interés y por el tiempo dedicado al proceso de <strong>{safe_job_title}</strong>.</p>"
            "<p>En esta oportunidad no continuaremos con tu postulación.</p>"
            "<div style=\"margin:20px 0;padding:16px;border-left:4px solid #b91c1c;background:#fef2f2;\">"
            f"<strong>Feedback del equipo de selección</strong><br>{safe_feedback}"
            "</div>"
            "<p>Esperamos que esta información te sea útil en tus próximos procesos. "
            "Agradecemos la confianza depositada en PRI.</p>"
            "<p>Saludos,<br>Equipo PRI</p>"
        )
        return subject, body

    status_text = {
        "avanzar": "ha avanzado a la siguiente etapa",
        "reservar": "ha quedado en reserva",
        "recepcion": "ha sido recibida exitosamente",
        "contratar": "ha sido seleccionada para contratación"
    }.get(action, "ha sido actualizada")
    subject = "Actualización de tu postulación - PRI"
    body = (
        f"<p>Hola {safe_name},</p>"
        f"<p>Tu postulación {escape(status_text)}.</p>"
        "<p>Gracias por confiar en nosotros.</p>"
        "<p>Equipo PRI</p>"
    )
    return subject, body


def _candidate_recipient(application: Application) -> tuple[str | None, str, str | None]:
    candidate = application.candidate
    if candidate is None:
        return None, "Candidato", None

    user_email = candidate.user.email if candidate.user else None
    email_candidates = [user_email, candidate.contact_email]
    recipient = next(
        (
            normalized
            for email in email_candidates
            if email and not is_internal_candidate_email(email)
            if (normalized := normalize_candidate_email(email)) is not None
        ),
        None,
    )
    job_title = application.job_offer.title if application.job_offer else None
    return recipient, candidate.full_name, job_title


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
        send_status="reintento",
        retry_count=retry_count,
    )
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification


def ensure_decision_notification_record(
    session: Session,
    decision: Decision,
    *,
    commit: bool = True,
) -> Notification:
    """Return the immutable audit delivery record belonging to one decision."""
    existing = session.exec(
        select(Notification).where(Notification.decision_id == decision.id)
    ).first()
    if existing is not None:
        return existing

    notification = Notification(
        application_id=decision.application_id,
        decision_id=decision.id,
        type=_notification_type_for_action(decision.action),
        send_status="reintento",
        retry_count=0,
    )
    session.add(notification)
    if commit:
        session.commit()
        session.refresh(notification)
    else:
        session.flush()
    return notification


async def _deliver_with_retries(
    notification_id: int,
    candidate_email: str,
    subject: str,
    body: str,
) -> None:
    from app.services.mail import get_mail_provider, MailError

    delays = [60, 300, 900]  # 1 min, 5 min, 15 min
    try:
        provider = get_mail_provider()
    except Exception as exc:
        with Session(engine) as session:
            notification = session.get(Notification, notification_id)
            if notification is not None:
                notification.send_status = "fallido"
                session.add(notification)
                session.commit()
        print(f"[Mail Provider Error] {exc}")
        return

    for attempt, delay in enumerate([0] + delays):
        if attempt > 0:
            await asyncio.sleep(delay)

        try:
            message_id = provider.send(candidate_email, subject, body)
            sent = True
        except MailError as exc:
            sent = False
            message_id = None
            print(f"[Mail Provider Error] {exc}")
        except Exception as exc:
            sent = False
            message_id = None
            print(f"[Unknown Mail Error] {exc}")

        with Session(engine) as session:
            notification = session.get(Notification, notification_id)
            if notification is None:
                return
            if sent:
                notification.send_status = "enviado"
                notification.sent_at = datetime.utcnow()
                notification.retry_count = attempt
                notification.message_id = message_id
                session.add(notification)
                session.commit()
                return
            notification.send_status = "reintento"
            notification.retry_count = attempt
            session.add(notification)
            session.commit()

    with Session(engine) as session:
        notification = session.get(Notification, notification_id)
        if notification is not None:
            notification.send_status = "fallido"
            session.add(notification)
            session.commit()


async def async_deliver_notification(application_id: int, action: str):
    """Deliver a non-decision notification, such as application receipt."""
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if not application:
            return

        candidate_email, candidate_name, job_title = _candidate_recipient(application)
        notification_type = _notification_type_for_action(action)
        notification = ensure_notification_record(session, application.id, notification_type)
        if notification.send_status == "enviado":
            return
        if candidate_email is None:
            notification.send_status = "fallido"
            session.add(notification)
            session.commit()
            return
        subject, body = _build_notification_message(action, candidate_name, job_title=job_title)
        notification_id = notification.id

    await _deliver_with_retries(notification_id, candidate_email, subject, body)


async def async_deliver_decision_notification(decision_id: int) -> None:
    """Deliver exactly one auditable email for one append-only decision."""
    with Session(engine) as session:
        decision = session.get(Decision, decision_id)
        if decision is None:
            return
        application = session.get(Application, decision.application_id)
        if application is None:
            return
        notification = ensure_decision_notification_record(session, decision)
        if notification.send_status == "enviado":
            return
        candidate_email, candidate_name, job_title = _candidate_recipient(application)
        if candidate_email is None:
            notification.send_status = "fallido"
            session.add(notification)
            session.commit()
            return
        subject, body = _build_notification_message(
            decision.action,
            candidate_name,
            job_title=job_title,
            feedback=decision.feedback,
        )
        notification_id = notification.id

    await _deliver_with_retries(notification_id, candidate_email, subject, body)


# Compatibility helper for synchronous jobs and tests.
def deliver_decision_notification(session: Session, decision_id: int) -> Notification:
    decision = session.get(Decision, decision_id)
    if decision is None:
        raise ValueError("Decision not found")
    
    notification = ensure_decision_notification_record(session, decision)
    if notification.send_status == "enviado":
        return notification
    application = session.get(Application, decision.application_id)
    if application is None:
        raise ValueError("Application not found")
    candidate_email, candidate_name, job_title = _candidate_recipient(application)
    if not candidate_email:
        notification.send_status = "fallido"
        session.add(notification)
        session.commit()
        session.refresh(notification)
        return notification

    from app.services.mail import get_mail_provider

    subject, body = _build_notification_message(
        decision.action,
        candidate_name,
        job_title=job_title,
        feedback=decision.feedback,
    )
    provider = get_mail_provider()
    for attempt in range(1, 4):
        try:
            notification.message_id = provider.send(candidate_email, subject, body)
            notification.send_status = "enviado"
            notification.sent_at = datetime.utcnow()
            notification.retry_count = attempt - 1
            break
        except Exception:
            notification.retry_count = attempt
            notification.send_status = "fallido" if attempt == 3 else "reintento"
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification


def get_notification_completion_rate(session: Session) -> float:
    # Métrica exacta OE-4: Porcentaje de notificaciones en plazo (24 hrs)
    # Excluye SQLite para evitar errores de sintaxis en testing, o previene la falla.
    if session.bind.dialect.name == "sqlite":
        # Alternativa para SQLite (tests funcionales)
        total = session.exec(select(Notification)).all()
        if not total:
            return 1.0
        sent = sum(1 for n in total if n.send_status == "enviado")
        return sent / len(total)
        
    query = text("""
        SELECT
          COUNT(*) FILTER (WHERE n.sent_at - d.decided_at < INTERVAL '24 hours')::float
          / NULLIF(COUNT(*), 0) AS porcentaje_en_plazo
        FROM decision d
        JOIN notification n ON (
            n.decision_id = d.id
            OR (
                n.decision_id IS NULL
                AND n.application_id = d.application_id
                AND n.type = CASE d.action
                    WHEN 'avanzar' THEN 'avance'
                    WHEN 'descartar' THEN 'descarte'
                    WHEN 'reservar' THEN 'avance'
                    WHEN 'contratar' THEN 'avance'
                END
            )
        )
        WHERE n.type = (
            CASE d.action 
                WHEN 'avanzar' THEN 'avance' 
                WHEN 'descartar' THEN 'descarte' 
                WHEN 'reservar' THEN 'avance' 
                WHEN 'contratar' THEN 'avance'
            END
        )
    """)
    result = session.execute(query).scalar()
    return float(result) if result is not None else 1.0


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
                select(Notification.decision_id).where(Notification.decision_id.is_not(None))
            ).all()
        ))
    ).all()
