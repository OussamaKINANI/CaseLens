import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import pbkdf2_hmac
from uuid import UUID

import jwt

from app.auth_schemas import ReviewerRole
from app.config import settings


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"

# OWASP guidance for PBKDF2-HMAC-SHA256 (2024). Sign-in is a rare,
# interactive operation, so a deliberately slow hash is affordable.
PASSWORD_HASH_ITERATIONS = 600_000

PASSWORD_SALT_BYTES = 16

JWT_ALGORITHM = "HS256"


class InvalidAccessTokenError(Exception):
    """Raised when a bearer token cannot be trusted."""


@dataclass(frozen=True)
class AccessTokenClaims:
    reviewer_id: UUID
    role: ReviewerRole
    expires_at: datetime


def _encode_segment(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_segment(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)

    return urlsafe_b64decode(value + padding)


def _derive_key(
    password: str,
    *,
    salt: bytes,
    iterations: int,
) -> bytes:
    return pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)

    derived_key = _derive_key(
        password,
        salt=salt,
        iterations=PASSWORD_HASH_ITERATIONS,
    )

    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            _encode_segment(salt),
            _encode_segment(derived_key),
        ]
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_key = (
            encoded_hash.split("$")
        )

        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False

        iterations = int(raw_iterations)
        salt = _decode_segment(raw_salt)
        expected_key = _decode_segment(raw_key)
    except (ValueError, TypeError):
        # A stored hash we cannot parse never authenticates anyone.
        return False

    candidate_key = _derive_key(
        password,
        salt=salt,
        iterations=iterations,
    )

    return hmac.compare_digest(candidate_key, expected_key)


@lru_cache(maxsize=1)
def _unusable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def spend_password_verification_time() -> None:
    """Burn one hash verification for an unknown reviewer.

    Sign-in failures should cost the same whether or not the email
    exists, so an attacker cannot enumerate reviewers by timing.
    """
    verify_password(
        secrets.token_urlsafe(32),
        _unusable_password_hash(),
    )


def create_access_token(
    *,
    reviewer_id: UUID,
    role: ReviewerRole,
    expires_in_seconds: int | None = None,
) -> tuple[str, int]:
    """Return a signed bearer token and its lifetime in seconds."""
    lifetime_seconds = (
        expires_in_seconds
        if expires_in_seconds is not None
        else settings.access_token_expire_minutes * 60
    )

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=lifetime_seconds)

    token = jwt.encode(
        {
            "sub": str(reviewer_id),
            "role": role.value,
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )

    return token, lifetime_seconds


def decode_access_token(token: str) -> AccessTokenClaims:
    try:
        # Pinning the algorithm list rejects "alg": "none" and any
        # attempt to have the secret verified as a public key.
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "exp", "iat"],
            },
        )
    except jwt.PyJWTError as error:
        raise InvalidAccessTokenError(str(error)) from error

    try:
        reviewer_id = UUID(payload["sub"])
        role = ReviewerRole(payload["role"])
    except (KeyError, ValueError, AttributeError, TypeError) as error:
        raise InvalidAccessTokenError(
            "Access token claims are malformed"
        ) from error

    return AccessTokenClaims(
        reviewer_id=reviewer_id,
        role=role,
        expires_at=datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.utc,
        ),
    )
