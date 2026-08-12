from pypdf import PdfReader
from io import BytesIO

async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Recibe los bytes del PDF y extrae todo su texto.
    """
    try:
        reader = PdfReader(BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""
