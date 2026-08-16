import httpx
from app.core.config import settings
from .base import MailProvider, MailError

URL = "https://api.brevo.com/v3/smtp/email"

class BrevoProvider(MailProvider):
    def send(self, to: str, subject: str, html: str) -> str:
        payload = {
            "sender": {"email": settings.MAIL_FROM_EMAIL,
                       "name": settings.MAIL_FROM_NAME},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        }
        headers = {
            "api-key": settings.BREVO_API_KEY,
            "content-type": "application/json",
            "accept": "application/json",
        }
        try:
            r = httpx.post(URL, json=payload, headers=headers, timeout=15)
            r.raise_for_status()
            return r.json().get("messageId", "")
        except httpx.HTTPStatusError as e:
            raise MailError(f"Brevo respondió {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise MailError(f"Error de red al contactar Brevo: {e}")
