from sqlmodel import Session, select
from app.db.session import engine, init_db
from app.models import Company, JobOffer

def seed():
    # Asegurar que las tablas y el admin existan
    init_db()
    
    with Session(engine) as session:
        # Check company
        company = session.exec(select(Company).where(Company.name == "TechCorp")).first()
        if not company:
            company = Company(name="TechCorp", description="Tech startup")
            session.add(company)
            session.commit()
            session.refresh(company)
            print(f"Compañía creada con ID: {company.id}")
        else:
            print(f"Compañía ya existe con ID: {company.id}")

        # Check job offer
        offer = session.exec(select(JobOffer).where(JobOffer.title == "Ingeniero de Software Backend")).first()
        if not offer:
            offer = JobOffer(
                company_id=company.id,
                title="Ingeniero de Software Backend",
                description="Buscamos un ingeniero para el equipo de Python.",
                requirements="Python, FastAPI, PostgreSQL",
                tech_stack="python,fastapi,postgresql,docker",
                salary_range="$3000 - $4000",
                experience_years=3,
                seniority="mid",
                status="active"
            )
            session.add(offer)
            session.commit()
            session.refresh(offer)
            print(f"Oferta de trabajo creada con ID: {offer.id}")
        else:
            print(f"Oferta ya existe con ID: {offer.id}")

if __name__ == "__main__":
    seed()
