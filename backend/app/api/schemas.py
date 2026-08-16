"""
Esquemas Pydantic para autenticación (entrada y salida).
Valida y normaliza en capas, no en endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

from app.core.security import (
    normalizar_email,
    validar_email_longitud,
    validar_password,
)


class UserCreate(BaseModel):
    """Esquema para crear reclutador (registro)."""

    email: EmailStr
    password: str
    nombre: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email_field(cls, v: str) -> str:
        """Normalizar correo en el schema."""
        v = normalizar_email(v)
        v = validar_email_longitud(v)
        return v

    @field_validator("password", mode="after")
    @classmethod
    def validar_password_field(cls, v: str, info) -> str:
        """Validar contraseña contra política."""
        email = info.data.get("email", "")
        nombre = info.data.get("nombre", "")
        validar_password(v, email, nombre)
        return v


class LoginRequest(BaseModel):
    """Esquema para login."""

    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email_field(cls, v: str) -> str:
        """Normalizar correo en el schema."""
        v = normalizar_email(v)
        v = validar_email_longitud(v)
        return v


class UserRead(BaseModel):
    """Esquema de respuesta (NO incluye password_hash)."""

    id: int
    email: str
    role: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Respuesta exitosa de login."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead
