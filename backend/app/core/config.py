from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Plataforma de Reclutamiento Inteligente (PRI)"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/pri_db"

    # AWS S3 Settings (Mocks as default)
    AWS_ACCESS_KEY_ID: str = "mock_access_key"
    AWS_SECRET_ACCESS_KEY: str = "mock_secret_key"
    AWS_REGION_NAME: str = "us-east-1"
    AWS_BUCKET_NAME: str = "pri-cv-bucket-mock"
    
    # AI Services
    OPENAI_API_KEY: str = "mock_openai_key"
    GEMINI_API_KEY: str = "mock_gemini_key"
    USE_MOCK_AI: bool = False

    # Mail Provider
    MAIL_PROVIDER: str = "mailpit"
    MAIL_FROM_EMAIL: str = "noreply@pri.local"
    MAIL_FROM_NAME: str = "PRI - Reclutamiento"
    BREVO_API_KEY: str = "mock_brevo_key"

    # SendGrid (Legacy/Fallback)
    SENDGRID_API_KEY: str = "mock_sendgrid_key"
    SENDER_EMAIL: str = "noreply@pri.local"

    # LinkedIn
    LINKEDIN_CLIENT_ID: str = "mock_linkedin_id"
    LINKEDIN_CLIENT_SECRET: str = "mock_linkedin_secret"
    LINKEDIN_REDIRECT_URI: str = "http://localhost:5173/linkedin/callback"
    LINKEDIN_SOURCING_ENABLED: bool = True
    SOURCING_INVITATION_BASE_URL: str = "http://localhost:5173/invitations"

    # Candidate capture
    MAX_UPLOAD_SIZE_BYTES: int = 3 * 1024 * 1024
    OPENAI_MODEL: str = "gpt-4o-mini"

    # JWT Authentication
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8

    class Config:
        env_file = ".env"

settings = Settings()
