"""SQLAlchemy ORM models for HireMantra."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
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
