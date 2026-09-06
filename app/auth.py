"""Password hashing and constant-time credential checks.

Passwords are never stored in plaintext. `accounts.json` holds each user's
hash in the format:

    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

Set one with:  python -m app.accounts set-password <username>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

DEFAULT_ITERATIONS = 600_000
ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Return an encoded PBKDF2 hash for `password`."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(
        ALGORITHM,
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    """Timing-safe check of `password` against an encoded PBKDF2 hash."""
    try:
        algorithm, iterations_raw, salt_b64, hash_b64 = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(candidate, expected)


def check_credentials(username: str, password: str, *, expected_username: str,
                      expected_hash: str) -> bool:
    """Verify a username/password pair without leaking which half was wrong.

    Both comparisons always run, so the response time does not reveal whether
    the username existed. Callers with no real user to check against should
    still call this with a decoy hash, for the same reason.
    """
    user_ok = hmac.compare_digest(username.encode("utf-8"),
                                  expected_username.encode("utf-8"))
    pass_ok = verify_password(password, expected_hash)
    return user_ok and pass_ok
