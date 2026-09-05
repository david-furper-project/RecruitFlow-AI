from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.core.config import settings
from .base import MailProvider, MailError

class SendGridProvider(MailProvider):
    def send(self, to: str, subject: str, html: str) -> str:
        if settings.SENDGRID_API_KEY == "mock_sendgrid_key":
            print(f"[MOCK SENDGRID] To: {to} | Subject: {subject} | Body: {html}")
            return "mock-id-sendgrid"

        message = Mail(
            from_email=settings.SENDER_EMAIL,
            to_emails=to,
            subject=subject,
            html_content=html,
        )
        try:
            client = SendGridAPIClient(settings.SENDGRID_API_KEY)
            response = client.send(message)
            if response.status_code not in (200, 201, 202):
                raise MailError(f"SendGrid respondió con error: {response.status_code}")
            
            # SendGrid no siempre retorna el message ID de forma sencilla en la respuesta síncrona
            # Retornaremos un identificador genérico si fue exitoso
            return response.headers.get('X-Message-Id', 'sendgrid-success-id')
        except Exception as e:
            raise MailError(f"Error al contactar SendGrid: {e}")
