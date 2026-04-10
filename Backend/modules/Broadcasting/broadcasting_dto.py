"""Pydantic DTOs for job description (broadcasting) APIs."""

from typing import Literal, Optional

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


class CreateBroadcastPostStructureDto(BaseModel):
    """Channel-specific post skeletons derived from the JD (LinkedIn, Unstop)."""

    channels: list[str] = Field(
        default_factory=lambda: ["linkedin", "unstop"],
        description="Lower-case names, e.g. linkedin, unstop",
    )


class GenerateBroadcastMediaDto(BaseModel):
    """Generate image (Gemini image) or video (Veo 3.1) from JD context."""

    content_type: Literal["image", "video"] = Field(
        ...,
        description="image: gemini-2.5-flash-image; video: veo-3.1-generate-preview",
    )
    aspect_ratio: Optional[str] = Field(
        "9:16",
        description="Video only: e.g. 9:16, 16:9, 1:1",
    )
    extra_context: Optional[str] = Field(
        None,
        max_length=4000,
        description="Appended to the auto-built media prompt",
    )
    use_structure_creative_brief: bool = Field(
        False,
        description="If true, first builds post structures and uses creative_brief_for_media in the visual prompt",
    )
    max_wait_seconds: float = Field(
        600.0,
        ge=60.0,
        le=3600.0,
        description="Video only: max seconds to poll Veo",
    )
    poll_interval_seconds: float = Field(
        10.0,
        ge=2.0,
        le=60.0,
        description="Video only: seconds between status polls",
    )
