"""Optional typed responses for careers listing (OpenAPI)."""

from typing import Optional

from pydantic import BaseModel


class JobDescriptionPublicItem(BaseModel):
    """JD fields returned for public careers listings."""

    jd_id: str
    organization_id: str
    role: str
    experience: str
    requirements: str
    responsibilities: str
    qualifications: str
    eligibility: str
    application_link: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
