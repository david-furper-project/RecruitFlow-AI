from abc import ABC, abstractmethod
from typing import Optional

class MailError(Exception):
    pass

class MailProvider(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, html: str) -> Optional[str]:
        """
        Envía un correo y retorna el ID del mensaje si el proveedor lo soporta, o None.
        Lanza MailError en caso de fallo.
        """
        pass
