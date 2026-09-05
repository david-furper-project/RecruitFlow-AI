import requests
from app.core.config import settings

def fetch_linkedin_profile(access_token: str) -> str:
    """Extrae datos del usuario desde la API de LinkedIn y devuelve texto para procesar."""
    if settings.LINKEDIN_CLIENT_ID == "mock_linkedin_id":
        raise RuntimeError("La integración autenticada de LinkedIn no está configurada.")
        
    url = "https://api.linkedin.com/v2/userinfo"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception("Failed to fetch LinkedIn profile")
        
    data = response.json()
    # Construimos un string estructurado con la data cruda para mandarlo al LLM
    text_data = f"Nombre: {data.get('name', 'N/A')}\n"
    text_data += f"Email: {data.get('email', 'N/A')}\n"
    return text_data
