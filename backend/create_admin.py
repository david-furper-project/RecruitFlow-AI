"""
Script para crear el usuario administrador por defecto.
Ejecutar desde el backend: python create_admin.py
"""

from sqlmodel import Session, select
from app.db.session import engine
from app.models import User
from app.core.auth import hash_password


def create_admin_user():
    """Crear un usuario admin con email: admin@pri.local y contraseña: admin"""
    
    with Session(engine) as session:
        # Verificar si el admin ya existe
        statement = select(User).where(User.email == "admin@pri.local")
        existing_admin = session.exec(statement).first()
        
        if existing_admin:
            print("✓ El usuario admin@pri.local ya existe en la base de datos.")
            return
        
        # Crear admin
        admin_user = User(
            email="admin@pri.local",
            password_hash=hash_password("admin"),
            role="recruiter"
        )
        
        session.add(admin_user)
        session.commit()
        session.refresh(admin_user)
        
        print("✓ Usuario admin creado exitosamente")
        print(f"  Email: admin@pri.local")
        print(f"  Contraseña: admin")
        print(f"  Rol: recruiter")
        print(f"  ID: {admin_user.id}")


if __name__ == "__main__":
    create_admin_user()
