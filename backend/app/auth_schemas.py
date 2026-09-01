from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class ReviewerRole(str, Enum):
    reviewer = "reviewer"
    administrator = "administrator"


class LoginRequest(BaseModel):
    # Whitespace stripping is applied to the email only. A password
    # must be verified exactly as the reviewer typed it.
    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        min_length=3,
        max_length=200,
    )

    password: str = Field(
        min_length=1,
        max_length=200,
    )

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class ReviewerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: ReviewerRole
    is_active: bool
    created_at: datetime


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    reviewer: ReviewerRead
