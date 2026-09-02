from datetime import datetime
from enum import Enum
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.review_limits import MAX_REVIEW_DOCUMENTS


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ReviewRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    awaiting_human_review = "awaiting_human_review"
    completed = "completed"
    rejected = "rejected"
    failed = "failed"


class HumanReviewDecision(str, Enum):
    approve = "approve"
    reject = "reject"


class CaseReviewRunCreate(StrictModel):
    document_ids: list[UUID] = Field(
        min_length=1,
        max_length=MAX_REVIEW_DOCUMENTS,
    )

    @field_validator("document_ids")
    @classmethod
    def reject_duplicate_documents(
        cls,
        value: list[UUID],
    ) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError(
                "document_ids must not contain duplicates"
            )

        return value


class HumanReviewRequest(StrictModel):
    decision: HumanReviewDecision

    notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    @model_validator(mode="after")
    def require_rejection_notes(self) -> Self:
        if (
            self.decision is HumanReviewDecision.reject
            and not self.notes
        ):
            raise ValueError(
                "notes are required when rejecting a review"
            )

        return self


class CaseReviewRunRead(StrictModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    id: UUID
    case_id: UUID
    status: ReviewRunStatus
    document_ids: list[UUID]
    temporal_workflow_id: str | None
    failure_code: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

class ReviewWorkflowCommandResponse(StrictModel):
    review_run_id: UUID
    temporal_workflow_id: str

    command_status: Literal[
        "started",
        "already_started",
        "accepted",
    ]
