from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)  # índice insensible a mayúsculas se crea en migración
    role: str = Field(default="recruiter")  # 'recruiter' o 'admin'
    password_hash: str
    is_active: bool = Field(default=True)
    last_login_at: Optional[datetime] = None
    failed_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = None
    password_changed_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    candidate_profile: Optional["CandidateProfile"] = Relationship(back_populates="user")
    decisions: List["Decision"] = Relationship(back_populates="user")


class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    industry: Optional[str] = None
    description: Optional[str] = None

    job_offers: List["JobOffer"] = Relationship(back_populates="company")


class CandidateProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    full_name: str
    resume_url: Optional[str] = None
    extracted_text: Optional[str] = None

    phone: Optional[str] = None
    tech_stack: Optional[str] = None
    years_of_experience: Optional[int] = None
    courses_and_diplomas: Optional[str] = None
    career_summary: Optional[str] = None
    salary_expectation: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    embedding: Optional[List[float]] = Field(sa_column=Column(Vector(1536)))

    user: User = Relationship(back_populates="candidate_profile")
    applications: List["Application"] = Relationship(back_populates="candidate")


class JobOffer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
    title: str
    description: str
    requirements: str
    tech_stack: str
    salary_range: str
    experience_years: int
    seniority: str
    status: str = Field(default="open")  # 'open', 'closed'
    embedding: Optional[List[float]] = Field(sa_column=Column(Vector(1536)))

    company: Company = Relationship(back_populates="job_offers")
    applications: List["Application"] = Relationship(back_populates="job_offer")
    stages: List["PipelineStage"] = Relationship(back_populates="job_offer", cascade_delete=True)

class PipelineStage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_offer_id: int = Field(foreign_key="joboffer.id")
    name: str = Field(max_length=60)
    order_index: int
    kind: str = Field(default="proceso", max_length=15)

    job_offer: "JobOffer" = Relationship(back_populates="stages")
    applications: List["Application"] = Relationship(back_populates="current_stage")


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidateprofile.id")
    job_offer_id: Optional[int] = Field(default=None, foreign_key="joboffer.id")
    status: str = Field(default="pending")  # Legacy, will be replaced by current_stage_id + outcome conceptually
    current_stage_id: Optional[int] = Field(default=None, foreign_key="pipelinestage.id")
    outcome: Optional[str] = Field(default=None, max_length=15)
    similarity_score: Optional[float] = None
    consent_given_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    candidate: CandidateProfile = Relationship(back_populates="applications")
    job_offer: "JobOffer" = Relationship(back_populates="applications")
    current_stage: Optional[PipelineStage] = Relationship(back_populates="applications")
    evaluations: List["Evaluation"] = Relationship(back_populates="application")
    decisions: List["Decision"] = Relationship(back_populates="application")
    notifications: List["Notification"] = Relationship(back_populates="application")
    privacy_requests: List["PrivacyRequestLog"] = Relationship(back_populates="application")


class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    suggested_category: str = Field(max_length=15)
    explanation: Optional[str] = None
    interview_questions: Optional[str] = None
    model_version: str = Field(max_length=50)
    prompt_version: str = Field(max_length=50)
    excluded_fields: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    application: Application = Relationship(back_populates="evaluations")


class Decision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    action: str = Field(max_length=25)
    discrepancy_reason: Optional[str] = None
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    from_stage_id: Optional[int] = Field(default=None, foreign_key="pipelinestage.id")
    to_stage_id: Optional[int] = Field(default=None, foreign_key="pipelinestage.id")

    application: Application = Relationship(back_populates="decisions")
    user: User = Relationship(back_populates="decisions")
    from_stage: Optional[PipelineStage] = Relationship(sa_relationship_kwargs={"foreign_keys": "Decision.from_stage_id"})
    to_stage: Optional[PipelineStage] = Relationship(sa_relationship_kwargs={"foreign_keys": "Decision.to_stage_id"})


class Notification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    type: str = Field(max_length=30)
    send_status: str = Field(max_length=20)
    message_id: Optional[str] = Field(default=None)
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = Field(default=0)

    application: Application = Relationship(back_populates="notifications")


class PrivacyRequestLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    requested_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    action: str = Field(max_length=50)
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None

    application: Optional[Application] = Relationship(back_populates="privacy_requests")

