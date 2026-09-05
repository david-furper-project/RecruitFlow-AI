from sqlmodel import Session, select

from app.models import Application, SourcingProspect


APPLICATION_ORIGINS = {"pri", "application_link", "sourcing"}

SOURCE_LABELS = {
    "linkedin": "LinkedIn",
    "computrabajo": "Computrabajo",
    "laborum": "Laborum",
    "referido": "Referido",
    "otro": "Otro origen",
}


def application_origin_label(session: Session, application: Application) -> str:
    if application.origin == "sourcing":
        prospect = session.exec(
            select(SourcingProspect).where(
                SourcingProspect.candidate_profile_id == application.candidate_id,
                SourcingProspect.job_offer_id == application.job_offer_id,
            )
        ).first()
        if prospect is not None:
            return f"{SOURCE_LABELS.get(prospect.source, prospect.source.title())} / Sourcing"
        return "Sourcing de talento"
    if application.origin == "application_link":
        return "Link de postulación"
    return "Desde PRI"


def sourcing_origin_labels(session: Session, candidate_id: int) -> list[str]:
    prospects = session.exec(
        select(SourcingProspect).where(SourcingProspect.candidate_profile_id == candidate_id)
    ).all()
    return list(dict.fromkeys(
        f"{SOURCE_LABELS.get(prospect.source, prospect.source.title())} / Sourcing"
        for prospect in prospects
    ))
