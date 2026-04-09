"""Pydantic DTOs for job description (broadcasting) APIs."""

from typing import Optional

from pydantic import BaseModel, Field


class GenerateJdDto(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=16000,
        description="HR brief / prompt for generating the job description",
    )


class JobDescriptionUpdateDto(BaseModel):
    role: Optional[str] = Field(None, max_length=8000)
    experience: Optional[str] = Field(None, max_length=8000)
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    qualifications: Optional[str] = None
    eligibility: Optional[str] = None
    application_link: Optional[str] = Field(None, max_length=1024)
    hr_query: Optional[str] = Field(None, max_length=16000)
