"""SQLAlchemy ORM models for HireMantra."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Users(Base):
    """Authentication: email, password, OTP, verification."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    otp = Column(String(12), nullable=True)
    otp_created_at = Column(DateTime, nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organizations = relationship(
        "Organization",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Organization(Base):
    """
    Tenant root: generated organization_id at registration.
    Job descriptions and onboarding profile hang off this id.
    """

    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Users", back_populates="organizations")
    onboarding = relationship(
        "Onboarding",
        back_populates="organization",
        uselist=False,
        cascade="all, delete-orphan",
    )
    job_descriptions = relationship(
        "JobDescription",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class Onboarding(Base):
    """Organization profile: one row per organization."""

    __tablename__ = "onboarding"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    member_name = Column(String(255), nullable=False)
    organization_name = Column(String(255), nullable=False)
    contact = Column(String(64), nullable=False)
    address = Column(Text, nullable=False)
    team_size = Column(String(64), nullable=False)
    website = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="onboarding")


class JobDescription(Base):
    """Generated JD: stored under an organization; optional creator audit."""

    __tablename__ = "job_descriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    hr_query = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    experience = Column(Text, nullable=False)
    requirements = Column(Text, nullable=False)
    responsibilities = Column(Text, nullable=False)
    qualifications = Column(Text, nullable=False)
    eligibility = Column(Text, nullable=False)
    application_link = Column(String(1024), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="job_descriptions")
    creator = relationship("Users", backref="created_job_descriptions")
    candidates = relationship(
        "Candidate",
        back_populates="job_description",
        cascade="all, delete-orphan",
    )


class Candidate(Base):
    """Public job application against a published JD (careers)."""

    __tablename__ = "candidates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_description_id = Column(
        String(36),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name = Column(String(255), nullable=False)
    contact_phone = Column(String(64), nullable=False)
    email = Column(String(255), nullable=True, index=True)
    resume_relative_path = Column(String(1024), nullable=False)
    resume_original_filename = Column(String(512), nullable=False)
    screening_status = Column(
        String(32),
        nullable=False,
        default="pending",
    )
    ats_match_score = Column(Float, nullable=True)
    jd_match_analysis = Column(Text, nullable=True)
    screening_details_json = Column(Text, nullable=True)
    parsed_resume_summary = Column(Text, nullable=True)
    parser_error_message = Column(Text, nullable=True)
    screening_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    job_description = relationship("JobDescription", back_populates="candidates")
    notifications = relationship(
        "CandidateNotification",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    voice_interviews = relationship(
        "VoiceInterviewSession",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class CandidateNotification(Base):
    """Audit log of outbound emails to applicants (shortlist, rejection, interview)."""

    __tablename__ = "candidate_notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    candidate_id = Column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = Column(String(32), nullable=False, index=True)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(512), nullable=False)
    body_html = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="notifications")


class VoiceInterviewSession(Base):
    """Retell AI voice screening; transcript + LLM score/analysis after sync."""

    __tablename__ = "voice_interview_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    candidate_id = Column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    retell_call_id = Column(String(128), nullable=True, unique=True, index=True)
    from_number = Column(String(32), nullable=True)
    to_number = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="scheduled", index=True)
    transcript = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    retell_summary = Column(Text, nullable=True)
    interview_score = Column(Float, nullable=True)
    interview_analysis = Column(Text, nullable=True)
    interview_details_json = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="voice_interviews")
