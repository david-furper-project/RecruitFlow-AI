from app.core.config import settings
from .base import MailProvider
import uuid

class MailpitProvider(MailProvider):
    def send(self, to: str, subject: str, html: str) -> str:
        # Aquí normalmente se conectaría por SMTP al localhost:1025 si se estuviera
        # usando la imagen de Docker de Mailpit. Para mantener el MVP simple, lo mockeamos
        # imprimiendo en consola de forma estructurada.
        
        msg_id = f"mailpit-mock-{uuid.uuid4().hex[:8]}"
        print("="*50)
        print(f"📧 [MAILPIT MOCK] Enviando correo:")
        print(f"ID: {msg_id}")
        print(f"De: {settings.MAIL_FROM_NAME} <{settings.MAIL_FROM_EMAIL}>")
        print(f"Para: {to}")
        print(f"Asunto: {subject}")
        print("-" * 50)
        print(html)
        print("="*50)
        
        return msg_id
