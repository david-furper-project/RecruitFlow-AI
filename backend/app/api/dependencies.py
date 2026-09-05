from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.auth import verify_token
from app.db.session import get_session
from app.models import User


bearer_scheme = HTTPBearer(auto_error=False)


async def ensure_single_cv_file(request: Request) -> None:
    """Reject repeated ``file`` parts on endpoints that accept one CV."""
    form = await request.form()
    uploaded_files = [
        item
        for item in form.getlist("file")
        if isinstance(item, StarletteUploadFile)
    ]
    if len(uploaded_files) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes adjuntar exactamente un CV por postulación.",
        )


def require_recruiter(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida.")
    payload = verify_token(credentials.credentials)
    user = session.get(User, payload.get("user_id"))
    if user is None or not user.is_active or user.role not in {"recruiter", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso de reclutador requerido.")
    return user
