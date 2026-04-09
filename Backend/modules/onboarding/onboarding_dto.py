"""Pydantic DTOs for onboarding registration and updates."""

from typing import Optional

from pydantic import BaseModel, Field


class OnboardingRegisterDto(BaseModel):
    member_name: str = Field(..., min_length=1, max_length=255)
    organization_name: str = Field(..., min_length=1, max_length=255)
    contact: str = Field(..., min_length=1, max_length=64)
    address: str = Field(..., min_length=1)
    team_size: str = Field(..., min_length=1, max_length=64)
    website: Optional[str] = Field(None, max_length=512)
    password: str = Field(..., min_length=8, max_length=128)


class OnboardingUpdateDto(BaseModel):
    member_name: Optional[str] = Field(None, max_length=255)
    organization_name: Optional[str] = Field(None, max_length=255)
    contact: Optional[str] = Field(None, max_length=64)
    address: Optional[str] = None
    team_size: Optional[str] = Field(None, max_length=64)
    website: Optional[str] = Field(None, max_length=512)
