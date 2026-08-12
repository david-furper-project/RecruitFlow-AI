import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import SQLModel
from app.db.session import engine, init_db
from app.models import User, CandidateProfile, JobOffer, Application

print("Dropping all tables...")
SQLModel.metadata.drop_all(engine)
print("Initializing database with new schema...")
init_db()
print("Done!")
