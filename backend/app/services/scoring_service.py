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


def _build_interview_questions(candidate: CandidateProfile, job_offer: JobOffer) -> str:
    questions = []
    required_keywords = [
        keyword.strip()
        for keyword in (job_offer.requirements or "").split(",")
        if keyword.strip()
    ]
    if required_keywords:
        candidate_text = (candidate.tech_stack or "").lower()
        missing = [keyword for keyword in required_keywords if keyword.lower() not in candidate_text]
        for keyword in missing[:3]:
            questions.append(
                f"¿Podrías contarme más sobre tu experiencia práctica con {keyword} y cómo la has aplicado en proyectos reales?"
            )

    if not questions:
        questions.extend([
            "¿Podrías describir un proyecto reciente en el que hayas trabajado con tecnologías similares a esta vacante?",
            "¿Qué entregables típicos has liderado en equipos de ingeniería o producto?",
            "¿Qué te gustaría aprender o profundizar en este rol para sumar a la posición?",
        ])

    return "\n".join(questions[:5])


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
    interview_questions = _build_interview_questions(candidate, job_offer)

    evaluation = Evaluation(
        application_id=application.id,
        suggested_category=category,
        explanation=explanation,
        interview_questions=interview_questions,
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
        "score": score,
        "category": category,
        "explanation": explanation,
        "interview_questions": interview_questions,
    }

def async_evaluate_application(application_id: int):
    """
    Background task wrapper for evaluate_application.
    Opens its own DB session to avoid interfering with the request session.
    """
    from app.db.session import engine
    from sqlmodel import Session
    
    with Session(engine) as session:
        try:
            evaluate_application(session, application_id)
        except Exception as e:
            print(f"Error in background evaluate_application: {e}")

def register_decision(session: Session, application_id: int, user_id: int, action: str, discrepancy_reason: Optional[str]) -> Decision:
    if action not in {"avanzar", "descartar", "reservar"}:
        raise ValueError(f"Action '{action}' no válido")

    application = session.get(Application, application_id)
    if application is None:
        raise ValueError("Application not found")
        
    if action in {"avanzar", "reservar"} and application.outcome is not None:
        raise ValueError("No se puede avanzar ni reservar una postulación que ya tiene un resultado final.")

    from app.models import PipelineStage
    current_stage = session.get(PipelineStage, application.current_stage_id)
    if not current_stage:
        raise ValueError("La postulación no tiene una etapa actual válida.")

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
            "no_apto": {"descartar"},
        }
        if action not in allowed_by_category.get(category, set()):
            if discrepancy_reason is None or not discrepancy_reason.strip():
                raise ValueError("Se requiere discrepancy_reason cuando la decisión contradice la sugerencia.")

    from_stage_id = current_stage.id
    to_stage_id = current_stage.id

    if action == "avanzar":
        if current_stage.kind == "final":
            raise ValueError("No se puede avanzar desde la etapa final.")
        next_stage = session.exec(
            select(PipelineStage)
            .where(PipelineStage.job_offer_id == application.job_offer_id, PipelineStage.order_index > current_stage.order_index)
            .order_by(PipelineStage.order_index.asc())
        ).first()
        if not next_stage:
            raise ValueError("No hay más etapas disponibles para avanzar.")
        to_stage_id = next_stage.id
        application.current_stage_id = to_stage_id
        if next_stage.kind == "final":
            application.outcome = "contratado"
    elif action == "descartar":
        application.outcome = "descartado"
    elif action == "reservar":
        application.outcome = "reservado"

    decision = Decision(
        application_id=application_id,
        user_id=user_id,
        action=action,
        discrepancy_reason=discrepancy_reason,
        from_stage_id=from_stage_id,
        to_stage_id=to_stage_id,
    )
    session.add(decision)
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
    if application.outcome is not None:
        decision = session.exec(
            select(Decision)
            .where(Decision.application_id == application_id)
            .order_by(Decision.decided_at.desc())
        ).first()
        if decision is None:
            raise ValueError("Ninguna postulación puede alcanzar un estado final sin una fila en decision.")


def get_application_ranking(
    session: Session, 
    job_offer_id: int, 
    stage_id: Optional[int] = None, 
    outcome: Optional[str] = None,
    top_percent: Optional[int] = None,
    source: Optional[str] = None
) -> Dict[str, Any]:
    from app.models import PipelineStage
    offer = session.get(JobOffer, job_offer_id)
    if not offer:
        raise ValueError("Job offer not found")

    stages_db = session.exec(
        select(PipelineStage)
        .where(PipelineStage.job_offer_id == job_offer_id)
        .order_by(PipelineStage.order_index)
    ).all()
    
    rows = session.exec(
        select(Application, CandidateProfile, Evaluation)
        .join(CandidateProfile, CandidateProfile.id == Application.candidate_id)
        .outerjoin(Evaluation, Evaluation.application_id == Application.id)
        .where(Application.job_offer_id == job_offer_id)
        .order_by(Application.similarity_score.desc())
    ).all()

    stages_response = [{"id": s.id, "name": s.name, "order_index": s.order_index, "kind": s.kind, "count": 0} for s in stages_db]
    stages_map = {s["id"]: s for s in stages_response}
    
    discarded_count = 0
    hired_count = 0
    all_active_count = 0
    
    filtered_rows = []
    
    total_for_percent = len([r for r in rows if r[0].outcome is None])
    cutoff_index = int(total_for_percent * (top_percent / 100.0)) if top_percent else len(rows)
    
    active_idx = 0
    for app, cand, ev in rows:
        if app.outcome == "descartado":
            discarded_count += 1
        elif app.outcome == "contratado":
            hired_count += 1
        else:
            all_active_count += 1
            if app.current_stage_id in stages_map:
                stages_map[app.current_stage_id]["count"] += 1
                
        passes = True
        if outcome is not None:
            if app.outcome != outcome:
                passes = False
        else:
            # If no outcome filter, usually exclude discarded and hired unless specified
            if app.outcome is not None:
                passes = False
                
        if stage_id and app.current_stage_id != stage_id:
            passes = False
            
        is_top = False
        if app.outcome is None:
            if top_percent:
                if active_idx < cutoff_index:
                    is_top = True
            else:
                is_top = True
            active_idx += 1
        
        if top_percent and not is_top:
            passes = False

        if passes:
            filtered_rows.append((app, cand, ev))

    ranked_rows = []
    for app, cand, ev in filtered_rows:
        ranked_rows.append({
            "application_id": app.id,
            "candidate_id": cand.id,
            "full_name": cand.full_name,
            "similarity_score": app.similarity_score,
            "suggested_category": ev.suggested_category if ev else "no_apto",
            "explanation": ev.explanation if ev else "Sin evaluación",
            "interview_questions": ev.interview_questions if ev else None,
            "status": app.status,
            "current_stage_id": app.current_stage_id,
            "outcome": app.outcome,
            "career_summary": cand.career_summary,
            "tech_stack": cand.tech_stack,
        })

    total = len(ranked_rows)
    for index, row in enumerate(ranked_rows, start=1):
        row["rank_position"] = index
        row["percentile"] = round(((total - index) / total) * 100, 2) if total else 0.0

    return {
        "job_offer_id": job_offer_id,
        "stages": stages_response,
        "counts": {
            "all_active": all_active_count,
            "discarded": discarded_count,
            "hired": hired_count
        },
        "candidates": ranked_rows
    }
