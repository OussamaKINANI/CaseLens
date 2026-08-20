from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventType,
)
from app.database import SessionLocal
from app.document_models import ClinicalDocumentRecord
from app.review_models import CaseReviewRunRecord
from app.review_schemas import ReviewRunStatus
from app.review_workflow import (
    AWAIT_HUMAN_REVIEW_ACTIVITY,
    FAIL_REVIEW_ACTIVITY,
    FINALIZE_REVIEW_ACTIVITY,
    START_REVIEW_ACTIVITY,
    VALIDATE_DOCUMENTS_ACTIVITY,
)
from app.temporal_models import (
    CaseReviewWorkflowInput,
    CaseReviewWorkflowResult,
    FailReviewActivityInput,
    FinalizeReviewActivityInput,
    ReviewRunActivityInput,
)
from app.models import CaseRecord  # noqa: F401

SessionFactory = Callable[[], Session]


class CaseReviewActivities:
    def __init__(
        self,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    def _get_review_run(
        self,
        database: Session,
        review_run_id: str,
    ) -> CaseReviewRunRecord:
        try:
            parsed_review_run_id = UUID(
                review_run_id
            )
        except ValueError as error:
            raise ApplicationError(
                "Invalid review-run identifier",
                type="InvalidReviewRunId",
                non_retryable=True,
            ) from error

        review_run = database.get(
            CaseReviewRunRecord,
            parsed_review_run_id,
        )

        if review_run is None:
            raise ApplicationError(
                "Review run was not found",
                type="ReviewRunNotFound",
                non_retryable=True,
            )

        return review_run

    def _add_status_audit_event(
        self,
        database: Session,
        *,
        review_run: CaseReviewRunRecord,
        previous_status: str,
        new_status: str,
    ) -> None:
        database.add(
            AuditEventRecord(
                case_id=review_run.case_id,
                event_type=(
                    AuditEventType.status_changed.value
                ),
                actor_type=(
                    AuditActorType.system.value
                ),
                details={
                    "entity_type": "case_review_run",
                    "review_run_id": str(
                        review_run.id
                    ),
                    "previous_status": (
                        previous_status
                    ),
                    "new_status": new_status,
                },
            )
        )

    @activity.defn(name=START_REVIEW_ACTIVITY)
    def start_case_review(
        self,
        activity_input: ReviewRunActivityInput,
    ) -> str:
        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            current_status = review_run.status

            if current_status in {
                ReviewRunStatus.running.value,
                ReviewRunStatus.awaiting_human_review.value,
                ReviewRunStatus.completed.value,
                ReviewRunStatus.rejected.value,
            }:
                return current_status

            if current_status != ReviewRunStatus.queued.value:
                raise ApplicationError(
                    "Review run cannot be started "
                    f"from status {current_status}",
                    type="InvalidReviewTransition",
                    non_retryable=True,
                )

            review_run.status = (
                ReviewRunStatus.running.value
            )

            if review_run.started_at is None:
                review_run.started_at = datetime.now(
                    timezone.utc
                )

            self._add_status_audit_event(
                database,
                review_run=review_run,
                previous_status=current_status,
                new_status=review_run.status,
            )

            database.commit()

            return review_run.status

    @activity.defn(
        name=VALIDATE_DOCUMENTS_ACTIVITY
    )
    def validate_case_review_documents(
        self,
        workflow_input: CaseReviewWorkflowInput,
    ) -> str:
        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                workflow_input.review_run_id,
            )

            try:
                supplied_case_id = UUID(
                    workflow_input.case_id
                )

                supplied_document_ids = {
                    UUID(document_id)
                    for document_id
                    in workflow_input.document_ids
                }
            except ValueError as error:
                raise ApplicationError(
                    "Workflow input contains invalid UUIDs",
                    type="InvalidWorkflowInput",
                    non_retryable=True,
                ) from error

            if supplied_case_id != review_run.case_id:
                raise ApplicationError(
                    "Workflow case does not match "
                    "the review run",
                    type="ReviewScopeMismatch",
                    non_retryable=True,
                )

            if supplied_document_ids != set(
                review_run.document_ids
            ):
                raise ApplicationError(
                    "Workflow documents do not match "
                    "the review run",
                    type="ReviewScopeMismatch",
                    non_retryable=True,
                )

            statement = select(
                ClinicalDocumentRecord.id
            ).where(
                ClinicalDocumentRecord.case_id
                == review_run.case_id,
                ClinicalDocumentRecord.id.in_(
                    review_run.document_ids
                ),
            )

            existing_document_ids = set(
                database.scalars(
                    statement
                ).all()
            )

            if existing_document_ids != set(
                review_run.document_ids
            ):
                raise ApplicationError(
                    "One or more review documents "
                    "are unavailable",
                    type="ReviewDocumentUnavailable",
                    non_retryable=True,
                )

            return "validated"

    @activity.defn(
        name=AWAIT_HUMAN_REVIEW_ACTIVITY
    )
    def mark_case_review_awaiting_human(
        self,
        activity_input: ReviewRunActivityInput,
    ) -> str:
        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            current_status = review_run.status

            if current_status in {
                ReviewRunStatus.awaiting_human_review.value,
                ReviewRunStatus.completed.value,
                ReviewRunStatus.rejected.value,
            }:
                return current_status

            if current_status != ReviewRunStatus.running.value:
                raise ApplicationError(
                    "Review run cannot await human "
                    f"review from status {current_status}",
                    type="InvalidReviewTransition",
                    non_retryable=True,
                )

            review_run.status = (
                ReviewRunStatus
                .awaiting_human_review
                .value
            )

            self._add_status_audit_event(
                database,
                review_run=review_run,
                previous_status=current_status,
                new_status=review_run.status,
            )

            database.commit()

            return review_run.status

    @activity.defn(name=FINALIZE_REVIEW_ACTIVITY)
    def finalize_case_review(
        self,
        activity_input: FinalizeReviewActivityInput,
    ) -> CaseReviewWorkflowResult:
        if activity_input.decision not in {
            "approve",
            "reject",
        }:
            raise ApplicationError(
                "Invalid human-review decision",
                type="InvalidHumanReviewDecision",
                non_retryable=True,
            )

        if (
            activity_input.decision == "reject"
            and not activity_input.notes
        ):
            raise ApplicationError(
                "Rejection notes are required",
                type="MissingRejectionNotes",
                non_retryable=True,
            )

        target_status = (
            ReviewRunStatus.completed.value
            if activity_input.decision == "approve"
            else ReviewRunStatus.rejected.value
        )

        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            if review_run.status == target_status:
                return CaseReviewWorkflowResult(
                    review_run_id=str(review_run.id),
                    status=review_run.status,
                )

            if (
                review_run.status
                != ReviewRunStatus
                .awaiting_human_review
                .value
            ):
                raise ApplicationError(
                    "Review run cannot be finalized "
                    f"from status {review_run.status}",
                    type="InvalidReviewTransition",
                    non_retryable=True,
                )

            previous_status = review_run.status
            review_run.status = target_status
            review_run.completed_at = datetime.now(
                timezone.utc
            )
            review_run.failure_code = None

            notes_hash = None

            if activity_input.notes:
                notes_hash = sha256(
                    activity_input.notes.encode(
                        "utf-8"
                    )
                ).hexdigest()

            database.add(
                AuditEventRecord(
                    case_id=review_run.case_id,
                    event_type=(
                        AuditEventType
                        .human_review_completed
                        .value
                    ),
                    actor_type=(
                        AuditActorType.reviewer.value
                    ),
                    details={
                        "review_run_id": str(
                            review_run.id
                        ),
                        "previous_status": (
                            previous_status
                        ),
                        "new_status": target_status,
                        "decision": (
                            activity_input.decision
                        ),
                        "notes_sha256": notes_hash,
                    },
                )
            )

            database.commit()

            return CaseReviewWorkflowResult(
                review_run_id=str(review_run.id),
                status=review_run.status,
            )

    @activity.defn(name=FAIL_REVIEW_ACTIVITY)
    def fail_case_review(
        self,
        activity_input: FailReviewActivityInput,
    ) -> str:
        if (
            not activity_input.failure_code
            or len(activity_input.failure_code) > 100
        ):
            raise ApplicationError(
                "Invalid workflow failure code",
                type="InvalidFailureCode",
                non_retryable=True,
            )

        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            if review_run.status in {
                ReviewRunStatus.completed.value,
                ReviewRunStatus.rejected.value,
                ReviewRunStatus.failed.value,
            }:
                return review_run.status

            previous_status = review_run.status
            review_run.status = (
                ReviewRunStatus.failed.value
            )
            review_run.failure_code = (
                activity_input.failure_code
            )
            review_run.completed_at = datetime.now(
                timezone.utc
            )

            database.add(
                AuditEventRecord(
                    case_id=review_run.case_id,
                    event_type=(
                        AuditEventType
                        .processing_failed
                        .value
                    ),
                    actor_type=(
                        AuditActorType.system.value
                    ),
                    details={
                        "review_run_id": str(
                            review_run.id
                        ),
                        "previous_status": (
                            previous_status
                        ),
                        "new_status": (
                            ReviewRunStatus.failed.value
                        ),
                        "failure_code": (
                            activity_input.failure_code
                        ),
                    },
                )
            )

            database.commit()

            return review_run.status