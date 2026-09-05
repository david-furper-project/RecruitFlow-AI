"""
Seguridad y validación centralizada para autenticación y autorización.
Implementa Bloque 6: Validación de credenciales y sesión.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

# Constantes de política de contraseña
MIN_PASSWORD_LEN = 12
MAX_PASSWORD_LEN = 128
MAX_EMAIL_LEN = 150
MAX_INTENTOS = 5
BLOQUEO_MINUTOS = 15

# Lista negra de contraseñas comunes (en español)
COMMON_PASSWORDS = {
    "contrasena123",
    "password123",
    "administrador1",
    "qwerty123456",
    "123456789012",
    "reclutamiento1",
    "admin123456",
    "recruiter123",
    "prueba1234567",
    "temporal123",
}


def normalizar_email(email: str) -> str:
    """Normalizar correo: strip y lowercase."""
    return email.strip().lower()


def validar_email_longitud(email: str) -> str:
    """Validar longitud del correo después de normalizar."""
    email = normalizar_email(email)
    if len(email) > MAX_EMAIL_LEN:
        raise ValueError(f"El correo supera los {MAX_EMAIL_LEN} caracteres.")
    return email


def validar_password(password: str, email: str, nombre: str = "") -> None:
    """
    Validar contraseña contra política.
    Devuelve lista de errores, no de a uno.

    Args:
        password: Contraseña en texto plano
        email: Correo normalizado del usuario
        nombre: Nombre completo (opcional)

    Raises:
        ValueError: Con mensaje de todos los errores concatenados
    """
    errores = []

    # 1. Longitud
    if not (MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN):
        errores.append(
            f"Debe tener entre {MIN_PASSWORD_LEN} y {MAX_PASSWORD_LEN} caracteres."
        )

    # 2. Mayúscula (acentos incluidos)
    if not re.search(r"[A-ZÁÉÍÓÚÑ]", password):
        errores.append("Debe incluir al menos una mayúscula.")

    # 3. Minúscula (acentos incluidos)
    if not re.search(r"[a-záéíóúñ]", password):
        errores.append("Debe incluir al menos una minúscula.")

    # 4. Número
    if not re.search(r"\d", password):
        errores.append("Debe incluir al menos un número.")

    # 5. No contener parte local del correo
    local = email.split("@")[0].lower()
    if local and local in password.lower():
        errores.append("No puede contener su correo.")

    # 6. No contener partes del nombre (> 3 caracteres)
    if nombre:
        for parte in nombre.split():
            if len(parte) > 3 and parte.lower() in password.lower():
                errores.append("No puede contener su nombre.")
                break

    # 7. No estar en lista negra
    if password.lower() in COMMON_PASSWORDS:
        errores.append("Es una contraseña de uso frecuente.")

    if errores:
        raise ValueError(" ".join(errores))


def calcular_bloqueo_hasta(ahora: datetime) -> datetime:
    """Calcular timestamp de desbloqueo: ahora + BLOQUEO_MINUTOS."""
    return ahora + timedelta(minutes=BLOQUEO_MINUTOS)


def esta_bloqueado(locked_until: Optional[datetime], ahora: datetime) -> bool:
    """Verificar si la cuenta está bloqueada."""
    return locked_until is not None and locked_until > ahora
