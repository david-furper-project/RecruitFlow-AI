from fastapi import APIRouter
from app.api.candidates import router as candidates_router
from app.api.offers import router as offers_router
from app.api.recruiter import router as recruiter_router
from app.api.companies import router as companies_router
from app.api.scoring import router as scoring_router
from app.api.privacy import router as privacy_router
from app.api.auth import router as auth_router
from app.api.sourcing import router as sourcing_router
from app.api.reports import router as reports_router

api_router = APIRouter()

@api_router.get("/health")
def health_check():
    return {"status": "ok", "message": "PRI API is running y la DB está configurada."}

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(candidates_router, prefix="/candidates", tags=["candidates"])
api_router.include_router(offers_router, prefix="/offers", tags=["offers"])
api_router.include_router(recruiter_router, prefix="/recruiter", tags=["recruiter"])
api_router.include_router(companies_router, prefix="/companies", tags=["companies"])
api_router.include_router(scoring_router, tags=["scoring"])
api_router.include_router(privacy_router, prefix="/privacy", tags=["privacy"])
api_router.include_router(sourcing_router, prefix="/sourcing", tags=["sourcing"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
