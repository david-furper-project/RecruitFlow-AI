from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlmodel import Session, select

from app.models import Application, CandidateProfile, Decision, Evaluation, JobOffer
from app.services.matching_service import (
    MATCHING_MODEL_VERSION,
    MATCHING_PROMPT_VERSION,
    affinity_category,
    affinity_explanation,
    candidate_profile_text,
    cosine_similarity,
    job_offer_text,
)
from app.services.application_origin_service import application_origin_label
from app.services.candidate_identity_service import is_internal_candidate_email, normalize_candidate_email

SCORING_PROMPT_VERSION = MATCHING_PROMPT_VERSION
SCORING_MODEL_VERSION = MATCHING_MODEL_VERSION


def _unavailable_evaluation_result(application: Application, message: str) -> Dict[str, Any]:
    return {
        "application_id": application.id,
        "score": None,
        "similarity_score": None,
        "category": None,
        "explanation": message,
        "interview_questions": None,
        "evaluation_status": "unavailable",
        "evaluation_message": message,
    }


def _determine_category(score: float) -> str:
    return affinity_category(score)


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
    return cosine_similarity(candidate.embedding, job_offer.embedding)


def evaluate_application(
    session: Session,
    application_id: int,
    *,
    skip_if_current: bool = False,
) -> Dict[str, Any]:
    application = session.get(Application, application_id)
    if not application or application.archived_at is not None:
        raise ValueError("Application not found")

    candidate = session.get(CandidateProfile, application.candidate_id)
    job_offer = session.get(JobOffer, application.job_offer_id)
    if candidate is None or candidate.archived_at is not None or job_offer is None:
        raise ValueError("Application is missing candidate or job offer")

    previous_evaluation = None
    if skip_if_current:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:application_id)"),
            {"application_id": application.id},
        )
        previous_evaluation = session.exec(
            select(Evaluation)
            .where(Evaluation.application_id == application.id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
        ).first()
        if (
            previous_evaluation
            and previous_evaluation.prompt_version == SCORING_PROMPT_VERSION
            and application.similarity_score is not None
            and application.evaluation_status == "available"
        ):
            return {
                "application_id": application.id,
                "score": application.similarity_score,
                "similarity_score": application.similarity_score,
                "category": previous_evaluation.suggested_category,
                "explanation": previous_evaluation.explanation,
                "interview_questions": previous_evaluation.interview_questions,
                "evaluation_status": "available",
                "evaluation_message": None,
            }
    else:
        previous_evaluation = session.exec(
            select(Evaluation)
            .where(Evaluation.application_id == application.id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
        ).first()

    from app.services.ai_service import (
        AI_EVALUATION_UNAVAILABLE_MESSAGE,
        EmbeddingProviderUnavailableError,
        generate_embedding,
    )

    needs_embedding_migration = bool(
        previous_evaluation
        and previous_evaluation.prompt_version != SCORING_PROMPT_VERSION
    )
    # Existing v1 evaluations used another scale and partial inputs. New records
    # already receive canonical vectors when their CV/offer is created.
    application.evaluation_status = "pending"
    application.evaluation_message = None
    session.add(application)
    session.commit()

    try:
        if candidate.embedding is None or needs_embedding_migration:
            candidate.embedding = generate_embedding(candidate_profile_text(candidate))
            session.add(candidate)
        if job_offer.embedding is None or needs_embedding_migration:
            job_offer.embedding = generate_embedding(job_offer_text(job_offer))
            session.add(job_offer)
        session.flush()
    except EmbeddingProviderUnavailableError:
        session.rollback()
        application = session.get(Application, application_id)
        if application and previous_evaluation:
            application.evaluation_status = "available"
        elif application:
            application.evaluation_status = "unavailable"
        if application:
            session.add(application)
            session.commit()
        raise

    score = _db_similarity(session, candidate.id, job_offer.id)
    percentage = round(score * 100, 2)
    category = _determine_category(score)
    explanation = affinity_explanation(percentage)
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
    application.evaluation_status = "available"
    application.evaluation_message = None
    session.add(application)
    session.commit()
    session.refresh(application)

    return {
        "application_id": application.id,
        "score": score,
        "similarity_score": score,
        "category": category,
        "explanation": explanation,
        "interview_questions": interview_questions,
        "evaluation_status": "available",
        "evaluation_message": None,
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
            evaluate_application(session, application_id, skip_if_current=True)
        except Exception as e:
            print(f"Error in background evaluate_application: {e}")

def register_decision(
    session: Session,
    application_id: int,
    user_id: int,
    action: str,
    discrepancy_reason: Optional[str],
    feedback: Optional[str] = None,
) -> Decision:
    if action not in {"avanzar", "descartar", "reservar"}:
        raise ValueError(f"Action '{action}' no válido")

    normalized_feedback = (feedback or "").strip() or None
    if action == "descartar" and normalized_feedback is not None and len(normalized_feedback) < 10:
        raise ValueError("El feedback debe contener al menos 10 caracteres.")
    if normalized_feedback and len(normalized_feedback) > 2000:
        raise ValueError("El feedback no puede superar los 2000 caracteres.")
    if action == "descartar" and normalized_feedback is None:
        raise ValueError("El feedback para el candidato es obligatorio al descartar una postulación.")
    normalized_discrepancy_reason = (discrepancy_reason or "").strip() or None

    application = session.get(Application, application_id)
    if application is None or application.archived_at is not None:
        raise ValueError("Application not found")
    if action == "descartar":
        candidate = application.candidate
        user_email = candidate.user.email if candidate and candidate.user else None
        contact_email = candidate.contact_email if candidate else None
        has_deliverable_email = any(
            normalize_candidate_email(email) is not None and not is_internal_candidate_email(email)
            for email in (user_email, contact_email)
            if email
        )
        if not has_deliverable_email:
            raise ValueError(
                "No se puede descartar la postulación porque el candidato no tiene un correo válido para recibir el feedback."
            )
        
    # Allow recovering discarded candidates by advancing them again
    if action in {"reservar"} and application.outcome is not None:
        raise ValueError("No se puede reservar una postulación que ya tiene un resultado final.")
    if action == "avanzar" and application.outcome == "contratado":
        raise ValueError("No se puede avanzar una postulación ya contratada.")
    # If advancing a discarded candidate, clear the outcome so they re-enter the pipeline
    if action == "avanzar" and application.outcome == "descartado":
        application.outcome = None

    from app.models import PipelineStage
    current_stage = session.get(PipelineStage, application.current_stage_id) if application.current_stage_id else None
    if not current_stage:
        stages = session.exec(
            select(PipelineStage)
            .where(PipelineStage.job_offer_id == application.job_offer_id)
            .order_by(PipelineStage.order_index.asc())
        ).all()
        if not stages:
            stages = [
                PipelineStage(job_offer_id=application.job_offer_id, name="Pendiente", order_index=1, kind="inicial"),
                PipelineStage(job_offer_id=application.job_offer_id, name="Preselección", order_index=2, kind="proceso"),
                PipelineStage(job_offer_id=application.job_offer_id, name="Entrevista", order_index=3, kind="proceso"),
                PipelineStage(job_offer_id=application.job_offer_id, name="Finalista", order_index=4, kind="final"),
            ]
            session.add_all(stages)
            session.flush()
        current_stage = stages[0]
        application.current_stage_id = current_stage.id
        session.add(application)

    evaluation = session.exec(
        select(Evaluation)
        .where(Evaluation.application_id == application_id)
        .order_by(Evaluation.created_at.desc())
    ).first()

    if evaluation is not None:
        category = evaluation.suggested_category
        allowed_by_category = {
            "apto": {"avanzar", "reservar"},
            "en_revision": {"avanzar", "reservar"},
            "no_apto": {"descartar"},
        }
        if action not in allowed_by_category.get(category, set()):
            normalized_discrepancy_reason = normalized_discrepancy_reason or normalized_feedback
            if normalized_discrepancy_reason is None:
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
            job_offer = session.get(JobOffer, application.job_offer_id)
            if job_offer is not None and job_offer.status != "closed_final":
                job_offer.status = "closed"
                session.add(job_offer)
    elif action == "descartar":
        application.outcome = "descartado"
    elif action == "reservar":
        application.outcome = "reservado"

    decision = Decision(
        application_id=application_id,
        user_id=user_id,
        action=action,
        discrepancy_reason=normalized_discrepancy_reason,
        feedback=normalized_feedback,
        from_stage_id=from_stage_id,
        to_stage_id=to_stage_id,
    )
    session.add(decision)
    session.add(application)
    session.flush()
    from app.services.notification_service import ensure_decision_notification_record

    ensure_decision_notification_record(session, decision, commit=False)
    session.commit()
    session.refresh(decision)
    session.refresh(application)

    return decision


def register_finalist_decision(
    session: Session,
    application_id: int,
    user_id: int,
    discrepancy_reason: str,
) -> Decision:
    """Registra en una sola decisión auditable la selección explícita de finalista."""
    from app.models import PipelineStage

    application = session.get(Application, application_id)
    if application is None or application.archived_at is not None:
        raise ValueError("Application not found")
    final_stage = session.exec(
        select(PipelineStage)
        .where(
            PipelineStage.job_offer_id == application.job_offer_id,
            PipelineStage.kind == "final",
        )
        .order_by(PipelineStage.order_index.asc())
    ).first()
    if final_stage is None:
        raise ValueError("La vacante no tiene una etapa final configurada.")
    current_stage = session.get(PipelineStage, application.current_stage_id) if application.current_stage_id else None
    if current_stage is None:
        current_stage = session.exec(
            select(PipelineStage)
            .where(PipelineStage.job_offer_id == application.job_offer_id)
            .order_by(PipelineStage.order_index.asc())
        ).first()
    if current_stage is None:
        raise ValueError("La vacante no tiene etapas configuradas.")

    if current_stage.id == final_stage.id and application.outcome == "contratado":
        existing = session.exec(
            select(Decision)
            .where(Decision.application_id == application.id)
            .order_by(Decision.decided_at.desc())
        ).first()
        if existing is None:
            raise ValueError("El estado finalista no tiene una decisión asociada.")
        return existing

    application.current_stage_id = final_stage.id
    application.outcome = "contratado"
    job_offer = session.get(JobOffer, application.job_offer_id)
    if job_offer is not None and job_offer.status != "closed_final":
        job_offer.status = "closed"
        session.add(job_offer)
    decision = Decision(
        application_id=application.id,
        user_id=user_id,
        action="avanzar",
        discrepancy_reason=discrepancy_reason,
        from_stage_id=current_stage.id,
        to_stage_id=final_stage.id,
    )
    session.add(application)
    session.add(decision)
    session.flush()
    from app.services.notification_service import ensure_decision_notification_record

    ensure_decision_notification_record(session, decision, commit=False)
    session.commit()
    session.refresh(application)
    session.refresh(decision)
    return decision


def ensure_final_status_has_decision(session: Session, application_id: int) -> None:
    application = session.get(Application, application_id)
    if application is None:
        raise ValueError("Application not found")
    legacy_final_statuses = {"accepted", "rejected", "hired", "contratado", "descartado"}
    if application.outcome is not None or application.status in legacy_final_statuses:
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
    
    # Get all applications with candidates
    app_cand_rows = session.exec(
        select(Application, CandidateProfile)
        .join(CandidateProfile, CandidateProfile.id == Application.candidate_id)
        .where(
            Application.job_offer_id == job_offer_id,
            Application.archived_at.is_(None),
            CandidateProfile.archived_at.is_(None),
        )
        .order_by(Application.similarity_score.desc().nullslast())
    ).all()

    # Get latest evaluation per application to avoid duplicates from outerjoin
    from sqlalchemy import func
    latest_eval_subq = session.exec(
        select(Evaluation.application_id, func.max(Evaluation.id).label("max_ev_id"))
        .group_by(Evaluation.application_id)
    ).all()
    latest_eval_map = {row.application_id: row.max_ev_id for row in latest_eval_subq}

    # Fetch all evaluations that are the latest for their application
    all_evals = {}
    if latest_eval_map:
        for ev_id in latest_eval_map.values():
            ev = session.get(Evaluation, ev_id)
            if ev:
                all_evals[ev.application_id] = ev

    rows = [(app, cand, all_evals.get(app.id)) for app, cand in app_cand_rows]

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
            # Contratados should still count towards their final stage tab
            if app.current_stage_id in stages_map:
                stages_map[app.current_stage_id]["count"] += 1
        else:
            all_active_count += 1
            if app.current_stage_id in stages_map:
                stages_map[app.current_stage_id]["count"] += 1
                
        passes = True
        if outcome is not None:
            if app.outcome != outcome:
                passes = False
        else:
            # If no outcome filter, usually exclude discarded unless specified.
            # We exclude hired UNLESS we are specifically querying their stage.
            if app.outcome == "descartado":
                passes = False
            elif app.outcome == "contratado" and not stage_id:
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
        # Determine email from User if joined, otherwise placeholder
        # Note: cand.user is the relationship. Let's make sure it's accessible or handled
        email = cand.user.email if cand.user and not is_internal_candidate_email(cand.user.email) else "No especificado"

        ranked_rows.append({
            "application_id": app.id,
            "candidate_id": cand.id,
            "full_name": cand.full_name,
            "email": email,
            "phone": cand.phone,
            "years_of_experience": cand.years_of_experience,
            "salary_expectation": getattr(cand, "salary_expectation", None),
            "courses_and_diplomas": cand.courses_and_diplomas,
            "similarity_score": app.similarity_score,
            "evaluation_status": app.evaluation_status,
            "evaluation_message": app.evaluation_message,
            "suggested_category": ev.suggested_category if ev else None,
            "explanation": ev.explanation if ev else "Sin evaluación",
            "interview_questions": ev.interview_questions if ev else None,
            "evaluation_prompt_version": ev.prompt_version if ev else None,
            "status": app.status,
            "current_stage_id": app.current_stage_id,
            "outcome": app.outcome,
            "career_summary": cand.career_summary,
            "tech_stack": cand.tech_stack,
            "source": application_origin_label(session, app),
            "source_url": cand.source_url,
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
