from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select
from app.db.session import get_session
from app.models import User
from app.core.auth import verify_password, create_access_token, hash_password


router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    email: str
    role: str


class CreateRecruiterRequest(BaseModel):
    email: str
    password: str


class RecruiterResponse(BaseModel):
    id: int
    email: str
    role: str


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, session: Session = Depends(get_session)):
    """
    Login para reclutadores.
    Credenciales por defecto: admin@pri.local / admin
    """
    # Buscar el usuario por email
    statement = select(User).where(User.email == request.email)
    user = session.exec(statement).first()
    
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )
    
    # Verificar que sea reclutador
    if user.role != "recruiter":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los reclutadores pueden acceder",
        )
    
    # Crear token JWT
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        role=user.role,
    )


@router.post("/recruiter/create", response_model=RecruiterResponse)
def create_recruiter(request: CreateRecruiterRequest, session: Session = Depends(get_session)):
    """
    Crear un nuevo reclutador.
    Solo para uso administrativo (debe ejecutarse directamente en BD o por admin).
    """
    # Verificar que el email no exista
    statement = select(User).where(User.email == request.email)
    existing_user = session.exec(statement).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya existe",
        )
    
    # Crear nuevo reclutador
    hashed_password = hash_password(request.password)
    new_recruiter = User(
        email=request.email,
        password_hash=hashed_password,
        role="recruiter"
    )
    
    session.add(new_recruiter)
    session.commit()
    session.refresh(new_recruiter)
    
    return RecruiterResponse(
        id=new_recruiter.id,
        email=new_recruiter.email,
        role=new_recruiter.role,
    )
