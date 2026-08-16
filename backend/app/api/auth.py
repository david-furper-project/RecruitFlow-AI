"""
Endpoints de autenticación: login, registro, logout.
Implementa Bloque 6: Validación de credenciales y sesión.
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import User
from app.core.auth import (
    verify_password,
    create_access_token,
    hash_password,
    verify_token,
    revoke_token,
)
from app.api.schemas import LoginRequest, LoginResponse, UserCreate, UserRead
from app.core.security import (
    validar_password,
    esta_bloqueado,
    calcular_bloqueo_hasta,
    MAX_INTENTOS,
)

router = APIRouter()


@router.post("/login", response_model=LoginResponse, status_code=200)
def login(request: LoginRequest, session: Session = Depends(get_session)):
    """
    Login de reclutador con control de acceso.

    Flujo:
    1. Normalizar correo y buscar usuario
    2. Si está bloqueado (locked_until > ahora), rechazar 423
    3. Si no existe o contraseña falla: incrementar failed_attempts, devolver 401
    4. Si alcanza MAX_INTENTOS: fijar locked_until y resetear contador
    5. Si is_active=False: devolver 401
    6. Si exitoso: resetear failed_attempts, limpiar locked_until, actualizar last_login_at

    Respuestas:
    - 200: OK + token
    - 401: Credenciales inválidas o cuenta inactiva
    - 423: Cuenta bloqueada temporalmente
    """
    ahora = datetime.now(timezone.utc)

    # 1. Normalizar correo y buscar usuario
    email_normalizado = request.email.lower().strip()
    statement = select(User).where(User.email == email_normalizado)
    user = session.exec(statement).first()

    # 2. Verificar bloqueo ANTES de validar contraseña
    if user and esta_bloqueado(user.locked_until, ahora):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cuenta bloqueada temporalmente. Intente en unos minutos.",
        )

    # 3. Validar contraseña (ejecutar contra hash ficticio si no existe usuario)
    password_valida = False
    if user:
        password_valida = verify_password(request.password, user.password_hash)

    # 4. Si falla: incrementar contador e intentar bloquear
    if not user or not password_valida:
        if user:
            user.failed_attempts += 1

            # Si alcanza MAX_INTENTOS, bloquear
            if user.failed_attempts >= MAX_INTENTOS:
                user.locked_until = calcular_bloqueo_hasta(ahora)
                user.failed_attempts = 0  # Resetear contador

            session.add(user)
            session.commit()

        # SIEMPRE devolver el mismo mensaje (seguridad)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    # 5. Si existe pero inactivo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    # 6. Exitoso: resetear intentos, limpiar bloqueo, actualizar login
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = ahora
    session.add(user)
    session.commit()

    # Emitir token
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role}
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post("/register", response_model=UserRead, status_code=201)
def register(request: UserCreate, session: Session = Depends(get_session)):
    """
    Registrar nuevo reclutador.

    Validaciones (ya en schema):
    - Email válido y normalizado
    - Correo único (caso-insensible)
    - Contraseña cumple política

    Respuestas:
    - 201: Reclutador creado
    - 409: Correo ya existe
    - 422: Validación fallida
    """
    email_normalizado = request.email.lower().strip()

    # Verificar unicidad (case-insensitive)
    statement = select(User).where(User.email == email_normalizado)
    if session.exec(statement).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo ya está registrado.",
        )

    # Crear usuario
    nuevo_recruiter = User(
        email=email_normalizado,
        password_hash=hash_password(request.password),
        role="recruiter",
        is_active=True,
        password_changed_at=datetime.now(timezone.utc),
    )

    session.add(nuevo_recruiter)
    session.commit()
    session.refresh(nuevo_recruiter)

    return UserRead.model_validate(nuevo_recruiter)


@router.post("/logout", status_code=204)
def logout(token: str, session: Session = Depends(get_session)):
    """
    Logout: revocar token.

    El token se extrae de headers (Authorization: Bearer <token>)
    via dependencia en main.
    """
    revoke_token(token)
    return None

