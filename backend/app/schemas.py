from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CasePriority(str, Enum):
    routine = "routine"
    urgent = "urgent"


class CaseStatus(str, Enum):
    received = "received"
    processing = "processing"
    awaiting_review = "awaiting_review"
    completed = "completed"
    failed = "failed"


class CaseCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    patient_external_id: str = Field(
        min_length=1,
        max_length=100,
    )

    requested_service: str = Field(
        min_length=1,
        max_length=200,
    )

    priority: CasePriority = CasePriority.routine


class CaseRead(CaseCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: CaseStatus
    created_at: datetime

class CaseStatusUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: CaseStatus
    reason: str = Field(min_length=1, max_length=500)