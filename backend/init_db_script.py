"""
Script para inicializar la base de datos.
Ejecutar: python init_db_script.py
"""

from app.db.session import init_db

if __name__ == "__main__":
    print("Inicializando base de datos...")
    init_db()
    print("✓ Base de datos inicializada correctamente")
    print("✓ Admin creado: admin@ejemplo.com / Admin123456")
