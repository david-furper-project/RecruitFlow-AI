"""
Autenticación: hashing, tokens JWT y lista de revocación.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Set
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.core.config import settings

# Configurar hashing con Argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Lista negra de tokens revocados (jti)
# En producción, usar Redis o base de datos
REVOKED_TOKENS: Set[str] = set()


def hash_password(password: str) -> str:
    """Hashear contraseña con Argon2."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña contra su hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Crear JWT token.

    Token incluye:
    - sub: email del usuario
    - user_id: id del usuario
    - role: rol del usuario
    - jti: ID único del token (para revocación)
    - exp: expiración
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            hours=settings.JWT_EXPIRATION_HOURS
        )

    # Generar jti único para revocación
    import uuid

    jti = str(uuid.uuid4())

    to_encode.update({"exp": expire, "jti": jti})

    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> dict:
    """
    Verificar y decodificar JWT token.

    Valida:
    - Firma
    - Expiración
    - Revocación (jti en lista negra)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        # Verificar si el token está revocado
        jti = payload.get("jti")
        if jti in REVOKED_TOKENS:
            raise credentials_exception

        return payload

    except JWTError:
        raise credentials_exception


def revoke_token(token: str) -> None:
    """Agregar token a lista negra (logout)."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        jti = payload.get("jti")
        if jti:
            REVOKED_TOKENS.add(jti)
    except JWTError:
        pass  # Token inválido, ignorar

