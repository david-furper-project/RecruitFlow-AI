import math
import re
from typing import Iterable, Sequence

from app.models import CandidateProfile, JobOffer
from app.services.parsing_service import sanitize_text_for_model


MATCHING_PROMPT_VERSION = "semantic-affinity-v2.1"
MATCHING_MODEL_VERSION = "gemini-embedding-2-1536"


def _join_professional_fields(values: Iterable[object]) -> str:
    return sanitize_text_for_model("\n".join(str(value) for value in values if value not in (None, "")))


def _professional_document_text(value: str) -> str:
    """Remove contact identifiers before creating a professional embedding."""
    sanitized = sanitize_text_for_model(value)
    sanitized = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", " ", sanitized)
    sanitized = re.sub(r"https?://\S+|www\.\S+", " ", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\b\d{1,2}(?:\.\d{3}){2}-?[\dkK]\b", " ", sanitized)
    sanitized = re.sub(r"(?<!\w)\+?\d{1,3}[\s().-]\d{3,4}[\s.-]\d{3,4}(?!\w)", " ", sanitized)
    sanitized = re.sub(r"\b\d{8,15}\b", " ", sanitized)
    return re.sub(r"\s+", " ", sanitized).strip()[:20000]


def candidate_profile_text(candidate: CandidateProfile) -> str:
    """Build the only professional text used for candidate affinity embeddings."""
    if candidate.extracted_text:
        return _professional_document_text(candidate.extracted_text)
    return _join_professional_fields(
        (
            f"Titular: {candidate.professional_headline or ''}",
            f"Experiencia total: {candidate.years_of_experience or 0} años",
            f"Resumen: {candidate.career_summary or ''}",
            f"Competencias: {candidate.tech_stack or ''}",
            f"Formación: {candidate.courses_and_diplomas or ''}",
            f"Experiencia profesional: {candidate.extracted_text or ''}",
        )
    )


def structured_profile_text(structured: dict) -> str:
    """Build the same affinity input before a sourcing profile is persisted."""
    if structured.get("professional_text"):
        return _professional_document_text(str(structured["professional_text"]))
    return _join_professional_fields(
        (
            f"Titular: {structured.get('headline') or ''}",
            f"Experiencia total: {structured.get('years_of_experience') or 0} años",
            f"Resumen: {structured.get('summary') or ''}",
            f"Competencias: {structured.get('skills') or ''}",
            f"Formación: {structured.get('education') or ''}",
            f"Experiencia profesional: {structured.get('professional_text') or structured.get('experience') or ''}",
        )
    )


def job_offer_text(offer: JobOffer) -> str:
    """Build the canonical offer input used by sourcing and application scoring."""
    return _join_professional_fields(
        (
            f"Título: {offer.title or ''}",
            f"Descripción: {offer.description or ''}",
            f"Requerimientos: {offer.requirements or ''}",
            f"Stack Tecnológico: {offer.tech_stack or ''}",
            f"Seniority: {offer.seniority or ''}",
            f"Experiencia Mínima: {offer.experience_years or 0} años",
        )
    )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def affinity_percentage(left: Sequence[float], right: Sequence[float]) -> float:
    return round(cosine_similarity(left, right) * 100, 2)


def affinity_category(score: float) -> str:
    if score >= 0.75:
        return "apto"
    if score >= 0.60:
        return "en_revision"
    return "no_apto"


def affinity_explanation(percentage: float) -> str:
    if percentage >= 75:
        assessment = "alta afinidad profesional"
    elif percentage >= 60:
        assessment = "afinidad profesional en revisión"
    else:
        assessment = "afinidad profesional limitada"
    return (
        f"El perfil presenta {assessment} con la vacante ({percentage:.2f}%). "
        "El resultado usa el mismo criterio semántico de experiencia, competencias y requisitos "
        "en sourcing y postulaciones; no constituye una decisión de selección."
    )
