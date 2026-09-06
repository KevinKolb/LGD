"""Tests for password hashing and PandaDoc webhook signature verification."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from app.auth import check_credentials, hash_password, verify_password
from app.pandadoc import verify_webhook_signature

# Low iteration count keeps the suite fast; production uses the module default.
FAST = 1_000


def test_hash_is_salted_so_two_hashes_differ() -> None:
    first = hash_password("correct horse battery", iterations=FAST)
    second = hash_password("correct horse battery", iterations=FAST)
    assert first != second
    assert verify_password("correct horse battery", first)
    assert verify_password("correct horse battery", second)


def test_hash_never_contains_the_password() -> None:
    encoded = hash_password("hunter2-hunter2-hunter2", iterations=FAST)
    assert "hunter2" not in encoded


def test_wrong_password_is_rejected() -> None:
    encoded = hash_password("right password here", iterations=FAST)
    assert not verify_password("wrong password here", encoded)
    assert not verify_password("", encoded)


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "garbage",
        "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA==",
        "md5$1000$c2FsdA==$aGFzaA==",  # wrong algorithm
        "pbkdf2_sha256$1000$c2FsdA==",  # too few parts
    ],
)
def test_malformed_hashes_fail_closed(encoded: str) -> None:
    assert not verify_password("anything", encoded)


def test_check_credentials_requires_both_halves() -> None:
    encoded = hash_password("a good long password", iterations=FAST)
    assert check_credentials(
        "kevin", "a good long password",
        expected_username="kevin", expected_hash=encoded,
    )
    assert not check_credentials(
        "eve", "a good long password",
        expected_username="kevin", expected_hash=encoded,
    )
    assert not check_credentials(
        "kevin", "wrong",
        expected_username="kevin", expected_hash=encoded,
    )


# ---------------------------------------------------------------------------
# Webhook signatures
# ---------------------------------------------------------------------------

SHARED_KEY = "shared-key-from-the-developer-dashboard"
BODY = b'[{"event":"document_state_changed","data":{"id":"abc","status":"document.completed"}}]'


def sign(body: bytes, key: str = SHARED_KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_is_accepted() -> None:
    assert verify_webhook_signature(SHARED_KEY, BODY, sign(BODY))


def test_signature_is_rejected_when_the_body_changed() -> None:
    signature = sign(BODY)
    tampered = BODY.replace(b"document.completed", b"document.declined")
    assert not verify_webhook_signature(SHARED_KEY, tampered, signature)


def test_signature_from_a_different_key_is_rejected() -> None:
    assert not verify_webhook_signature(SHARED_KEY, BODY, sign(BODY, "wrong-key"))


@pytest.mark.parametrize("signature", ["", "   ", "not-hex", "abc123"])
def test_bad_signature_values_are_rejected(signature: str) -> None:
    assert not verify_webhook_signature(SHARED_KEY, BODY, signature)


def test_surrounding_whitespace_is_tolerated() -> None:
    assert verify_webhook_signature(SHARED_KEY, BODY, f"  {sign(BODY)}\n")


def test_reserialized_json_does_not_match() -> None:
    """The raw bytes must be verified, not a re-encoded copy of the JSON."""
    import json

    reserialized = json.dumps(json.loads(BODY)).encode()
    assert reserialized != BODY
    assert not verify_webhook_signature(SHARED_KEY, reserialized, sign(BODY))
