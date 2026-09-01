import json
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from uuid import uuid4

import jwt
import pytest

from app.auth_schemas import ReviewerRole
from app.config import settings
from app.security import (
    InvalidAccessTokenError,
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_salted() -> None:
    first_hash = hash_password("correct horse battery staple")
    second_hash = hash_password("correct horse battery staple")

    assert first_hash != second_hash
    assert "correct horse battery staple" not in first_hash


def test_verify_password_accepts_the_original_password() -> None:
    encoded_hash = hash_password("reviewer-password")

    assert verify_password("reviewer-password", encoded_hash)


def test_verify_password_rejects_a_wrong_password() -> None:
    encoded_hash = hash_password("reviewer-password")

    assert not verify_password("Reviewer-Password", encoded_hash)
    assert not verify_password("", encoded_hash)


@pytest.mark.parametrize(
    "stored_hash",
    [
        "",
        "not-a-hash",
        "pbkdf2_sha256$notanumber$c2FsdA$aGFzaA",
        "argon2$600000$c2FsdA$aGFzaA",
    ],
)
def test_verify_password_rejects_unusable_stored_hashes(
    stored_hash: str,
) -> None:
    assert not verify_password("reviewer-password", stored_hash)


def test_access_token_round_trip() -> None:
    reviewer_id = uuid4()

    token, expires_in_seconds = create_access_token(
        reviewer_id=reviewer_id,
        role=ReviewerRole.administrator,
    )

    claims = decode_access_token(token)

    assert expires_in_seconds == (
        settings.access_token_expire_minutes * 60
    )
    assert claims.reviewer_id == reviewer_id
    assert claims.role is ReviewerRole.administrator
    assert claims.expires_at > datetime.now(timezone.utc)


def test_decode_rejects_a_tampered_token() -> None:
    token, _ = create_access_token(
        reviewer_id=uuid4(),
        role=ReviewerRole.reviewer,
    )

    header, payload, signature = token.split(".")
    tampered_token = f"{header}.{payload}x.{signature}"

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(tampered_token)


def test_decode_rejects_a_token_signed_with_another_key() -> None:
    forged_token = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": ReviewerRole.administrator.value,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc).timestamp() + 3600,
        },
        "an-attacker-controlled-signing-key",
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(forged_token)


def test_decode_rejects_an_expired_token() -> None:
    token, _ = create_access_token(
        reviewer_id=uuid4(),
        role=ReviewerRole.reviewer,
        expires_in_seconds=-1,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_decode_rejects_an_unsigned_token() -> None:
    def encode_segment(value: dict[str, object]) -> str:
        return (
            urlsafe_b64encode(json.dumps(value).encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )

    header = encode_segment({"alg": "none", "typ": "JWT"})

    payload = encode_segment(
        {
            "sub": str(uuid4()),
            "role": ReviewerRole.administrator.value,
            "iat": 1_756_000_000,
            "exp": 4_102_444_800,
        }
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(f"{header}.{payload}.")


def test_decode_rejects_missing_or_malformed_claims() -> None:
    without_subject = jwt.encode(
        {
            "role": ReviewerRole.reviewer.value,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc).timestamp() + 3600,
        },
        settings.jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(without_subject)

    with_unknown_role = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": "chief-of-medicine",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc).timestamp() + 3600,
        },
        settings.jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(with_unknown_role)
