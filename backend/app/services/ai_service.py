import json
from typing import List

from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.core.config import settings


def get_embeddings_client():
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        class MockEmbeddings:
            def embed_query(self, text: str) -> List[float]:
                import hashlib
                import random
                seed = int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16)
                random.seed(seed)
                return [random.uniform(-1.0, 1.0) for _ in range(1536)]
        return MockEmbeddings()

    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2",
        google_api_key=settings.GEMINI_API_KEY,
        output_dimensionality=1536,
    )

def get_llm():
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        class MockLLM:
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
    """Generates an embedding vector for the given text."""
    try:
        client = get_embeddings_client()
        return client.embed_query(text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error calling Gemini Embeddings: {e}. Falling back to mock.")
        import hashlib
        import random
        seed = int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16)
        random.seed(seed)
        return [random.uniform(-1.0, 1.0) for _ in range(1536)]

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
        "nacionalidad": "No especificada (Mock)",
        "tech_stack": tech_stack,
        "years_of_experience": exp or 0,
        "courses_and_diplomas": "Datos extraídos (Simulados)",
        "career_summary": f"Resumen simulado extraído del texto (Longitud: {len(raw_text)}).",
        "salary_expectation": "No especificada"
    }

def extract_structured_profile(raw_text: str, target_role: str = None) -> dict:
    """Uses LLM to extract structured data from raw CV text, calculated relative to target_role if provided."""
    if getattr(settings, "USE_MOCK_AI", False) or getattr(settings, "GEMINI_API_KEY", "mock_gemini_key") == "mock_gemini_key":
        return mock_extract(raw_text)
        
    try:
        llm = get_llm()
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
            "'email' (string, busca correos electrónicos, o 'No especificado'), "
            "'phone' (string, busca números de teléfono, o 'No especificado'), "
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
        
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        return json.loads(content)
    except Exception as e:
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

