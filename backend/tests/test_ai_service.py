import json
from unittest.mock import patch, MagicMock

from app.services.ai_service import extract_structured_profile
from app.services.parsing_service import sanitize_text_for_model, _parse_structured_response, StructuredCandidateProfile


def test_sanitize_text_for_model_keeps_information():
    # Test that sanitization does not aggressively remove useful information
    raw_text = "Nacionalidad Chilena. Edad 30. Años de experiencia: 5 años. Stack: Python, Java. Email: juan@test.com Tel: +56912345678"
    sanitized = sanitize_text_for_model(raw_text)
    
    # Excluded fields shouldn't completely destroy the rest of the text
    assert "Años de experiencia: 5 años" in sanitized or "experiencia: 5 años" in sanitized
    assert "Python, Java" in sanitized
    assert "juan@test.com" in sanitized
    assert "+56912345678" in sanitized


class FakeLLM:
    def __init__(self, content):
        from langchain_core.messages import AIMessage
        self.response = AIMessage(content=content)
    def __ror__(self, other):
        return self
    def invoke(self, *args, **kwargs):
        return self.response
    def __call__(self, *args, **kwargs):
        return self.response

@patch("app.services.ai_service.get_llm")
def test_extract_structured_profile_handles_markdown_json(mock_get_llm):
    # Mock LLM returning markdown JSON
    mock_get_llm.return_value = FakeLLM("""
    Aquí está el JSON:
    ```json
    {
        "full_name": "Juan Pérez",
        "email": "juan@test.com",
        "phone": "+56912345678",
        "tech_stack": "Python, React",
        "years_of_experience": 5,
        "courses_and_diplomas": "Ingeniería en Informática",
        "career_summary": "Desarrollador Full Stack",
        "salary_expectation": "No especificada"
    }
    ```
    """)

    result = extract_structured_profile("Texto de prueba")
    
    assert result.get("full_name") == "Juan Pérez"
    assert result.get("email") == "juan@test.com"
    assert result.get("years_of_experience") == 5


@patch("app.services.ai_service.get_llm")
def test_extract_structured_profile_handles_raw_json(mock_get_llm):
    # Mock LLM returning raw JSON without markdown
    mock_get_llm.return_value = FakeLLM("""{
        "full_name": "Maria Lopez",
        "email": "maria@test.com",
        "phone": "No especificado",
        "tech_stack": "Java, Spring",
        "years_of_experience": 3,
        "courses_and_diplomas": "Ingeniería de Software",
        "career_summary": "Backend dev",
        "salary_expectation": "2000"
    }""")

    result = extract_structured_profile("Texto de prueba 2")
    
    assert result.get("full_name") == "Maria Lopez"
    assert result.get("years_of_experience") == 3


def test_parse_structured_response_cleans_empty_strings():
    # Test that the parser cleans empty strings to None
    raw_data = StructuredCandidateProfile(
        full_name="Pedro",
        email="No especificado",
        phone=" ",
        tech_stack="",
        years_of_experience=0,
        courses_and_diplomas="No especificado",
        career_summary="Developer",
        salary_expectation="No especificada"
    )
    
    cleaned = _parse_structured_response(raw_data)
    
    assert cleaned["email"] is None
    assert cleaned["phone"] is None
    assert cleaned["tech_stack"] is None
    assert cleaned["courses_and_diplomas"] is None
    assert cleaned["salary_expectation"] is None
    assert cleaned["full_name"] == "Pedro"
    assert cleaned["career_summary"] == "Developer"
    assert cleaned["years_of_experience"] == 0
