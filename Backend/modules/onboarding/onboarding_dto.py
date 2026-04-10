"""Pydantic DTOs for onboarding registration and updates."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class OnboardingRegisterDto(BaseModel):
    """
    Public registration: ``email`` identifies the account (no JWT required).
    A ``model_validator`` also accepts common frontend keys: firstName, lastName,
    organization, teamSize, country.

    Address: if the client sends a non-empty ``address``, it is kept. ``country``
    is only used to fill ``address`` when ``address`` is missing or whitespace.
    """

    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    member_name: str = Field(..., min_length=1, max_length=255)
    organization_name: str = Field(..., min_length=1, max_length=255)
    contact: str = Field(..., min_length=1, max_length=64)
    address: str = Field(..., min_length=1)
    team_size: str = Field(..., min_length=1, max_length=64)
    website: Optional[str] = Field(None, max_length=512)
    password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def _map_frontend_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)

        if not (out.get("member_name") or "").strip():
            fn = (out.get("firstName") or out.get("first_name") or "").strip()
            ln = (out.get("lastName") or out.get("last_name") or "").strip()
            full = f"{fn} {ln}".strip()
            if full:
                out["member_name"] = full

        if not (out.get("organization_name") or "").strip():
            org = (out.get("organization") or out.get("organizationName") or "").strip()
            if org:
                out["organization_name"] = org

        if not (out.get("team_size") or "").strip():
            ts = (out.get("teamSize") or out.get("team_size") or "").strip()
            if ts:
                out["team_size"] = ts

        addr = (out.get("address") or "").strip()
        if not addr:
            c = (out.get("country") or "").strip()
            if c:
                out["address"] = c

        return out


class OnboardingUpdateDto(BaseModel):
    member_name: Optional[str] = Field(None, max_length=255)
    organization_name: Optional[str] = Field(None, max_length=255)
    contact: Optional[str] = Field(None, max_length=64)
    address: Optional[str] = None
    team_size: Optional[str] = Field(None, max_length=64)
    website: Optional[str] = Field(None, max_length=512)
