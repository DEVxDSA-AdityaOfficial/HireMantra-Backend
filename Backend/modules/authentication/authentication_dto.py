"""Pydantic DTOs for authentication (OTP, JWT)."""

from pydantic import BaseModel, EmailStr, Field


class OtpRequestDto(BaseModel):
    email: EmailStr


class OtpVerifyDto(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=12)
