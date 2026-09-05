from app.core.config import settings
from .base import MailError, MailProvider
from .sendgrid_provider import SendGridProvider
from .brevo_provider import BrevoProvider
from .mailpit_provider import MailpitProvider

def get_mail_provider() -> MailProvider:
    provider = settings.MAIL_PROVIDER.strip().lower()
    
    if provider == "brevo":
        return BrevoProvider()
    elif provider == "sendgrid":
        return SendGridProvider()
    elif provider == "mailpit":
        return MailpitProvider()
    raise MailError(f"Proveedor de correo no soportado: {settings.MAIL_PROVIDER}.")
