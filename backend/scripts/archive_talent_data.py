"""Archive and anonymize operational talent data, preserving mandatory audits."""

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlmodel import Session, select

from app.db.session import engine, init_db
from app.models import User
from app.services.talent_cleanup_service import archive_operational_talent_data


def _delete_local_resume_file(resume_url: str) -> bool:
    parsed_path = urlparse(resume_url).path
    marker = "/uploads/"
    if marker not in parsed_path:
        return False
    relative_path = Path(parsed_path.split(marker, 1)[1])
    deleted = False
    for uploads_root in (BACKEND_ROOT / "uploads", PROJECT_ROOT / "uploads"):
        target = (uploads_root / relative_path).resolve()
        if uploads_root.resolve() not in target.parents:
            raise RuntimeError(f"Ruta de CV fuera del directorio permitido: {target}")
        if target.is_file():
            target.unlink()
            deleted = True
    return deleted


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archiva y anonimiza Banco de talento y elimina datos de sourcing."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirma la limpieza destructiva de datos operativos y archivos de CV.",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Se requiere --confirm para ejecutar la limpieza.")

    init_db()
    with Session(engine) as session:
        requester = session.exec(
            select(User)
            .where(User.role.in_(["recruiter", "admin"]), User.is_active.is_(True))
            .order_by(User.id.asc())
        ).first()
        result = archive_operational_talent_data(
            session,
            requested_by_user_id=requester.id if requester else None,
        )

    deleted_files = 0
    missing_or_remote_files = 0
    for resume_url in result.resume_urls:
        if _delete_local_resume_file(resume_url):
            deleted_files += 1
        else:
            missing_or_remote_files += 1

    print(f"Perfiles archivados y anonimizados: {result.archived_candidates}")
    print(f"Postulaciones archivadas: {result.archived_applications}")
    print(f"Prospectos de sourcing eliminados: {result.deleted_sourcing_prospects}")
    print(f"Versiones de CV eliminadas: {result.deleted_resume_versions}")
    print(f"Registros de privacidad creados: {result.privacy_logs_created}")
    print(f"Archivos locales de CV eliminados: {deleted_files}")
    print(f"Archivos remotos o ya ausentes: {missing_or_remote_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
