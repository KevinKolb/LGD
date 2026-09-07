"""Request models for the tenant-facing page: public rental applications,
notices a landlord/admin sends to a specific tenant, and news a landlord/
admin posts.

Kept separate from app/lease.py, which is about the PandaDoc lease itself -
these two features don't touch PandaDoc at all.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class Roommate(BaseModel):
    """Someone applying alongside the primary applicant - just their name
    and contact info for now. Not yet a separate application of their own:
    the plan is to later send each roommate their own application to fill
    out and tie the set together, but that's not built yet - for now this
    is only a household-size hint for whoever reviews the application."""

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class ApplicationRequest(BaseModel):
    """A prospective tenant's rental application. Submitted with no login -
    see the public /applicant/ page - so every field is treated as untrusted
    input, same as any other public form."""

    applicant_name: str = Field(min_length=1, max_length=200)
    applicant_email: EmailStr
    applicant_phone: str = Field(min_length=1, max_length=40)
    consent_to_text: bool = False
    # Free text, not a known landlord id - the applicant describes whatever
    # property they're interested in in their own words. This means an
    # application can no longer be scoped to one landlord server-side; see
    # api_list_applications in app/main.py, which is admin-only because of it.
    property_interest: str = Field(default="", max_length=300)
    desired_move_in: str = Field(default="", max_length=100)
    message: str = Field(default="", max_length=2000)
    roommates: list[Roommate] = Field(default_factory=list, max_length=10)


class NoticeRequest(BaseModel):
    """A free-form message a landlord/admin sends one tenant."""

    tenant_username: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class NewsRequest(BaseModel):
    """A news post a landlord/admin publishes for one landlord."""

    landlord_id: str = Field(min_length=1, max_length=100)
    headline: str = Field(min_length=1, max_length=200)
    article: str = Field(min_length=1, max_length=5000)
