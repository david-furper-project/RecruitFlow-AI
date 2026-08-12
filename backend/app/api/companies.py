from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from pydantic import BaseModel
from app.db.session import get_session
from app.models import Company

router = APIRouter()

class CompanyCreate(BaseModel):
    name: str
    industry: str = None
    description: str = None

@router.get("/", response_model=List[Company])
def list_companies(session: Session = Depends(get_session)):
    companies = session.exec(select(Company)).all()
    return companies

@router.post("/", response_model=Company)
def create_company(company_data: CompanyCreate, session: Session = Depends(get_session)):
    company = Company(**company_data.dict())
    session.add(company)
    session.commit()
    session.refresh(company)
    return company
