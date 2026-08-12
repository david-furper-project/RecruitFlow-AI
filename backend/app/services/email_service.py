import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.core.config import settings

def send_status_notification(to_email: str, status: str, candidate_name: str) -> bool:
    """Envía un correo de notificación de estado usando SendGrid."""
    subject = f"Actualización de tu postulación - {settings.PROJECT_NAME}"
    content = f"Hola {candidate_name},\n\nEl estado de tu postulación ha sido actualizado a: {status}.\n\nSaludos,\nEl Equipo de Reclutamiento"
    
    if settings.SENDGRID_API_KEY == "mock_sendgrid_key":
        print(f"[MOCK EMAIL] To: {to_email} | Subject: {subject} | Content: {content}")
        return True
        
    message = Mail(
        from_email=settings.SENDER_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=content
    )
    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        return response.status_code in (200, 201, 202)
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
