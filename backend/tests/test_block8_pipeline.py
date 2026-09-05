import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.db.session import engine
from app.models import JobOffer, PipelineStage, Company

client = TestClient(app)

@pytest.fixture
def session():
    with Session(engine) as session:
        yield session

def test_pipeline_stages_seeded_and_put(session: Session):
    # Setup company
    company = Company(name="Test Company 8")
    session.add(company)
    session.commit()
    
    # Create offer directly in DB
    offer = JobOffer(
        company_id=company.id,
        title="Backend Dev 8",
        description="Desc",
        requirements="Req",
        tech_stack="Python",
        salary_range="100-120",
        experience_years=3,
        seniority="mid",
        embedding=[0.1]*1536
    )
    session.add(offer)
    session.commit()
    
    # Seed stages manually to simulate create_offer
    default_stages = [
        PipelineStage(job_offer_id=offer.id, name="Pendiente", order_index=1, kind="inicial"),
        PipelineStage(job_offer_id=offer.id, name="Entrevista", order_index=2, kind="proceso"),
        PipelineStage(job_offer_id=offer.id, name="Finalista", order_index=3, kind="final")
    ]
    session.add_all(default_stages)
    session.commit()
    
    # Test GET stages implicitly or test PUT directly
    stages = session.exec(select(PipelineStage).where(PipelineStage.job_offer_id == offer.id).order_by(PipelineStage.order_index)).all()
    assert len(stages) == 3
    
    # Payload for PUT
    payload = {
        "stages": [
            {"id": stages[0].id, "name": "Nueva Pendiente", "order_index": 1, "kind": "inicial"},
            {"name": "Technical Test", "order_index": 2, "kind": "proceso"},
            {"id": stages[-1].id, "name": "Contratado", "order_index": 3, "kind": "final"}
        ]
    }
    
    print("PAYLOAD:", payload)
    res = client.put(f"/api/offers/{offer.id}/stages", json=payload)
    print("RESPONSE:", res.text)
    assert res.status_code == 200, res.text
    
    session.expire_all()
    session.commit() # End current transaction to see TestClient's changes
    
    new_stages = session.exec(select(PipelineStage).where(PipelineStage.job_offer_id == offer.id).order_by(PipelineStage.order_index)).all()
    print("NEW STAGES:", new_stages)
    assert len(new_stages) == 3
    assert new_stages[0].name == "Nueva Pendiente"
    assert new_stages[1].name == "Technical Test"
    assert new_stages[2].name == "Contratado"
