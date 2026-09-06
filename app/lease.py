"""Lease form model and PandaDoc token mapping.

Every field here corresponds to a blank in the source lease, transcribed in
`originals/lease_transcript_verbatim.md`. Section numbers in comments refer to
that document.

Terminology note: the lease document says "Lessee". The landlord-facing
dashboard calls the same person an "Approved Potential Tenant". The model keeps
the legal term because the tokens feed a legal document.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

MONTHS = list(calendar.month_name)[1:]


def ordinal(day: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', 23 -> '23rd'."""
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def money(amount: Decimal) -> str:
    """Decimal('1850') -> '1,850.00'. The lease reads '<blank> dollars'."""
    return f"{amount:,.2f}"


def two_digit_year(year: int) -> str:
    """The lease pre-prints '20__', so only the last two digits go in."""
    return f"{year % 100:02d}"


class Tenant(BaseModel):
    """An approved potential tenant - the "Lessee" of the lease document."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class LeaseRequest(BaseModel):
    """What the landlord fills in on the dashboard."""

    # Preamble. The Lessor is chosen by id; the server resolves name and email
    # so the browser cannot supply an arbitrary signer.
    lessor_id: str = Field(min_length=1, max_length=64)
    premises_address: str = Field(min_length=1, max_length=300)
    tenants: list[Tenant] = Field(min_length=1, max_length=3)

    # Section 1 - TERM
    term_start: date
    term_end_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    # Section 2 - RENT
    monthly_rent: Decimal = Field(gt=0, le=Decimal("1000000"))
    discounted_rent: Decimal | None = None

    # Section 3 - SECURITY DEPOSIT
    security_deposit: Decimal = Field(ge=0, le=Decimal("1000000"))

    # Section 4 - OCCUPANTS
    occupants: str = Field(min_length=1, max_length=1000)

    # Section 13 - UTILITIES ("Lessee agrees to pay all utilities ... except __")
    utilities_excluded: str = Field(default="none", max_length=200)

    # Execution block
    execution_city: str = Field(default="New Orleans", min_length=1, max_length=100)
    execution_date: date = Field(default_factory=date.today)

    @field_validator("premises_address", "occupants", "utilities_excluded",
                     "execution_city")
    @classmethod
    def _collapse_whitespace(cls, v: str) -> str:
        return re.sub(r"[ \t]+", " ", v).strip()

    @field_validator("monthly_rent", "discounted_rent", "security_deposit")
    @classmethod
    def _quantize(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else v.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def _check_term(self) -> "LeaseRequest":
        if self.term_end_date <= self.term_start:
            raise ValueError("Lease end month must fall after the start date.")
        if self.discounted_rent is not None and self.discounted_rent > self.monthly_rent:
            raise ValueError("Discounted rent cannot exceed the monthly rent.")
        return self

    @property
    def term_end_date(self) -> date:
        """Section 1 ends the lease on the last day of the chosen month."""
        year, month = (int(part) for part in self.term_end_month.split("-"))
        return date(year, month, calendar.monthrange(year, month)[1])

    def net_rent(self, discount: Decimal) -> Decimal:
        """Section 2's on-time-payment rent, floored at zero."""
        if self.discounted_rent is not None:
            return self.discounted_rent
        return max(Decimal("0.00"), self.monthly_rent - discount)

    def tenant_block(self) -> str:
        """The names that fill the 'hereinafter referred to as Lessee' line."""
        return "; ".join(t.full_name for t in self.tenants)

    def document_name(self) -> str:
        return f"Lease - {self.premises_address} - {self.tenant_block()}"

    def tokens(self, *, lessor_name: str, discount: Decimal) -> list[dict[str, str]]:
        """Map the form onto the tokens defined in pandadoc/TEMPLATE_SETUP.md."""
        end = self.term_end_date
        values: dict[str, str] = {
            "Lessor.Name": lessor_name,
            "Lessee.Names": self.tenant_block(),
            "Premises.Address": self.premises_address,
            "Term.StartDay": ordinal(self.term_start.day),
            "Term.StartMonth": MONTHS[self.term_start.month - 1],
            "Term.StartYear": two_digit_year(self.term_start.year),
            "Term.EndMonth": MONTHS[end.month - 1],
            "Term.EndYear": two_digit_year(end.year),
            "Rent.Monthly": money(self.monthly_rent),
            "Rent.Discounted": money(self.net_rent(discount)),
            "Deposit.Amount": money(self.security_deposit),
            "Occupants.List": self.occupants,
            "Utilities.Excluded": self.utilities_excluded or "none",
            "Execution.City": self.execution_city,
            "Execution.Day": ordinal(self.execution_date.day),
            "Execution.Month": MONTHS[self.execution_date.month - 1],
            "Execution.Year": two_digit_year(self.execution_date.year),
        }
        return [{"name": key, "value": value} for key, value in values.items()]

    def recipients(self, *, lessor_name: str,
                   lessor_email: str) -> list[dict[str, Any]]:
        """Lessor signs first, then each tenant.

        Role names must match the template's roles exactly.
        """
        first, _, rest = lessor_name.partition(" ")
        people: list[dict[str, Any]] = [
            {
                "email": lessor_email,
                "first_name": first,
                "last_name": rest or "Lessor",
                "role": "Lessor",
                "signing_order": 1,
            }
        ]
        for index, tenant in enumerate(self.tenants, start=1):
            people.append(
                {
                    "email": tenant.email,
                    "first_name": tenant.first_name,
                    "last_name": tenant.last_name,
                    "role": "Lessee" if index == 1 else f"Lessee{index}",
                    "signing_order": 2,
                }
            )
        return people
