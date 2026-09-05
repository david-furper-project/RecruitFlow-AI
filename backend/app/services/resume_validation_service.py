"""High-confidence content and identity validation for uploaded CVs."""

import re
import unicodedata
from dataclasses import dataclass

from fastapi import HTTPException

from app.services.candidate_identity_service import EMAIL_PATTERN, normalize_candidate_email
from app.services.parsing_service import normalize_extracted_text


_PROFESSIONAL_PATTERNS = {
    "experience": (
        r"\bexperiencia\s+(?:profesional|laboral)\b",
        r"(?:^|\n)\s*experiencia\s*(?::|\n|$)",
        r"\b(?:work|professional)\s+experience\b",
        r"\b(?:employment|career)\s+history\b",
        r"\b\d+\s+(?:anos?|años?|years?)\s+(?:de\s+)?experiencia\b",
    ),
    "education": (
        r"\b(?:educacion|educación|formacion|formación)\s+(?:academica|académica|profesional)\b",
        r"(?:^|\n)\s*(?:educacion|educación|formacion|formación)\s*(?::|\n|$)",
        r"\b(?:education|academic background)\b",
        r"\b(?:universidad|university|instituto profesional|technical institute)\b",
    ),
    "skills": (
        r"\b(?:habilidades|competencias|conocimientos)\s+(?:tecnicas|técnicas|profesionales)\b",
        r"(?:^|\n)\s*(?:habilidades|competencias|aptitudes)\s*(?::|\n|$)",
        r"\b(?:technical skills|professional skills|tech stack)\b",
        r"\b(?:tecnologias|tecnologías|herramientas|lenguajes)\b",
    ),
    "profile": (
        r"\b(?:perfil|resumen|objetivo)\s+(?:personal|profesional)\b",
        r"\b(?:professional summary|career objective|professional profile)\b",
    ),
    "dated_history": (
        r"\b(?:19|20)\d{2}\s*(?:-|–|—|a|hasta|to)\s*(?:(?:19|20)\d{2}|actual(?:idad)?|presente|current|present)\b",
    ),
}

_TECHNOLOGY_TERMS = {
    "angular",
    "aws",
    "azure",
    "c#",
    "c++",
    "docker",
    "fastapi",
    "gcp",
    "git",
    "java",
    "javascript",
    "kubernetes",
    "node.js",
    "postgresql",
    "python",
    "react",
    "selenium",
    "sql",
    "typescript",
}


@dataclass(frozen=True)
class ResumeValidationResult:
    detected_sections: tuple[str, ...]
    document_emails: tuple[str, ...]


def _normalized_tokens(value: str) -> list[str]:
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", ascii_value.lower())


def _professional_sections(text: str) -> set[str]:
    lowered = (text or "").lower()
    sections = {
        section
        for section, patterns in _PROFESSIONAL_PATTERNS.items()
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns)
    }
    technology_hits = {
        term
        for term in _TECHNOLOGY_TERMS
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered)
    }
    if len(technology_hits) >= 2:
        sections.add("skills")
    return sections


def validate_resume_document(text: str) -> ResumeValidationResult:
    """Reject an upload whose extracted text does not resemble a CV.

    This content-only gate is shared by recruiter and candidate uploads. Identity
    checks remain separate because recruiter imports may legitimately lack a
    visible email address or use the stored name of an existing profile.
    """
    readable_text = normalize_extracted_text(text)
    normalized_text = re.sub(r"\s+", " ", readable_text).strip()
    sections = _professional_sections(readable_text)
    has_career_core = "experience" in sections or {"education", "skills"}.issubset(sections)
    if len(normalized_text) < 120 or len(sections) < 2 or not has_career_core:
        raise HTTPException(
            400,
            "El archivo no parece ser un currículum. Debe incluir información profesional verificable, "
            "como experiencia, educación y habilidades.",
        )

    document_emails = tuple(
        sorted(
            {
                normalized
                for match in EMAIL_PATTERN.findall(readable_text)
                if (normalized := normalize_candidate_email(match)) is not None
            }
        )
    )

    return ResumeValidationResult(
        detected_sections=tuple(sorted(sections)),
        document_emails=document_emails,
    )


def validate_public_resume_document(
    text: str,
    submitted_name: str,
    submitted_email: str,
) -> ResumeValidationResult:
    """Validate CV content and the identity supplied in a public form.

    The gate intentionally favors false negatives over creating a false candidate,
    application, evaluation, or talent-bank record from an unrelated document.
    """
    result = validate_resume_document(text)
    readable_text = normalize_extracted_text(text)
    form_email = normalize_candidate_email(submitted_email)
    document_emails = result.document_emails
    if document_emails and form_email not in document_emails:
        raise HTTPException(
            400,
            "El correo ingresado en el formulario no coincide con el correo incluido en el CV.",
        )

    submitted_tokens = list(dict.fromkeys(token for token in _normalized_tokens(submitted_name) if len(token) >= 2))
    header_tokens = set(_normalized_tokens(readable_text[:1500]))
    matching_tokens = [token for token in submitted_tokens if token in header_tokens]
    required_matches = max(2, (len(submitted_tokens) + 1) // 2)
    if len(submitted_tokens) < 2 or len(matching_tokens) < required_matches:
        raise HTTPException(
            400,
            "El nombre ingresado en el formulario no coincide con el nombre visible en el CV.",
        )

    return result
