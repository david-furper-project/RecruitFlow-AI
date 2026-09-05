import asyncio
from app.services.ai_service import generate_offer_details
from app.core.config import settings

# mock_gemini_key
print(f"USE_MOCK_AI: {getattr(settings, 'USE_MOCK_AI', False)}")

text = """¡Busco Desarrollador/a Java Semi Senior!

🔹 Requisitos:
• 3+ años de experiencia en desarrollo Backend
• Java + Spring Boot
• Microservicios y APIs REST
• Experiencia con Oracle y/o SQL Server
• Formación en Informática, Computación o carrera afín

📍 Santiago de Chile
💻 Modalidad híbrida: 1 día presencial y 4 días remotos

📩 Si te interesa, envíame tu CV actualizado + pretensión de renta líquida por mensaje interno.

Si conoces a alguien que pueda calzar con el perfil, ¡compártele esta oportunidad! 🙌"""

res = generate_offer_details(text)
print(res)
