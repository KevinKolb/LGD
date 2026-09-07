"""Request models for the tenant-facing page: public rental applications, and
notices a landlord/admin sends to a specific tenant.

Kept separate from app/lease.py, which is about the PandaDoc lease itself -
these two features don't touch PandaDoc at all.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class ApplicationRequest(BaseModel):
    """A prospective tenant's rental application. Submitted with no login -
    see the public /tenant/ page - so every field is treated as untrusted
    input, same as any other public form."""

    applicant_name: str = Field(min_length=1, max_length=200)
    applicant_email: EmailStr
    applicant_phone: str = Field(default="", max_length=40)
    landlord_id: str | None = None
    desired_move_in: str = Field(default="", max_length=100)
    message: str = Field(default="", max_length=2000)


class NoticeRequest(BaseModel):
    """A free-form message a landlord/admin sends one tenant."""

    tenant_username: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
