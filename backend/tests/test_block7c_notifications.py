import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from datetime import datetime

from app.main import app
from app.db.session import engine
from app.models import Application, CandidateProfile, Decision, JobOffer, Notification, User
from app.services.notification_service import async_deliver_notification

client = TestClient(app)

@pytest.fixture
def db_session():
    with Session(engine) as session:
        yield session

@pytest.fixture
def test_data_for_notifications(db_session: Session):
    # Crear usuario candidato
    user = User(email="test_candidate@notify.com", password_hash="hash")
    db_session.add(user)
    db_session.commit()
    
    # Crear perfil
    profile = CandidateProfile(user_id=user.id, full_name="Test Candidate")
    db_session.add(profile)
    db_session.commit()
    
    from app.models import Company
    
    # Crear empresa
    company = Company(name="Test Company")
    db_session.add(company)
    db_session.commit()
    
    # Crear oferta
    offer = JobOffer(
        title="Test Job",
        description="Test Desc",
        requirements="Test Req",
        tech_stack="Python",
        salary_range="1-2",
        experience_years=1,
        seniority="junior",
        status="open",
        embedding=[0.0] * 1536,
        company_id=company.id
    )
    db_session.add(offer)
    db_session.commit()
    
    # Crear aplicación
    application = Application(candidate_id=profile.id, job_offer_id=offer.id, status="pending")
    db_session.add(application)
    db_session.commit()
    
    return application

@pytest.mark.asyncio
async def test_successful_notification_delivery(db_session: Session, test_data_for_notifications, monkeypatch):
    application = test_data_for_notifications
    
    # Mock sendgrid_mailer para que retorne True
    def mock_mailer(email, subject, body):
        return True
    
    monkeypatch.setattr("app.services.notification_service.sendgrid_mailer", mock_mailer)
    
    # Ejecutar la tarea en background
    await async_deliver_notification(application.id, "recepcion")
    
    # Verificar base de datos
    db_session.expire_all()
    notification = db_session.exec(
        select(Notification)
        .where(Notification.application_id == application.id, Notification.type == "recepcion")
    ).first()
    
    assert notification is not None
    assert notification.send_status == "enviado"
    assert notification.sent_at is not None
    assert notification.retry_count == 0

@pytest.mark.asyncio
async def test_failed_notification_retries(db_session: Session, test_data_for_notifications, monkeypatch):
    application = test_data_for_notifications
    
    # Mock sendgrid_mailer para que siempre falle y asyncio.sleep para que no demore el test real
    def mock_mailer(email, subject, body):
        return False
        
    async def mock_sleep(seconds):
        pass
        
    monkeypatch.setattr("app.services.notification_service.sendgrid_mailer", mock_mailer)
    monkeypatch.setattr("asyncio.sleep", mock_sleep)
    
    await async_deliver_notification(application.id, "avanzar")
    
    db_session.expire_all()
    notification = db_session.exec(
        select(Notification)
        .where(Notification.application_id == application.id, Notification.type == "avance")
    ).first()
    
    assert notification is not None
    assert notification.send_status == "fallido"
    assert notification.sent_at is None
    # Hubo el intento 0 más 3 intentos con delay = 3
    assert notification.retry_count == 3

def test_api_metric_endpoint(db_session: Session, test_data_for_notifications):
    # La prueba de integración con FastAPI
    response = client.get("/api/notifications/completion-rate")
    assert response.status_code == 200
    data = response.json()
    assert "rate" in data
    assert data["threshold"] == 95.0
