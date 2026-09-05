import sys
import os

# Ajustar el path para que pueda importar módulos de app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.mail import get_mail_provider, MailError

def main():
    if len(sys.argv) < 4:
        print("Uso: python scripts/test_email.py <correo_outlook> <correo_gmail> <correo_institucional>")
        sys.exit(1)

    correos = sys.argv[1:4]
    subject = "Prueba PRI - Postulacion a Ingeniero de Software"
    body = "Estimado Andrés, ¿cómo está? Recibimos su postulación al cargo."

    provider = get_mail_provider()
    
    print(f"Usando proveedor de correo: {provider.__class__.__name__}")
    
    for email in correos:
        print(f"Enviando a {email}...")
        try:
            message_id = provider.send(email, subject, body)
            print(f"✅ Enviado exitosamente. MessageID: {message_id}")
        except MailError as e:
            print(f"❌ Error al enviar: {e}")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    main()
