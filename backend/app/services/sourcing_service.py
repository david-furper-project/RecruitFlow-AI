import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Callable, Optional
from urllib.parse import urlparse, urlunparse

import requests
from sqlmodel import Session, select

from app.core.config import settings
from app.models import CandidateProfile, JobOffer, User
from app.services.ai_service import generate_embedding
from app.services.parsing_service import extract_candidate_profile, sanitize_text_for_model


class ProfileExtractionError(RuntimeError):
    pass


@dataclass
class PublicProfessionalProfile:
    source_url: str
    text: str
    title: Optional[str] = None
    description: Optional[str] = None


class ProfessionalProfileConnector(ABC):
    @abstractmethod
    def extract(self, url: str) -> PublicProfessionalProfile:
        raise NotImplementedError


class _PublicMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.json_ld: list[dict] = []
        self.visible: list[str] = []
        self._capture_title = False
        self._capture_json = False
        self._json_buffer: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self._capture_title = True
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1
        if tag == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self._capture_json = True
            self._json_buffer = []
        if tag == "meta":
            key = attrs_dict.get("property") or attrs_dict.get("name")
            value = attrs_dict.get("content")
            if key and value:
                self.meta[key.lower()] = unescape(value).strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._capture_title = False
        if tag == "script" and self._capture_json:
            self._capture_json = False
            try:
                payload = json.loads("".join(self._json_buffer))
                values = payload if isinstance(payload, list) else [payload]
                self.json_ld.extend(item for item in values if isinstance(item, dict))
            except (TypeError, ValueError):
                pass
        if tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data):
        value = unescape(data).strip()
        if self._capture_json:
            self._json_buffer.append(data)
        elif self._capture_title:
            self.title += value
        elif not self._hidden_depth and value:
            self.visible.append(value)


def normalize_linkedin_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    if parsed.scheme not in {"http", "https"} or host not in {"linkedin.com", "www.linkedin.com"}:
        raise ValueError("La URL debe pertenecer a linkedin.com.")
    if not re.fullmatch(r"/in/[^/]+", path, flags=re.IGNORECASE):
        raise ValueError("La URL debe corresponder a un perfil público linkedin.com/in/...")
    return urlunparse(("https", "www.linkedin.com", path, "", "", ""))


class LinkedInPublicProfileConnector(ProfessionalProfileConnector):
    def __init__(self, getter: Callable = requests.get):
        self.getter = getter

    def extract(self, url: str) -> PublicProfessionalProfile:
        normalized = normalize_linkedin_url(url)
        try:
            response = self.getter(
                normalized,
                headers={"User-Agent": "PRI-PublicProfilePreview/1.0 (+contact: admin@pri.local)"},
                timeout=12,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            raise ProfileExtractionError("No fue posible consultar el perfil público de LinkedIn.") from exc
        if response.status_code in {401, 403, 429, 999}:
            raise ProfileExtractionError(
                f"LinkedIn bloqueó la consulta automática del perfil (HTTP {response.status_code}). "
                "Puedes abrir el perfil original y pegar manualmente la información profesional visible."
            )
        if response.status_code != 200:
            raise ProfileExtractionError(f"LinkedIn respondió HTTP {response.status_code} al consultar el perfil público.")
        html = response.text or ""
        final_url = str(getattr(response, "url", normalized)).lower()
        final_host = (urlparse(final_url).hostname or "").lower()
        if final_host not in {"linkedin.com", "www.linkedin.com"}:
            raise ProfileExtractionError("LinkedIn redirigió la consulta fuera de su dominio; la extracción fue cancelada.")
        blocked_markers = ("authwall", "/checkpoint/", "linkedin login, sign in")
        if "/login" in final_url or any(marker in html.lower() for marker in blocked_markers):
            raise ProfileExtractionError("LinkedIn exige autenticación para ver este perfil; no se intentará evadir el bloqueo.")
        parser = _PublicMetadataParser()
        parser.feed(html)
        json_text: list[str] = []
        professional_keys = {"name", "headline", "description", "jobTitle", "alumniOf", "knowsAbout", "worksFor"}
        def collect_json_ld(value, key=None):
            if isinstance(value, dict):
                for child_key, child in value.items():
                    collect_json_ld(child, child_key)
            elif isinstance(value, list):
                for child in value:
                    collect_json_ld(child, key)
            elif key in professional_keys and isinstance(value, (str, int, float)):
                json_text.append(str(value))
        for item in parser.json_ld:
            collect_json_ld(item)
        title = parser.meta.get("og:title") or parser.title.strip() or None
        description = parser.meta.get("og:description") or parser.meta.get("description") or None
        parts = json_text + [value for value in (title, description) if value] + parser.visible
        text = sanitize_text_for_model("\n".join(dict.fromkeys(parts)))
        if len(text) < 40:
            raise ProfileExtractionError("El perfil no expone suficiente información profesional públicamente.")
        return PublicProfessionalProfile(normalized, text[:20000], title, description)


def build_manual_public_profile(url: str, professional_text: str) -> PublicProfessionalProfile:
    """Construye una entrada explícita desde texto público copiado por el reclutador."""
    normalized = normalize_linkedin_url(url)
    safe_text = sanitize_text_for_model(professional_text or "")
    if len(safe_text) < 40:
        raise ValueError("Pega al menos 40 caracteres de información profesional pública.")
    return PublicProfessionalProfile(normalized, safe_text[:20000])


def is_linkedin_sourcing_enabled() -> bool:
    return bool(getattr(settings, "LINKEDIN_SOURCING_ENABLED", True))


def structure_public_profile(profile: PublicProfessionalProfile) -> dict:
    safe_text = sanitize_text_for_model(profile.text)
    try:
        structured = extract_candidate_profile(safe_text, strict=True)
    except Exception as exc:
        raise ProfileExtractionError(str(exc)) from exc
    return {
        "full_name": structured.get("full_name") or profile.title,
        "headline": structured.get("headline") or profile.title,
        "experience": structured.get("experience") or profile.description,
        "years_of_experience": structured.get("years_of_experience"),
        "education": structured.get("education") or structured.get("courses_and_diplomas"),
        "skills": structured.get("tech_stack"),
        "summary": structured.get("career_summary") or profile.description,
        "source_url": profile.source_url,
        "contact_email": structured.get("email"),
        "professional_text": safe_text,
    }


def calculate_sourcing_affinity(session: Session, structured: dict, job_offer_id: Optional[int]) -> tuple[Optional[float], Optional[str]]:
    if job_offer_id is None:
        return None, None
    offer = session.get(JobOffer, job_offer_id)
    if offer is None:
        raise ValueError("La vacante no existe.")
    candidate_text = sanitize_text_for_model(
        f"{structured.get('summary') or ''} {structured.get('skills') or ''} {structured.get('experience') or ''}"
    )
    candidate_vector = generate_embedding(candidate_text)
    offer_vector = offer.embedding or generate_embedding(f"{offer.title} {offer.description} {offer.requirements} {offer.tech_stack}")
    dot = sum(a * b for a, b in zip(candidate_vector, offer_vector))
    norm_a = sum(a * a for a in candidate_vector) ** 0.5
    norm_b = sum(b * b for b in offer_vector) ** 0.5
    similarity = max(0.0, min(1.0, dot / (norm_a * norm_b))) if norm_a and norm_b else 0.0
    percentage = round(similarity * 100, 2)
    return percentage, f"Afinidad semántica entre la experiencia profesional pública y los requisitos de la vacante: {percentage}%."


def internal_sourcing_email(source_url: str) -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:24]
    return f"linkedin-{digest}@sourcing.internal.invalid"


def import_sourced_candidate(session: Session, structured: dict) -> CandidateProfile:
    source_url = normalize_linkedin_url(structured.get("source_url", ""))
    existing = session.exec(
        select(CandidateProfile).where(
            CandidateProfile.source_url == source_url,
            CandidateProfile.archived_at.is_(None),
        )
    ).first()
    if existing:
        return existing
    email = internal_sourcing_email(source_url)
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email, role="candidate", password_hash="sourcing-invitation-only")
        session.add(user)
        session.flush()
    professional_text = sanitize_text_for_model(structured.get("professional_text") or "")
    candidate = CandidateProfile(
        user_id=user.id,
        full_name=structured.get("full_name") or "Perfil profesional sin nombre público",
        resume_url=None,
        extracted_text=professional_text,
        tech_stack=structured.get("skills"),
        years_of_experience=structured.get("years_of_experience"),
        courses_and_diplomas=structured.get("education"),
        career_summary=structured.get("summary"),
        professional_headline=structured.get("headline"),
        source="linkedin",
        source_url=source_url,
        contact_status="not_contacted",
        embedding=generate_embedding(f"{structured.get('summary') or ''} {structured.get('skills') or ''}"),
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate
