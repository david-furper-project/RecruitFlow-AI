import json
import os
import re
import zipfile
from io import BytesIO
from typing import Any, Dict, Optional, Set, Tuple

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from app.core.config import settings

EXCLUDED_FIELDS = [
    "nacionalidad",
    "edad",
    "fecha_nacimiento",
    "fotografia",
    "universidad_egreso",
    "direccion",
    "ubicacion",
    "ubicación",
    "estado_civil",
    "genero",
    "género",
]

EXTRACTION_PROMPT_VERSION = "extract-v1.0"

DEFAULT_CV_EXTENSIONS = {".pdf", ".doc", ".docx"}
WORD_BINARY_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
WORD_DOCUMENT_DIRECTORY_ENTRY = "WordDocument".encode("utf-16le")
CV_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".doc": {"application/msword", "application/vnd.ms-word"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
}


class StructuredCandidateProfile(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    rut: Optional[str] = None
    tech_stack: Optional[str] = None
    years_of_experience: Optional[int] = None
    courses_and_diplomas: Optional[str] = None
    career_summary: Optional[str] = None
    salary_expectation: Optional[str] = None
    headline: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None


def sanitize_text_for_model(raw_text: str) -> str:
    text = raw_text or ""
    sanitized = text
    for term in EXCLUDED_FIELDS:
        pattern = re.compile(rf"(?i)\b{re.escape(term)}\b\s*[:\-]?\s*[^\n,.;]+[\n,.;]?", re.IGNORECASE)
        sanitized = pattern.sub(" ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def _heuristic_extract(raw_text: str) -> Dict[str, Any]:
    text = raw_text or ""
    text_lower = text.lower()
    tech_keywords = [
        "python", "sql", "postgresql", "fastapi", "react", "typescript", "javascript",
        "node", "aws", "docker", "kubernetes", "java", "c#", "azure", "gcp", "spark",
        "data warehouse", "pandas", "pytorch", "tensorflow", "machine learning",
    ]
    found = [item for item in tech_keywords if item in text_lower]
    stack = ", ".join(sorted({tech.capitalize() for tech in found}, key=lambda x: x.lower())) or "No especificado"

    years_match = re.search(r"(\d+)\s+(?:años?|years?)\s+(?:de\s+)?experiencia", text_lower)
    years = int(years_match.group(1)) if years_match else 0

    summary = " ".join(text.split())
    summary = re.sub(r"\s+", " ", summary)
    summary = summary[:500] if len(summary) > 500 else summary

    result = {
        "full_name": "",
        "tech_stack": stack,
        "years_of_experience": years,
        "courses_and_diplomas": "No especificado",
        "career_summary": summary or "No especificado",
    }

    name_match = re.search(r"(?:nombre|full name|candidate)\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñü\s]+)", text)
    if name_match:
        result["full_name"] = name_match.group(1).strip()
    return result


def _parse_structured_response(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        data = payload
    elif hasattr(payload, "model_dump"):
        data = payload.model_dump()
    elif hasattr(payload, "dict"):
        data = payload.dict()
    else:
        data = json.loads(str(payload))

    cleaned: Dict[str, Any] = {}
    for key in ["full_name", "email", "phone", "tech_stack", "years_of_experience", "courses_and_diplomas", "career_summary", "salary_expectation", "headline", "experience", "education"]:
        value = data.get(key)
        if key == "years_of_experience":
            if isinstance(value, str):
                try:
                    cleaned[key] = int(value)
                except ValueError:
                    cleaned[key] = None
            else:
                cleaned[key] = value
        elif isinstance(value, str):
            cleaned[key] = value.strip() or None
        else:
            cleaned[key] = value

    if cleaned.get("full_name") in (None, ""):
        cleaned["full_name"] = None
    if cleaned.get("email") in (None, "", "No especificado"):
        cleaned["email"] = None
    if cleaned.get("phone") in (None, "", "No especificado"):
        cleaned["phone"] = None
    if cleaned.get("tech_stack") in (None, "", "No especificado"):
        cleaned["tech_stack"] = None
    if cleaned.get("courses_and_diplomas") in (None, "", "No especificado"):
        cleaned["courses_and_diplomas"] = None
    if cleaned.get("career_summary") in (None, "", "No especificado"):
        cleaned["career_summary"] = None
    if cleaned.get("salary_expectation") in (None, "", "No especificada"):
        cleaned["salary_expectation"] = None

    return cleaned


def extract_candidate_profile(raw_text: str, strict: bool = False) -> Dict[str, Any]:
    filtered_text = sanitize_text_for_model(raw_text)
    if not filtered_text:
        return {
            "full_name": None,
            "email": None,
            "phone": None,
            "tech_stack": None,
            "years_of_experience": None,
            "courses_and_diplomas": None,
            "career_summary": None,
            "salary_expectation": None,
        }

    try:
        from app.services.ai_service import extract_structured_profile
        
        parsed = extract_structured_profile(filtered_text, allow_fallback=not strict)
        validated = StructuredCandidateProfile(**{k: v for k, v in parsed.items() if v is not None and k in StructuredCandidateProfile.model_fields})
        return _parse_structured_response(validated)
    except Exception as exc:
        if strict:
            raise
        print(f"Structured extraction fallback activated: {exc}")
        fallback = _heuristic_extract(filtered_text)
        try:
            validated = StructuredCandidateProfile(**{k: v for k, v in fallback.items() if v is not None})
            return _parse_structured_response(validated)
        except ValidationError:
            return _parse_structured_response(StructuredCandidateProfile())


def validate_and_merge_profile(candidate: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged = {"full_name": None, "email": None, "phone": None, "tech_stack": None, "years_of_experience": None, "courses_and_diplomas": None, "career_summary": None, "salary_expectation": None}
    if existing:
        merged.update({k: v for k, v in existing.items() if v is not None})
    for key, value in candidate.items():
        if value not in (None, "", []) and value != "No especificado":
            merged[key] = value
    return merged


def normalize_extracted_text(text: str) -> str:
    """Repair text extracted from PDFs that render words with spaced glyphs.

    Design tools such as Canva can store visible text as ``D A V I D`` and use
    two spaces between words.  Humans see a normal document, but parsers and
    identity checks otherwise receive isolated characters.  Only lines made up
    predominantly of one-character glyphs are compacted, so ordinary prose is
    left unchanged.
    """
    normalized_lines = []
    for raw_line in (text or "").splitlines():
        stripped = raw_line.strip()
        tokens = re.findall(r"\S+", stripped)
        glyph_tokens = [token for token in tokens if len(token) == 1]
        if len(tokens) >= 4 and len(glyph_tokens) / len(tokens) >= 0.7:
            word_fragments = re.split(r"[ \t]{2,}", stripped)
            stripped = " ".join(
                re.sub(r"[ \t]+", "", fragment)
                for fragment in word_fragments
                if fragment.strip()
            )
        normalized_lines.append(stripped)
    return "\n".join(normalized_lines).strip()


def extract_text_from_upload(file_bytes: bytes, filename: str) -> str:
    extension = os.path.splitext(filename or "")[1].lower()
    if extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(file_bytes))
            pages = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text:
                    pages.append(text)
            return normalize_extracted_text("\n".join(pages))
        except Exception:
            return ""

    if extension == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
                xml = zf.read("word/document.xml")
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for paragraph in root.iterfind(".//w:p", ns):
                paragraph_text = "".join(
                    node.text or ""
                    for node in paragraph.iterfind(".//w:t", ns)
                ).strip()
                if paragraph_text:
                    paragraphs.append(paragraph_text)
            return normalize_extracted_text("\n".join(paragraphs))
        except Exception:
            return ""

    if extension == ".doc":
        # Legacy Word files store text in OLE streams. This conservative fallback
        # recovers readable ASCII/UTF-16 fragments without executing document data.
        fragments = []
        for raw_fragment in re.findall(rb"[\x20-\x7e\t\r\n]{4,}", file_bytes):
            decoded = raw_fragment.decode("latin-1", errors="ignore").strip()
            if decoded and decoded != "WordDocument":
                fragments.append(decoded)
        try:
            utf16_text = file_bytes.decode("utf-16le", errors="ignore")
            fragments.extend(
                fragment.strip()
                for fragment in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9@.,+()/_\- ]{4,}", utf16_text)
                if fragment.strip() and fragment.strip() != "WordDocument"
            )
        except UnicodeError:
            pass
        return normalize_extracted_text(" ".join(dict.fromkeys(fragments)))

    return ""


def validate_cv_upload(
    file: UploadFile,
    *,
    allowed_extensions: Optional[Set[str]] = None,
    max_size_bytes: Optional[int] = None,
) -> Tuple[bytes, str, str]:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="El archivo no tiene nombre.")

    extension = os.path.splitext(file.filename)[1].lower()
    accepted_extensions = allowed_extensions or DEFAULT_CV_EXTENSIONS
    if extension not in accepted_extensions:
        formats = ", ".join(sorted(item.removeprefix(".").upper() for item in accepted_extensions))
        raise HTTPException(
            status_code=400,
            detail=f"Formato inválido. Solo se aceptan CV en {formats}.",
        )

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="El CV está vacío.")
    size_limit = max_size_bytes or settings.MAX_UPLOAD_SIZE_BYTES
    if len(file_bytes) > size_limit:
        max_size_mb = size_limit / (1024 * 1024)
        formatted_size = f"{max_size_mb:g}"
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el tamaño máximo permitido de {formatted_size} MB.",
        )

    declared_mime = (file.content_type or "").split(";", 1)[0].strip().lower()
    allowed_mimes = CV_MIME_TYPES.get(extension, set())
    if declared_mime and declared_mime != "application/octet-stream" and declared_mime not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail="El tipo MIME declarado no corresponde al formato del CV.",
        )

    if extension == ".pdf" and not file_bytes.lstrip().startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="El contenido del archivo no corresponde a un PDF válido.",
        )
    if extension == ".docx":
        if not zipfile.is_zipfile(BytesIO(file_bytes)):
            raise HTTPException(
                status_code=400,
                detail="El contenido del archivo no corresponde a un documento Word (.docx) válido.",
            )
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as document:
                entries = set(document.namelist())
        except zipfile.BadZipFile:
            entries = set()
        if "word/document.xml" not in entries or "[Content_Types].xml" not in entries:
            raise HTTPException(
                status_code=400,
                detail="El contenido del archivo no corresponde a un documento Word (.docx) válido.",
            )
    if extension == ".doc" and (
        not file_bytes.startswith(WORD_BINARY_SIGNATURE)
        or WORD_DOCUMENT_DIRECTORY_ENTRY not in file_bytes
    ):
        raise HTTPException(
            status_code=400,
            detail="El contenido del archivo no corresponde a un documento Word (.doc) válido.",
        )

    extracted_text = extract_text_from_upload(file_bytes, file.filename)
    if not extracted_text:
        raise HTTPException(status_code=400, detail="No se pudo extraer texto del CV. Probablemente está escaneado o corrupto.")

    file.file.seek(0)
    return file_bytes, extracted_text, os.path.basename(file.filename)
