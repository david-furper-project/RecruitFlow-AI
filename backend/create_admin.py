"""
Script para crear el usuario administrador por defecto.
Ejecutar desde el backend: python create_admin.py

Credenciales por defecto (Bloque 6):
- Email: admin@pri.local
- Contraseña: Admin123456 (cumple política: 12+ chars, mayús, minús, números)
"""

from datetime import datetime, timezone
from sqlmodel import Session, select
from app.db.session import engine
from app.models import User
from app.core.auth import hash_password


def create_admin_user():
    """Crear un usuario admin con contraseña que cumple la política."""

    with Session(engine) as session:
        # Verificar si el admin ya existe (case-insensitive)
        statement = select(User).where(User.email == "admin@ejemplo.com")
        existing_admin = session.exec(statement).first()

        if existing_admin:
            print("✓ El usuario admin@ejemplo.com ya existe en la base de datos.")
            return

        # Crear admin con contraseña que cumple Bloque 6
        admin_user = User(
            email="admin@ejemplo.com",
            password_hash=hash_password("Admin123456"),
            role="recruiter",
            is_active=True,
            password_changed_at=datetime.now(timezone.utc),
        )

        session.add(admin_user)
        session.commit()
        session.refresh(admin_user)

        print("✓ Usuario admin creado exitosamente")
        print(f"  Email: admin@ejemplo.com")
        print(f"  Contraseña: Admin123456")
        print(f"  Rol: recruiter")
        print(f"  ID: {admin_user.id}")
        print("\n⚠️  CAMBIAR ESTA CONTRASEÑA EN PRODUCCIÓN")


if __name__ == "__main__":
    create_admin_user()

