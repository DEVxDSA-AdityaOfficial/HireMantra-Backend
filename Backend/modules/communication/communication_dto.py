"""Request bodies for communication APIs."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class SendShortlistEmailDto(BaseModel):
    """If ``to_email`` is omitted, ``Candidate.email`` must be set."""

    to_email: Optional[EmailStr] = None
    extra_note: Optional[str] = Field(None, max_length=4000)


class SendRejectionEmailDto(BaseModel):
    to_email: Optional[EmailStr] = None
    extra_note: Optional[str] = Field(None, max_length=4000)


class ScheduleVoiceInterviewDto(BaseModel):
    """Optional phone override; otherwise uses ``Candidate.contact_phone``."""

    to_number: Optional[str] = Field(None, max_length=32)
    send_interview_invite_email: bool = False
    invite_to_email: Optional[EmailStr] = None
    invite_extra_note: Optional[str] = Field(None, max_length=2000)
