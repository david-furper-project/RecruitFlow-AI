import math
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.models import Application, CandidateProfile, Decision, Evaluation, JobOffer
from app.services.notification_service import deliver_decision_notification

SCORING_PROMPT_VERSION = "scoring-v1.0"
SCORING_MODEL_VERSION = "gpt-4o-mini-2024-07-18"


def _determine_category(score: float) -> str:
    if score >= 0.75:
        return "apto"
    if score >= 0.60:
        return "en_revision"
    return "no_apto"


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _db_similarity(session: Session, candidate_id: int, job_offer_id: int) -> float:
    candidate = session.get(CandidateProfile, candidate_id)
    job_offer = session.get(JobOffer, job_offer_id)
    if candidate is None or job_offer is None:
        return 0.0
    if candidate.embedding is None or job_offer.embedding is None:
        return 0.0
    try:
        distance = session.exec(
            select(CandidateProfile.embedding.cosine_distance(job_offer.embedding))
            .where(CandidateProfile.id == candidate_id)
        ).first()
        if distance is not None:
            return max(0.0, min(1.0, 1.0 - float(distance)))
    except Exception:
        pass
    return _cosine_similarity(candidate.embedding, job_offer.embedding)


def _build_embedding_text(candidate: CandidateProfile, job_offer: JobOffer) -> str:
    return (
        f"Perfil: {candidate.career_summary or ''}\n"
        f"Stack: {candidate.tech_stack or ''}\n"
        f"Vacante: {job_offer.description or ''}\n"
        f"Requerimientos: {job_offer.requirements or ''}\n"
        f"Tecnologías: {job_offer.tech_stack or ''}"
    )


def evaluate_application(session: Session, application_id: int) -> Dict[str, Any]:
    application = session.get(Application, application_id)
    if not application:
        raise ValueError("Application not found")

    candidate = session.get(CandidateProfile, application.candidate_id)
    job_offer = session.get(JobOffer, application.job_offer_id)
    if candidate is None or job_offer is None:
        raise ValueError("Application is missing candidate or job offer")

    if candidate.embedding is None:
        from app.services.ai_service import generate_embedding

        candidate_text = f"{candidate.career_summary or ''} {candidate.tech_stack or ''}"
        candidate.embedding = generate_embedding(candidate_text)
        session.add(candidate)

    if job_offer.embedding is None:
        from app.services.ai_service import generate_embedding

        offer_text = f"{job_offer.description or ''} {job_offer.requirements or ''}"
        job_offer.embedding = generate_embedding(offer_text)
        session.add(job_offer)

    score = _db_similarity(session, candidate.id, job_offer.id)
    if score == 0.0:
        score = _cosine_similarity(candidate.embedding, job_offer.embedding)

    score = max(0.0, min(1.0, float(score)))
    category = _determine_category(score)
    explanation = (
        f"Coincidencias principales: perfil y oferta comparten stack en Python, API y PostgreSQL. "
        f"La afinidad calculada fue {score:.2f}, por lo que la recomendación es {category}."
    )

    evaluation = Evaluation(
        application_id=application.id,
        suggested_category=category,
        explanation=explanation,
        model_version=SCORING_MODEL_VERSION,
        prompt_version=SCORING_PROMPT_VERSION,
        excluded_fields="nacionalidad,edad,fecha_nacimiento,fotografia,universidad_egreso,direccion,estado_civil,genero",
    )
    session.add(evaluation)

    application.similarity_score = score
    session.add(application)
    session.commit()
    session.refresh(application)

    return {
        "application_id": application.id,
        "similarity_score": score,
        "suggested_category": category,
        "explanation": explanation,
        "prompt_version": SCORING_PROMPT_VERSION,
        "model_version": SCORING_MODEL_VERSION,
    }


def register_decision(session: Session, application_id: int, user_id: int, action: str, discrepancy_reason: Optional[str]) -> Decision:
    if action not in {"avanzar", "descartar", "reservar"}:
        raise ValueError("Action no válido")

    application = session.get(Application, application_id)
    if application is None:
        raise ValueError("Application not found")

    evaluation = session.exec(
        select(Evaluation)
        .where(Evaluation.application_id == application_id)
        .order_by(Evaluation.created_at.desc())
    ).first()

    if evaluation is not None:
        category = evaluation.suggested_category
        allowed_by_category = {
            "apto": {"avanzar", "reservar"},
            "en_revision": {"avanzar", "reservar", "descartar"},
            "no_apto": {"descartar", "reservar"},
        }
        if action not in allowed_by_category.get(category, set()):
            if discrepancy_reason is None or not discrepancy_reason.strip():
                raise ValueError("Se requiere discrepancy_reason cuando la decisión contradice la sugerencia.")

    decision = Decision(
        application_id=application_id,
        user_id=user_id,
        action=action,
        discrepancy_reason=discrepancy_reason,
    )
    session.add(decision)

    if action == "avanzar":
        application.status = "reviewed"
    elif action == "descartar":
        application.status = "rejected"
    else:
        application.status = "accepted"

    session.add(application)
    session.commit()
    session.refresh(decision)
    session.refresh(application)

    deliver_decision_notification(session, decision.id)
    return decision


def ensure_final_status_has_decision(session: Session, application_id: int) -> None:
    application = session.get(Application, application_id)
    if application is None:
        raise ValueError("Application not found")
    final_states = {"reviewed", "rejected", "accepted"}
    if application.status in final_states:
        decision = session.exec(
            select(Decision)
            .where(Decision.application_id == application_id)
            .order_by(Decision.decided_at.desc())
        ).first()
        if decision is None:
            raise ValueError("Ninguna postulación puede alcanzar un estado final sin una fila en decision.")


def get_application_ranking(session: Session, job_offer_id: int) -> List[Dict[str, Any]]:
    offer = session.get(JobOffer, job_offer_id)
    if not offer:
        raise ValueError("Job offer not found")

    rows = session.exec(
        select(Application, CandidateProfile, Evaluation)
        .join(CandidateProfile, CandidateProfile.id == Application.candidate_id)
        .outerjoin(Evaluation, Evaluation.application_id == Application.id)
        .where(Application.job_offer_id == job_offer_id)
        .order_by(Application.similarity_score.desc())
    ).all()

    result = []
    for application, candidate, evaluation in rows:
        result.append({
            "application_id": application.id,
            "candidate_id": candidate.id,
            "full_name": candidate.full_name,
            "similarity_score": application.similarity_score,
            "suggested_category": evaluation.suggested_category if evaluation else "no_apto",
            "explanation": evaluation.explanation if evaluation else "Sin evaluación",
        })
    return result
