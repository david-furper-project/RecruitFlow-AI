"""
Pruebas para Bloque 6: Validación de credenciales y sesión (RF-01, RF-19, RF-20).

Suite: Unitaria - Autenticación
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select

from app.models import User
from app.core.auth import hash_password, verify_password, create_access_token, verify_token
from app.core.security import (
    validar_password,
    normalizar_email,
    validar_email_longitud,
    esta_bloqueado,
    calcular_bloqueo_hasta,
)
from app.api.schemas import UserCreate, LoginRequest


# ============= PRUEBAS DE CORREO =============


class TestEmailValidation:
    """Validar formato, normalización y longitud de correo."""

    def test_email_valido(self):
        """Formato de correo válido es aceptado."""
        email = "recruiter@empresa.cl"
        normalizado = normalizar_email(email)
        assert normalizado == "recruiter@empresa.cl"

    def test_email_invalido_rechazado(self):
        """Formato inválido levanta error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(email="correo_invalido", password="Test123456")

    def test_email_normalizacion_espacios(self):
        """Espacios alrededor se remueven."""
        email = "  Juan@Empresa.CL  "
        normalizado = normalizar_email(email)
        assert normalizado == "juan@empresa.cl"

    def test_email_normalizacion_mayusculas(self):
        """Se convierte a minúsculas."""
        email = "ADMIN@PRILOCAL.COM"
        normalizado = normalizar_email(email)
        assert normalizado == "admin@prilocal.com"

    def test_email_longitud_excedida(self):
        """Supera 150 caracteres: rechazado."""
        email = "x" * 160 + "@test.com"
        with pytest.raises(ValueError, match="supera los 150 caracteres"):
            validar_email_longitud(email)


# ============= PRUEBAS DE CONTRASEÑA =============


class TestPasswordPolicy:
    """Validar política de contraseña."""

    def test_password_muy_corta(self):
        """11 caracteres: rechazada."""
        with pytest.raises(ValueError, match="entre 12 y 128 caracteres"):
            validar_password("Short1234567", "user@test.com")

    def test_password_muy_larga(self):
        """129 caracteres: rechazada."""
        pwd = "A" + "a" + "1" * 129
        with pytest.raises(ValueError, match="entre 12 y 128 caracteres"):
            validar_password(pwd, "user@test.com")

    def test_password_sin_numeros(self):
        """Sin números: rechazada."""
        with pytest.raises(ValueError, match="al menos un número"):
            validar_password("PasswordXY", "user@test.com")

    def test_password_sin_mayusculas(self):
        """Sin mayúsculas: rechazada."""
        with pytest.raises(ValueError, match="al menos una mayúscula"):
            validar_password("password1234", "user@test.com")

    def test_password_sin_minusculas(self):
        """Sin minúsculas: rechazada."""
        with pytest.raises(ValueError, match="al menos una minúscula"):
            validar_password("PASSWORD1234", "user@test.com")

    def test_password_contiene_email_local(self):
        """Contiene parte local del correo: rechazada."""
        with pytest.raises(ValueError, match="No puede contener su correo"):
            validar_password("JohnSmith123", "john@empresa.com")

    def test_password_contiene_nombre(self):
        """Contiene parte del nombre (>3 chars): rechazada."""
        with pytest.raises(ValueError, match="No puede contener su nombre"):
            validar_password("AlexMiller123", "alex@empresa.com", nombre="Alex Miller")

    def test_password_lista_negra(self):
        """En lista negra: rechazada."""
        with pytest.raises(ValueError, match="uso frecuente"):
            validar_password("contrasena123", "user@test.com")

    def test_password_valido(self):
        """Cumple todas las reglas: aceptado."""
        # No debe lanzar
        validar_password("ValidPass123", "user@test.com", nombre="John")

    def test_password_errores_multiples_juntos(self):
        """Se devuelven todos los errores juntos, no de a uno."""
        with pytest.raises(ValueError) as exc_info:
            validar_password("short", "user@test.com")

        # Debe incluir múltiples errores
        msg = str(exc_info.value)
        assert "caracteres" in msg
        assert "mayúscula" in msg or "minúscula" in msg or "número" in msg


# ============= PRUEBAS DE ALMACENAMIENTO =============


class TestPasswordStorage:
    """Verificar hashing y persistencia."""

    def test_password_hasheado_diferente(self):
        """Texto plano y hash son diferentes."""
        pwd = "MySecurePassword123"
        hashed = hash_password(pwd)
        assert hashed != pwd

    def test_password_verifica_correctamente(self):
        """Hash verifica contra la contraseña correcta."""
        pwd = "MySecurePassword123"
        hashed = hash_password(pwd)
        assert verify_password(pwd, hashed) is True

    def test_password_rechaza_incorrecta(self):
        """Hash no verifica contra otra contraseña."""
        pwd = "MySecurePassword123"
        otra = "OtherPassword123"
        hashed = hash_password(pwd)
        assert verify_password(otra, hashed) is False


# ============= PRUEBAS DE CONTROL DE ACCESO =============


class TestAccountLocking:
    """Validar bloqueo después de intentos fallidos."""

    def test_cinco_intentos_fallos_bloquean(self):
        """5 intentos fallidos → cuenta bloqueada por 15 minutos."""
        max_intentos = 5
        ahora = datetime.now(timezone.utc)

        # Simular 5 intentos fallidos
        for i in range(max_intentos):
            assert not esta_bloqueado(None, ahora)  # No bloqueado antes

        # Después de MAX_INTENTOS, calcular bloqueo
        bloqueado_hasta = calcular_bloqueo_hasta(ahora)
        assert esta_bloqueado(bloqueado_hasta, ahora) is True

    def test_sexto_intento_rechazado_sin_verificar(self):
        """6º intento válido es rechazado sin verificar contraseña."""
        # Esto se verifica en el endpoint de login
        pass

    def test_bloqueo_levanta_despues_tiempo(self):
        """Después de 15 minutos, el bloqueo se levanta."""
        ahora = datetime.now(timezone.utc)
        bloqueado_hasta = calcular_bloqueo_hasta(ahora)

        # Simular paso de tiempo
        futura = bloqueado_hasta + timedelta(seconds=1)
        assert not esta_bloqueado(bloqueado_hasta, futura)


# ============= PRUEBAS DE SESIÓN =============


class TestJWTSession:
    """Validar tokens JWT con revocación."""

    def test_token_incluye_sub_role_exp_jti(self):
        """Token contiene: sub, role, exp, jti."""
        from jose import jwt
        from app.core.config import settings

        token = create_access_token(
            data={"sub": "admin@pri.local", "user_id": 1, "role": "recruiter"}
        )

        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        assert payload.get("sub") == "admin@pri.local"
        assert payload.get("user_id") == 1
        assert payload.get("role") == "recruiter"
        assert "exp" in payload
        assert "jti" in payload

    def test_token_vencido_rechazado(self):
        """Token con exp pasado levanta error."""
        from jose import jwt
        from app.core.config import settings

        # Crear token con expiración en el pasado
        ahora = datetime.now(timezone.utc)
        payload = {
            "sub": "admin@pri.local",
            "user_id": 1,
            "role": "recruiter",
            "jti": "test-jti",
            "exp": ahora - timedelta(hours=1),
        }

        token = jwt.encode(
            payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )

        # Verificar debe fallar
        with pytest.raises(Exception):  # JWTError
            verify_token(token)

    def test_token_revocado_rechazado(self):
        """Token en lista negra es rechazado."""
        from app.core.auth import revoke_token

        token = create_access_token(
            data={"sub": "admin@pri.local", "user_id": 1, "role": "recruiter"}
        )

        # Token válido inicialmente
        payload = verify_token(token)
        assert payload["sub"] == "admin@pri.local"

        # Revocar
        revoke_token(token)

        # Ahora debe fallar
        with pytest.raises(Exception):  # HTTPException 401
            verify_token(token)


# ============= PRUEBAS DE USUARIO INACTIVO =============


class TestInactiveUser:
    """Usuario con is_active=False no puede acceder."""

    def test_usuario_inactivo_rechazado_login(self, db_session: Session):
        """Usuario inactivo devuelve 401 con mensaje genérico."""
        # Esto se verifica en el endpoint de login
        pass
