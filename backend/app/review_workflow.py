from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from app.temporal_models import (
    CaseReviewWorkflowInput,
    CaseReviewWorkflowResult,
    FailReviewActivityInput,
    FinalizeReviewActivityInput,
    HumanReviewUpdate,
    ReviewRunActivityInput,
)


START_REVIEW_ACTIVITY = "start_case_review"
VALIDATE_DOCUMENTS_ACTIVITY = (
    "validate_case_review_documents"
)
AWAIT_HUMAN_REVIEW_ACTIVITY = (
    "mark_case_review_awaiting_human"
)
FINALIZE_REVIEW_ACTIVITY = "finalize_case_review"
FAIL_REVIEW_ACTIVITY = "fail_case_review"


ACTIVITY_TIMEOUT = timedelta(seconds=30)

ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)


@workflow.defn(name="case-review-workflow")
class CaseReviewWorkflow:
    def __init__(self) -> None:
        self._phase = "created"
        self._human_review: HumanReviewUpdate | None = None

    @workflow.run
    async def run(
        self,
        workflow_input: CaseReviewWorkflowInput,
    ) -> CaseReviewWorkflowResult:
        try:
            self._phase = "starting"

            await workflow.execute_activity(
                START_REVIEW_ACTIVITY,
                ReviewRunActivityInput(
                    review_run_id=(
                        workflow_input.review_run_id
                    ),
                ),
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            self._phase = "validating_documents"

            await workflow.execute_activity(
                VALIDATE_DOCUMENTS_ACTIVITY,
                workflow_input,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            self._phase = "awaiting_human_review"

            await workflow.execute_activity(
                AWAIT_HUMAN_REVIEW_ACTIVITY,
                ReviewRunActivityInput(
                    review_run_id=(
                        workflow_input.review_run_id
                    ),
                ),
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

            await workflow.wait_condition(
                lambda: self._human_review is not None
            )

            human_review = self._human_review

            if human_review is None:
                raise RuntimeError(
                    "Human-review decision was not recorded"
                )

            self._phase = "finalizing"

            result = await workflow.execute_activity(
                FINALIZE_REVIEW_ACTIVITY,
                FinalizeReviewActivityInput(
                    review_run_id=(
                        workflow_input.review_run_id
                    ),
                    decision=human_review.decision,
                    notes=human_review.notes,
                ),
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=ACTIVITY_RETRY_POLICY,
                result_type=CaseReviewWorkflowResult,
            )

            self._phase = result.status
            return result

        except Exception:
            self._phase = "failed"

            try:
                await workflow.execute_activity(
                    FAIL_REVIEW_ACTIVITY,
                    FailReviewActivityInput(
                        review_run_id=(
                            workflow_input.review_run_id
                        ),
                        failure_code=(
                            "review_workflow_failed"
                        ),
                    ),
                    start_to_close_timeout=(
                        ACTIVITY_TIMEOUT
                    ),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
            except Exception:
                pass

            raise

    @workflow.update(name="submit_human_review")
    def submit_human_review(
        self,
        review: HumanReviewUpdate,
    ) -> str:
        self._human_review = review
        return "accepted"

    @submit_human_review.validator
    def validate_human_review(
        self,
        review: HumanReviewUpdate,
    ) -> None:
        if review.decision not in {
            "approve",
            "reject",
        }:
            raise ValueError(
                "decision must be approve or reject"
            )

        if (
            review.decision == "reject"
            and not review.notes
        ):
            raise ValueError(
                "notes are required when rejecting"
            )

        if self._human_review is not None:
            raise ValueError(
                "A human-review decision already exists"
            )

    @workflow.query(name="current_phase")
    def current_phase(self) -> str:
        return self._phase