import json
import logging
from typing import List

from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.core.config import settings


logger = logging.getLogger(__name__)

AI_EVALUATION_UNAVAILABLE_MESSAGE = (
    "Evaluación pendiente/no disponible. Gemini no respondió o no tiene cuota "
    "disponible. Puedes reintentar más tarde."
)


class AIServiceUnavailableError(RuntimeError):
    """Raised when a real AI result cannot be obtained from the provider."""

class EmbeddingProviderUnavailableError(Exception):
    pass

def get_embeddings_client():
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2",
        google_api_key=settings.GEMINI_API_KEY,
        output_dimensionality=1536,
    )

def get_llm():
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        class MockLLM:
            is_fallback_mock = True

            def invoke(self, prompt: str):
                class Response:
                    content = '{"habilidades": ["Mock"], "experiencia_resumen": "Mock", "educacion": "Mock"}'
                return Response()
        return MockLLM()

    return ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        temperature=0.0,
        google_api_key=settings.GEMINI_API_KEY
    )

def generate_embedding(text: str) -> List[float]:
    """Generate a real embedding or fail closed without fabricating a score."""
    try:
        client = get_embeddings_client()
        return client.embed_query(text)
    except Exception as e:
        logger.exception("Gemini embeddings are unavailable")
        raise EmbeddingProviderUnavailableError(AI_EVALUATION_UNAVAILABLE_MESSAGE) from e

def mock_extract(raw_text: str) -> dict:
    import re
    text_lower = raw_text.lower() if raw_text else ""
    common_techs = ["react", "python", "postgresql", "aws", "node", "java", "sql", "typescript"]
    found_techs = [tech.capitalize() for tech in common_techs if tech in text_lower]
    tech_stack = ", ".join(found_techs) if found_techs else "No especificado"
    exp = 0
    exp_match = re.search(r'(\d+)\s+(años?|years?)\s+(de\s+)?experiencia', text_lower)
    if exp_match:
        exp = int(exp_match.group(1))
    return {
        "tech_stack": tech_stack,
        "years_of_experience": exp or 0,
        "courses_and_diplomas": "Datos extraídos (Simulados)",
        "career_summary": f"Resumen simulado extraído del texto (Longitud: {len(raw_text)}).",
        "salary_expectation": "No especificada"
    }

def extract_structured_profile(raw_text: str, target_role: str = None, allow_fallback: bool = True) -> dict:
    """Uses LLM to extract structured data from raw CV text, calculated relative to target_role if provided."""
    llm = get_llm()
    if getattr(llm, "is_fallback_mock", False):
        if not allow_fallback:
            raise RuntimeError("Gemini no está configurado para procesar perfiles de sourcing.")
        return mock_extract(raw_text)

    try:
        role_instruction = ""
        if target_role:
            role_instruction = (
                f"\nATENCIÓN: El candidato está postulando para el cargo de '{target_role}'. "
                "Al calcular 'years_of_experience', SUMA ÚNICAMENTE los años de servicio en posiciones "
                f"que sean directamente relevantes o equivalentes al rol de {target_role}. "
                "Ignora años de experiencia en rubros u oficios no relacionados.\n"
            )

        prompt = PromptTemplate.from_template(
            "Extrae la siguiente información estructurada en formato JSON puro del siguiente CV. "
            "Revisa bien todo el documento para encontrar los datos solicitados. "
            "Usa exactamente estas claves en el JSON: "
            "'full_name' (string), "
            "'headline' (string, titular o cargo profesional), "
            "'experience' (string, síntesis de experiencia profesional), "
            "'education' (string, formación y certificaciones), "
            "'email' (string, busca correos electrónicos, o 'No especificado'), "
            "'phone' (string, busca números de teléfono, o 'No especificado'), "
            "'rut' (string, busca RUT chileno con formato XX.XXX.XXX-X o sin puntos, normalízalo sin puntos ni guión ej: '12345678K', o null si no se encuentra), "
            "'tech_stack' (string de tecnologías, lenguajes, frameworks, herramientas separadas por coma), "
            "'years_of_experience' (entero, deduce el número total de años de experiencia a partir de las fechas o descripciones, o 0 si no hay), "
            "'courses_and_diplomas' (string, lista de educación formal, certificaciones o cursos), "
            "'career_summary' (string breve que resuma su perfil, habilidades principales y trayectoria), "
            "'salary_expectation' (string, expectativa salarial si se menciona, o 'No especificada' si no se encuentra).\n"
            f"{role_instruction}\n"
            "CV:\n{text}\n\n"
            "Responde ÚNICAMENTE con el JSON válido, sin formato markdown extra."
        )

        chain = prompt | llm
        raw_response = chain.invoke({"text": raw_text})

        content = raw_response.content
        if isinstance(content, list):
            content = content[0].get("text", "")
        content = content.strip()

        import re
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        else:
            # Maybe it didn't use markdown blocks but just returned the JSON
            # Try to find the first '{' and last '}'
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]

        return json.loads(content)
    except Exception as e:
        if not allow_fallback:
            raise RuntimeError("Gemini no pudo estructurar el perfil profesional público.") from e
        print(f"Error calling Gemini LLM: {e}. Falling back to mock extraction.")
        return mock_extract(raw_text)

def extract_job_tech_stack(text: str) -> str:
    """Uses LLM to extract a comma-separated list of technologies from a job description."""
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        return "React, Node.js, AWS, PostgreSQL (Mock)"

    try:
        llm = get_llm()
        prompt = PromptTemplate.from_template(
            "Extrae el stack tecnológico (lenguajes, frameworks, herramientas, bases de datos, nube) "
            "del siguiente texto de descripción/requerimientos de una oferta laboral.\n"
            "Responde ÚNICAMENTE con una lista de tecnologías separadas por coma, sin ningún otro texto o viñetas.\n"
            "Si el texto no menciona ninguna tecnología o herramienta específica, responde ÚNICAMENTE con: 'No especificado'.\n"
            "Texto:\n{text}\n"
        )
        chain = prompt | llm
        raw_response = chain.invoke({"text": text})

        content = raw_response.content
        if isinstance(content, list):
            content = content[0].get("text", "")
        return content.strip()
    except Exception as e:
        print(f"Error extracting tech stack: {e}")
        return "No especificado"

def evaluate_candidate_match(candidate_text: str, offer_text: str) -> dict:
    """
    Evaluates the match between a candidate and a job offer using the LLM.
    Returns a dictionary with score (0 to 100), category, explanation, and interview_questions.
    """
    import json
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        return {
            "score": None,
            "category": None,
            "explanation": AI_EVALUATION_UNAVAILABLE_MESSAGE,
            "interview_questions": None,
            "evaluation_status": "unavailable",
        }

    try:
        llm = get_llm()
        prompt = f"""
Eres un reclutador experto en tecnología.
Tu tarea es evaluar la idoneidad de un candidato para una oferta de trabajo.

OFERTA DE TRABAJO:
{offer_text}

PERFIL DEL CANDIDATO:
{candidate_text}

Debes devolver un objeto JSON con la siguiente estructura exacta:
{{
  "score": (número entero del 0 al 100 representando el porcentaje de match),
  "category": (solo puede ser "apto", "en_revision", o "no_apto"),
  "explanation": (breve explicación del porqué de este puntaje y categoría),
  "interview_questions": (lista de 2 o 3 preguntas recomendadas para hacerle en la entrevista)
}}

REGLAS ESTRICTAS:
- No incluyas nacionalidad en tu evaluación.
- El JSON debe ser válido y la respuesta debe contener únicamente el JSON.
"""
        response = llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = content[0].get("text", "")

        content = content.replace("```json", "").replace("```", "").strip()
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        if start_idx != -1 and end_idx != -1:
            content = content[start_idx:end_idx+1]

        result = json.loads(content)

        # Ensure category is valid
        if result.get("category") not in {"apto", "en_revision", "no_apto"}:
            score = result.get("score", 0)
            if score >= 80:
                result["category"] = "apto"
            elif score >= 50:
                result["category"] = "en_revision"
            else:
                result["category"] = "no_apto"

        # Ensure questions are a string if it's a list
        if isinstance(result.get("interview_questions"), list):
            result["interview_questions"] = "\n".join(result["interview_questions"])

        return result
    except Exception as e:
        logger.exception("Gemini match evaluation is unavailable")
        return {
            "score": None,
            "category": None,
            "explanation": AI_EVALUATION_UNAVAILABLE_MESSAGE,
            "interview_questions": None,
            "evaluation_status": "unavailable",
        }

def generate_offer_details(raw_text: str) -> dict:
    """Uses LLM to extract structured Job Offer data from raw text."""
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        return {
            "title": "Ingeniero Mock",
            "description": "Mock description",
            "requirements": "Mock requirements",
            "tech_stack": "Mock tech",
            "salary_range": "No especificado",
            "experience_years": 0,
            "seniority": "Junior",
            "country": "No especificado",
            "modality": "No especificado",
            "message": "Mock message",
            "stages_count": 4
        }

    try:
        llm = get_llm()
        prompt = PromptTemplate.from_template(
            "Extrae la siguiente información estructurada en formato JSON puro del texto sobre una oferta de trabajo. "
            "Revisa bien todo el documento para encontrar los datos solicitados. "
            "Usa exactamente estas claves en el JSON:\n"
            "'title' (string, título del cargo),\n"
            "'description' (string, descripción de la oferta y funciones),\n"
            "'requirements' (string, requisitos excluyentes y deseables),\n"
            "'tech_stack' (string, tecnologías separadas por coma),\n"
            "'salary_range' (string, pretensión salarial o presupuesto indicado, o 'No especificado'),\n"
            "'experience_years' (entero, años de experiencia mínima solicitada, o 0 si no se indica),\n"
            "'seniority' (string, ej: Junior, Semi-Senior, Senior, Lead, etc, o 'No especificado'),\n"
            "'country' (string, país, LATAM, o lugar específico, o 'No especificado'),\n"
            "'modality' (string, modalidad que puede ser: 'presencial', 'remoto' o 'híbrido', o 'No especificado'),\n"
            "'message' (string, algún mensaje importante de la oferta o contexto extra, o 'No especificado'),\n"
            "'stages_count' (entero, cantidad de procesos o etapas de entrevista, típicamente 1, 2, 3 o 4, o null si no se menciona).\n\n"
            "Texto de la oferta:\n{text}\n\n"
            "Responde ÚNICAMENTE con el JSON válido, sin formato markdown extra."
        )

        chain = prompt | llm
        raw_response = chain.invoke({"text": raw_text})

        content = raw_response.content
        if isinstance(content, list):
            content = content[0].get("text", "")
        content = content.strip()

        import re
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        else:
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]

        return json.loads(content)
    except Exception as e:
        print(f"Error calling Gemini LLM for job offer: {e}")
        return {
            "title": "Error extrayendo",
            "description": "El formato del texto no pudo ser procesado",
            "requirements": "",
            "tech_stack": "No especificado",
            "salary_range": "No especificado",
            "experience_years": 0,
            "seniority": "No especificado",
            "country": "No especificado",
            "modality": "No especificado",
            "message": "No especificado",
            "stages_count": 0
        }
