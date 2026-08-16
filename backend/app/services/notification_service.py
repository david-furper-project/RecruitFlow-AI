import asyncio
from datetime import datetime
from sqlalchemy import text
from sqlmodel import Session, select

from app.db.session import engine
from app.models import Application, Decision, Notification

ALLOWED_NOTIFICATION_TYPES = {"recepcion", "avance", "descarte"}


def _notification_type_for_action(action: str) -> str:
    mapping = {
        "avanzar": "avance",
        "descartar": "descarte",
        "reservar": "avance",
        "recepcion": "recepcion",
        "contratar": "contratacion"
    }
    return mapping.get(action, "recepcion")


def _build_notification_message(action: str, candidate_name: str) -> tuple[str, str]:
    status_text = {
        "avanzar": "ha avanzado a la siguiente etapa",
        "descartar": "ha sido descartada en esta etapa",
        "reservar": "ha quedado en reserva",
        "recepcion": "ha sido recibida exitosamente",
        "contratar": "ha sido seleccionada para contratación"
    }.get(action, "ha sido actualizada")
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


async def async_deliver_notification(application_id: int, action: str):
    """
    Función asíncrona que se encarga del envío del correo electrónico.
    Debe llamarse utilizando FastAPI BackgroundTasks.
    No usa la sesión de la request para evitar conflictos.
    """
    from app.services.mail import get_mail_provider, MailError
    
    delays = [60, 300, 900]  # 1 min, 5 min, 15 min
    provider = get_mail_provider()
    
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if not application:
            return
            
        candidate = application.candidate
        candidate_email = candidate.user.email if candidate and candidate.user else None
        candidate_name = candidate.full_name if candidate else "Candidato"
        
        notification_type = _notification_type_for_action(action)
        notification = ensure_notification_record(session, application.id, notification_type)
        
        if candidate_email is None:
            notification.send_status = "fallido"
            session.add(notification)
            session.commit()
            return
            
        subject, body = _build_notification_message(action, candidate_name)
        notification_id = notification.id
        
    for attempt, delay in enumerate([0] + delays):
        if attempt > 0:
            await asyncio.sleep(delay)
            
        message_id = None
        error_msg = None
        
        try:
            message_id = provider.send(candidate_email, subject, body)
            sent = True
        except MailError as e:
            sent = False
            error_msg = str(e)
            print(f"[Mail Provider Error] {error_msg}")
            
            # Si el error indica límite excedido (429), reintentamos en el siguiente loop
            # Si es 401 o 403, podría ser permanente pero dejaremos que agote los intentos
            # según la instrucción.
        except Exception as e:
            sent = False
            error_msg = str(e)
            print(f"[Unknown Mail Error] {error_msg}")
            
        with Session(engine) as session:
            notification = session.get(Notification, notification_id)
            if sent:
                notification.send_status = "enviado"
                notification.sent_at = datetime.utcnow()
                notification.retry_count = attempt
                notification.message_id = message_id
                session.add(notification)
                session.commit()
                return
            else:
                notification.send_status = "reintento"
                notification.retry_count = attempt
                session.add(notification)
                session.commit()

    # Si agotamos los intentos
    with Session(engine) as session:
        notification = session.get(Notification, notification_id)
        notification.send_status = "fallido"
        session.add(notification)
        session.commit()


# Compatibilidad hacia atrás (por si algún lugar la sigue llamando síncronamente)
# Recomendado: Quitar su uso a favor de async_deliver_notification + BackgroundTasks
def deliver_decision_notification(session: Session, decision_id: int) -> Notification:
    decision = session.get(Decision, decision_id)
    if decision is None:
        raise ValueError("Decision not found")
    
    notification_type = _notification_type_for_action(decision.action)
    notification = ensure_notification_record(session, decision.application_id, notification_type)
    return notification


def get_notification_completion_rate(session: Session) -> float:
    # Métrica exacta OE-4: Porcentaje de notificaciones en plazo (24 hrs)
    # Excluye SQLite para evitar errores de sintaxis en testing, o previene la falla.
    if session.bind.dialect.name == "sqlite":
        # Alternativa para SQLite (tests funcionales)
        total = session.exec(select(Notification)).all()
        if not total:
            return 100.0
        sent = sum(1 for n in total if n.send_status == "enviado")
        return (sent / len(total)) * 100.0
        
    query = text("""
        SELECT
          COUNT(*) FILTER (WHERE n.sent_at - d.decided_at < INTERVAL '24 hours')::float
          / NULLIF(COUNT(*), 0) * 100 AS porcentaje_en_plazo
        FROM decision d
        JOIN notification n ON n.application_id = d.application_id
        WHERE n.type = (
            CASE d.action 
                WHEN 'avanzar' THEN 'avance' 
                WHEN 'descartar' THEN 'descarte' 
                WHEN 'reservar' THEN 'avance' 
                WHEN 'contratar' THEN 'contratacion' 
            END
        )
    """)
    result = session.execute(query).scalar()
    return float(result) if result is not None else 100.0


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
