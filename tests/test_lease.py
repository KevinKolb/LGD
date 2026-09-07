"""Unit tests for the lease form model and token mapping."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.lease import (
    PARKING_CLAUSE_TEXT,
    PARKING_NOT_AVAILABLE_TEXT,
    LeaseRequest,
    money,
    ordinal,
    strike,
    two_digit_year,
)

DISCOUNT = Decimal("50")


def make_lease(**overrides) -> LeaseRequest:
    payload = {
        "lessor_id": "1",
        "premises_address": "1556 Camp Street, Unit B",
        "tenants": [
            {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}
        ],
        "term_start": "2026-10-01",
        "term_end_month": "2027-09",
        "monthly_rent": "1850",
        "security_deposit": "1850",
        "occupants": "Jane Doe",
        "execution_date": "2026-09-15",
    }
    payload.update(overrides)
    return LeaseRequest.model_validate(payload)


@pytest.mark.parametrize(
    "day,expected",
    [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"),
     (13, "13th"), (21, "21st"), (22, "22nd"), (23, "23rd"), (30, "30th")],
)
def test_ordinal(day: int, expected: str) -> None:
    assert ordinal(day) == expected


def test_money_uses_thousands_separator_and_cents() -> None:
    assert money(Decimal("1850")) == "1,850.00"
    assert money(Decimal("950.5")) == "950.50"


def test_two_digit_year_matches_preprinted_20() -> None:
    # The lease pre-prints "20__", so only the last two digits are supplied.
    assert two_digit_year(2026) == "26"
    assert two_digit_year(2005) == "05"


def test_term_end_falls_on_last_day_of_month() -> None:
    assert make_lease(term_end_month="2027-02").term_end_date == date(2027, 2, 28)
    # Leap year.
    assert make_lease(term_end_month="2028-02").term_end_date == date(2028, 2, 29)


def test_net_rent_applies_discount_by_default() -> None:
    assert make_lease().net_rent(DISCOUNT) == Decimal("1800.00")


def test_net_rent_honours_explicit_override() -> None:
    lease = make_lease(monthly_rent="1850", discounted_rent="1775")
    assert lease.net_rent(DISCOUNT) == Decimal("1775.00")


def test_net_rent_never_goes_negative() -> None:
    assert make_lease(monthly_rent="30").net_rent(DISCOUNT) == Decimal("0.00")


def test_tokens_cover_every_template_placeholder() -> None:
    tokens = make_lease().tokens(lessor_name="Pat Landlord", discount=DISCOUNT)
    by_name = {token["name"]: token["value"] for token in tokens}

    assert by_name == {
        "Lessor.Name": "Pat Landlord",
        "Lessee.Names": "Jane Doe",
        "Premises.Address": "1556 Camp Street, Unit B",
        "Term.StartDay": "1st",
        "Term.StartMonth": "October",
        "Term.StartYear": "26",
        "Term.EndMonth": "September",
        "Term.EndYear": "27",
        "Rent.Monthly": "1,850.00",
        "Rent.Discounted": "1,800.00",
        "Deposit.Amount": "1,850.00",
        "Occupants.List": "Jane Doe",
        "Utilities.Excluded": "none",
        "Parking.Clause": f"( ) {strike(PARKING_NOT_AVAILABLE_TEXT)}  (X) {PARKING_CLAUSE_TEXT}",
        "Execution.City": "New Orleans",
        "Execution.Day": "15th",
        "Execution.Month": "September",
        "Execution.Year": "26",
    }


def test_parking_clause_is_normal_when_available() -> None:
    # "Available but limited" is the chosen radio option - it stays plain;
    # "not available" is the unchosen one, so it's struck through instead.
    lease = make_lease(parking_not_available=False)
    clause = lease.parking_clause()
    assert clause == f"( ) {strike(PARKING_NOT_AVAILABLE_TEXT)}  (X) {PARKING_CLAUSE_TEXT}"


def test_parking_clause_is_struck_through_when_unavailable() -> None:
    # "Not available" is now the chosen option - it stays plain; "available
    # but limited" becomes the unchosen one and gets struck through.
    lease = make_lease(parking_not_available=True)
    clause = lease.parking_clause()
    assert clause == f"(X) {PARKING_NOT_AVAILABLE_TEXT}  ( ) {strike(PARKING_CLAUSE_TEXT)}"


def test_multiple_tenants_join_into_the_lessee_line() -> None:
    lease = make_lease(
        tenants=[
            {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"},
            {"first_name": "John", "last_name": "Roe", "email": "john@example.com"},
        ]
    )
    assert lease.tenant_block() == "Jane Doe; John Roe"


def test_recipients_put_lessor_first_and_number_extra_tenants() -> None:
    lease = make_lease(
        tenants=[
            {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"},
            {"first_name": "John", "last_name": "Roe", "email": "john@example.com"},
        ]
    )
    recipients = lease.recipients(
        lessor_name="Pat Landlord", lessor_email="pat@example.com"
    )

    assert [r["role"] for r in recipients] == ["Lessor", "Lessee", "Lessee2"]
    assert [r["signing_order"] for r in recipients] == [1, 2, 2]
    assert recipients[0]["email"] == "pat@example.com"
    assert recipients[0]["first_name"] == "Pat"
    assert recipients[0]["last_name"] == "Landlord"


def test_single_word_lessor_name_still_produces_a_last_name() -> None:
    # PandaDoc rejects a blank last_name, so a mononym falls back to "Lessor".
    recipients = make_lease().recipients(
        lessor_name="Robertson", lessor_email="pat@example.com"
    )
    assert recipients[0]["first_name"] == "Robertson"
    assert recipients[0]["last_name"] == "Lessor"


def test_end_month_must_be_after_start() -> None:
    with pytest.raises(ValidationError, match="after the start date"):
        make_lease(term_start="2026-10-01", term_end_month="2026-09")


def test_discount_cannot_exceed_rent() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        make_lease(monthly_rent="1000", discounted_rent="1200")


def test_at_least_one_tenant_is_required() -> None:
    with pytest.raises(ValidationError):
        make_lease(tenants=[])


def test_at_most_three_tenants() -> None:
    person = {"first_name": "A", "last_name": "B", "email": "a@example.com"}
    with pytest.raises(ValidationError):
        make_lease(tenants=[person] * 4)


def test_bad_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_lease(
            tenants=[{"first_name": "Jane", "last_name": "Doe", "email": "not-an-email"}]
        )


def test_whitespace_is_collapsed() -> None:
    lease = make_lease(premises_address="  1556   Camp   Street  ")
    assert lease.premises_address == "1556 Camp Street"
