from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Column, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)  # también protegido sin distinguir mayúsculas en PostgreSQL
    role: str = Field(default="recruiter")  # 'recruiter' o 'admin'
    password_hash: str
    is_active: bool = Field(default=True)
    last_login_at: Optional[datetime] = None
    failed_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = None
    password_changed_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    candidate_profile: Optional["CandidateProfile"] = Relationship(back_populates="user")
    decisions: List["Decision"] = Relationship(back_populates="user")
    sourcing_prospects_created: List["SourcingProspect"] = Relationship(back_populates="created_by")


class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    industry: Optional[str] = None
    description: Optional[str] = None

    job_offers: List["JobOffer"] = Relationship(back_populates="company")


class CandidateProfile(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_candidateprofile_user_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    full_name: str
    resume_url: Optional[str] = None
    extracted_text: Optional[str] = None

    phone: Optional[str] = None
    rut: Optional[str] = Field(default=None, max_length=15)
    tech_stack: Optional[str] = None
    years_of_experience: Optional[int] = None
    courses_and_diplomas: Optional[str] = None
    career_summary: Optional[str] = None
    salary_expectation: Optional[str] = None
    professional_headline: Optional[str] = None
    source: Optional[str] = Field(default=None, max_length=30)
    source_url: Optional[str] = Field(default=None, max_length=500)
    contact_status: str = Field(default="not_contacted", max_length=30)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    invited_job_offer_id: Optional[int] = Field(default=None, foreign_key="joboffer.id")
    invitation_expires_at: Optional[datetime] = None
    archived_at: Optional[datetime] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    embedding: Optional[List[float]] = Field(sa_column=Column(Vector(1536)))

    user: User = Relationship(back_populates="candidate_profile")
    applications: List["Application"] = Relationship(back_populates="candidate")
    sourcing_prospects: List["SourcingProspect"] = Relationship(back_populates="candidate_profile")
    resume_versions: List["CandidateResumeVersion"] = Relationship(
        back_populates="candidate",
        cascade_delete=True,
    )


class JobOffer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: str = Field(
        default_factory=lambda: str(uuid4()),
        max_length=36,
        index=True,
        unique=True,
    )
    company_id: int = Field(foreign_key="company.id")
    title: str
    description: str
    requirements: str
    tech_stack: str
    salary_range: str
    experience_years: int
    seniority: str
    country: Optional[str] = None
    modality: Optional[str] = None
    message: Optional[str] = None
    status: str = Field(default="open")  # 'open', 'closed' (reabrible), 'closed_final'
    embedding: Optional[List[float]] = Field(sa_column=Column(Vector(1536)))

    company: Company = Relationship(back_populates="job_offers")
    applications: List["Application"] = Relationship(back_populates="job_offer")
    stages: List["PipelineStage"] = Relationship(back_populates="job_offer", cascade_delete=True)
    sourcing_prospects: List["SourcingProspect"] = Relationship(back_populates="job_offer")


class CandidateResumeVersion(SQLModel, table=True):
    """Snapshot append-only de cada CV recibido para una persona."""

    __table_args__ = (
        UniqueConstraint("file_sha256", name="uq_candidateresumeversion_file_sha256"),
        CheckConstraint(
            "source IN ('pri', 'application_link', 'sourcing', 'profile_update', 'legacy')",
            name="ck_candidateresumeversion_source",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidateprofile.id", index=True)
    job_offer_id: Optional[int] = Field(default=None, foreign_key="joboffer.id", index=True)
    uploaded_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    resume_url: str = Field(max_length=1000)
    original_filename: str = Field(max_length=255)
    file_sha256: Optional[str] = Field(default=None, max_length=64, index=True)
    source: str = Field(max_length=30)
    extracted_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    tech_stack: Optional[str] = Field(default=None, sa_column=Column(Text))
    years_of_experience: Optional[int] = None
    courses_and_diplomas: Optional[str] = Field(default=None, sa_column=Column(Text))
    career_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    candidate: CandidateProfile = Relationship(back_populates="resume_versions")


class SourcingProspect(SQLModel, table=True):
    """Gestión de un perfil encontrado externamente para una vacante concreta.

    Esta entidad no representa una postulación. El vínculo con ``Application`` se
    materializa únicamente cuando el prospecto acepta, entrega un CV vigente y
    consiente el tratamiento de sus datos.
    """

    __table_args__ = (
        UniqueConstraint("candidate_profile_id", "job_offer_id", name="uq_sourcingprospect_candidate_job"),
        CheckConstraint(
            "source IN ('linkedin', 'computrabajo', 'laborum', 'referido', 'otro')",
            name="ck_sourcingprospect_source",
        ),
        CheckConstraint(
            "status IN ('identificado', 'contactado', 'interesado', 'invitado', "
            "'no_interesado', 'sin_respuesta', 'convertido')",
            name="ck_sourcingprospect_status",
        ),
        CheckConstraint(
            "semantic_similarity IS NULL OR (semantic_similarity >= 0 AND semantic_similarity <= 100)",
            name="ck_sourcingprospect_similarity",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_profile_id: int = Field(foreign_key="candidateprofile.id", index=True)
    job_offer_id: int = Field(foreign_key="joboffer.id", index=True)
    created_by_user_id: int = Field(foreign_key="user.id", index=True)
    source: str = Field(max_length=30)
    source_url: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="identificado", max_length=30, index=True)
    semantic_similarity: Optional[float] = None
    match_explanation: Optional[str] = Field(default=None, sa_column=Column(Text))
    contact_channel: Optional[str] = Field(default=None, max_length=30)
    contact_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    invitation_token_hash: Optional[str] = Field(default=None, max_length=64, index=True)
    invitation_expires_at: Optional[datetime] = None
    authorization_channel: Optional[str] = Field(default=None, max_length=50)
    authorization_at: Optional[datetime] = None
    authorization_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    contacted_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    invited_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    candidate_profile: CandidateProfile = Relationship(back_populates="sourcing_prospects")
    job_offer: JobOffer = Relationship(back_populates="sourcing_prospects")
    created_by: User = Relationship(back_populates="sourcing_prospects_created")

class PipelineStage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_offer_id: int = Field(foreign_key="joboffer.id")
    name: str = Field(max_length=60)
    order_index: int
    kind: str = Field(default="proceso", max_length=15)

    job_offer: "JobOffer" = Relationship(back_populates="stages")
    applications: List["Application"] = Relationship(back_populates="current_stage")


class Application(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_offer_id", name="uq_application_candidate_job"),
        CheckConstraint(
            "origin IN ('pri', 'application_link', 'sourcing')",
            name="ck_application_origin",
        ),
        CheckConstraint(
            "evaluation_status IN ('pending', 'available', 'unavailable')",
            name="ck_application_evaluation_status",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidateprofile.id")
    job_offer_id: Optional[int] = Field(default=None, foreign_key="joboffer.id")
    status: str = Field(default="pending")  # Legacy, will be replaced by current_stage_id + outcome conceptually
    current_stage_id: Optional[int] = Field(default=None, foreign_key="pipelinestage.id")
    outcome: Optional[str] = Field(default=None, max_length=15)
    similarity_score: Optional[float] = None
    evaluation_status: str = Field(default="pending", max_length=20)
    evaluation_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    consent_given_at: Optional[datetime] = None
    consent_text_version: Optional[str] = Field(default=None, max_length=50)
    consent_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    origin: str = Field(default="application_link", max_length=30)
    archived_at: Optional[datetime] = Field(default=None, index=True)

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
    feedback: Optional[str] = Field(default=None, sa_column=Column(Text))
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    from_stage_id: Optional[int] = Field(default=None, foreign_key="pipelinestage.id")
    to_stage_id: Optional[int] = Field(default=None, foreign_key="pipelinestage.id")

    application: Application = Relationship(back_populates="decisions")
    user: User = Relationship(back_populates="decisions")
    from_stage: Optional[PipelineStage] = Relationship(sa_relationship_kwargs={"foreign_keys": "Decision.from_stage_id"})
    to_stage: Optional[PipelineStage] = Relationship(sa_relationship_kwargs={"foreign_keys": "Decision.to_stage_id"})
    notifications: List["Notification"] = Relationship(back_populates="decision")


class Notification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    decision_id: Optional[int] = Field(default=None, foreign_key="decision.id")
    type: str = Field(max_length=30)
    send_status: str = Field(max_length=20)
    message_id: Optional[str] = Field(default=None)
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = Field(default=0)

    application: Application = Relationship(back_populates="notifications")
    decision: Optional[Decision] = Relationship(back_populates="notifications")


class PrivacyRequestLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    requested_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    action: str = Field(max_length=50)
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None

    application: Optional[Application] = Relationship(back_populates="privacy_requests")
