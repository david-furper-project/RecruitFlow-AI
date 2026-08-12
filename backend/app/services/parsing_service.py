import json
import os
import re
import zipfile
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

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
    "estado_civil",
    "genero",
]

EXTRACTION_PROMPT_VERSION = "extract-v1.0"


class StructuredCandidateProfile(BaseModel):
    full_name: Optional[str] = None
    tech_stack: Optional[str] = None
    years_of_experience: Optional[int] = None
    courses_and_diplomas: Optional[str] = None
    career_summary: Optional[str] = None


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
    for key in ["full_name", "tech_stack", "years_of_experience", "courses_and_diplomas", "career_summary"]:
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
    if cleaned.get("tech_stack") in (None, ""):
        cleaned["tech_stack"] = None
    if cleaned.get("courses_and_diplomas") in (None, ""):
        cleaned["courses_and_diplomas"] = None
    if cleaned.get("career_summary") in (None, ""):
        cleaned["career_summary"] = None

    return cleaned


def extract_candidate_profile(raw_text: str) -> Dict[str, Any]:
    filtered_text = sanitize_text_for_model(raw_text)
    if not filtered_text:
        return {
            "full_name": None,
            "tech_stack": None,
            "years_of_experience": None,
            "courses_and_diplomas": None,
            "career_summary": None,
        }

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate

        if getattr(settings, "OPENAI_API_KEY", "mock_openai_key") == "mock_openai_key":
            raise RuntimeError("openai mock")

        llm = ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0, api_key=settings.OPENAI_API_KEY)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un extractor de CV. Devuelve solo un JSON válido con estas claves: full_name, tech_stack, years_of_experience, courses_and_diplomas, career_summary."),
            ("user", "Extrae solo la información relevante para desempeño laboral del siguiente texto. Excluye datos sensibles e irrelevantes. Texto:\n{cv_text}")
        ])
        structured_llm = llm.with_structured_output(StructuredCandidateProfile)
        response = structured_llm.invoke({"cv_text": filtered_text})
        parsed = _parse_structured_response(response)
        validated = StructuredCandidateProfile(**{k: v for k, v in parsed.items() if v is not None})
        return _parse_structured_response(validated)
    except Exception as exc:
        print(f"Structured extraction fallback activated: {exc}")
        fallback = _heuristic_extract(filtered_text)
        try:
            validated = StructuredCandidateProfile(**{k: v for k, v in fallback.items() if v is not None})
            return _parse_structured_response(validated)
        except ValidationError:
            return _parse_structured_response(fallback)


def validate_and_merge_profile(candidate: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged = {"full_name": None, "tech_stack": None, "years_of_experience": None, "courses_and_diplomas": None, "career_summary": None}
    if existing:
        merged.update({k: v for k, v in existing.items() if v is not None})
    for key, value in candidate.items():
        if value not in (None, "", []) and value != "No especificado":
            merged[key] = value
    return merged


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
            return "\n".join(pages).strip()
        except Exception:
            return ""

    if extension == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
                xml = zf.read("word/document.xml")
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            texts = []
            for node in root.iterfind(".//w:t", ns):
                text = node.text or ""
                if text:
                    texts.append(text)
            return " ".join(texts).strip()
        except Exception:
            return ""

    return ""


def validate_cv_upload(file: UploadFile) -> Tuple[bytes, str, str]:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="El archivo no tiene nombre.")

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Formato inválido. Solo se aceptan archivos PDF o DOCX.")

    file_bytes = file.file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"El archivo supera el tamaño máximo permitido de 5 MB.")

    extracted_text = extract_text_from_upload(file_bytes, file.filename)
    if not extracted_text:
        raise HTTPException(status_code=400, detail="No se pudo extraer texto del CV. Probablemente está escaneado o corrupto.")

    file.file.seek(0)
    return file_bytes, extracted_text, file.filename
