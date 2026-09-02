"""Runs the case review workflow inside Temporal.

tests/test_review_workflow.py exercises the workflow's decision
rules as plain Python objects. These tests instead hand the
workflow to Temporal's time-skipping test server, so the parts
only Temporal can drive are covered too: Activity dispatch by
name, payload conversion, the human-review Update and its
validator, retry policies, the failure path, and replay
determinism.

The shared test server, worker and stand-in Activities live in
tests/temporal_support.py.
"""

import asyncio
import threading
from uuid import uuid4

import pytest
from app.config import settings
from app.review_activities import CaseReviewActivities
from app.review_limits import MAX_REVIEW_DOCUMENTS
from app.review_processing_activities import (
    ReviewProcessingActivities,
)
from app.review_workflow import (
    AWAIT_HUMAN_REVIEW_ACTIVITY,
    EXTRACT_DOCUMENT_ACTIVITY,
    FAIL_REVIEW_ACTIVITY,
    FINALIZE_REVIEW_ACTIVITY,
    INDEX_DOCUMENT_ACTIVITY,
    START_REVIEW_ACTIVITY,
    VALIDATE_DOCUMENTS_ACTIVITY,
    CaseReviewWorkflow,
)
from app.review_workflow_gateway import (
    TemporalReviewWorkflowGateway,
)
from app.temporal_models import (
    CaseReviewWorkflowInput,
    CaseReviewWorkflowResult,
    FailReviewActivityInput,
    FinalizeReviewActivityInput,
    HumanReviewUpdate,
)
from app.temporal_worker import build_review_activities
from temporalio.client import (
    WorkflowExecutionStatus,
    WorkflowHistory,
    WorkflowUpdateFailedError,
)
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    RetryState,
)
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from tests.temporal_support import (
    CASE_ID,
    DOCUMENT_IDS,
    FIRST_DOCUMENT_ID,
    REVIEW_RUN_ID,
    REVIEWER_ID,
    REVIEWER_LABEL,
    TASK_QUEUE,
    WORKFLOW_ACTIVITY_NAMES,
    RecordingReviewActivities,
    ReviewWorkflowHandle,
    activity_thread_pool,
    human_review_update,
    registered_activity_name,
    run_in_test_environment,
    run_review_expecting_failure,
    run_review_to_decision,
    run_workflow_scenario,
    start_review_workflow,
    wait_for_phase,
    wait_until,
)


def test_temporal_runs_the_full_review_lifecycle(
) -> None:
    activities = RecordingReviewActivities()

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> CaseReviewWorkflowResult:
        handle = await start_review_workflow(
            environment.client
        )

        await wait_for_phase(
            handle,
            "awaiting_human_review",
        )

        description = await handle.describe()

        # Nothing but a human decision can move the run on.
        assert description.status == (
            WorkflowExecutionStatus.RUNNING
        )

        update_result = await handle.execute_update(
            CaseReviewWorkflow.submit_human_review,
            human_review_update("approve"),
        )

        assert update_result == "accepted"

        result = await handle.result()

        assert await handle.query(
            CaseReviewWorkflow.current_phase
        ) == "completed"

        return result

    result = run_workflow_scenario(
        scenario,
        activities=activities,
    )

    assert result == CaseReviewWorkflowResult(
        review_run_id=REVIEW_RUN_ID,
        status="completed",
    )

    assert activities.call_names == [
        START_REVIEW_ACTIVITY,
        VALIDATE_DOCUMENTS_ACTIVITY,
        INDEX_DOCUMENT_ACTIVITY,
        INDEX_DOCUMENT_ACTIVITY,
        EXTRACT_DOCUMENT_ACTIVITY,
        EXTRACT_DOCUMENT_ACTIVITY,
        AWAIT_HUMAN_REVIEW_ACTIVITY,
        FINALIZE_REVIEW_ACTIVITY,
    ]

    assert activities.document_ids_for(
        INDEX_DOCUMENT_ACTIVITY
    ) == set(DOCUMENT_IDS)

    assert activities.document_ids_for(
        EXTRACT_DOCUMENT_ACTIVITY
    ) == set(DOCUMENT_IDS)

    finalize_input = activities.only_input_for(
        FINALIZE_REVIEW_ACTIVITY
    )

    # The reviewer identity has to survive the round trip
    # through Temporal's payload conversion.
    assert finalize_input == FinalizeReviewActivityInput(
        review_run_id=REVIEW_RUN_ID,
        decision="approve",
        notes=None,
        reviewer_id=REVIEWER_ID,
        reviewer_label=REVIEWER_LABEL,
    )


def test_temporal_finalizes_a_rejection_with_notes(
) -> None:
    activities = RecordingReviewActivities()

    result = run_review_to_decision(
        activities,
        review=human_review_update(
            "reject",
            "Imaging does not support the request.",
        ),
    )

    assert result.status == "rejected"

    finalize_input = activities.only_input_for(
        FINALIZE_REVIEW_ACTIVITY
    )

    assert finalize_input.decision == "reject"
    assert finalize_input.notes == (
        "Imaging does not support the request."
    )


@pytest.mark.parametrize(
    ("rejected_review", "expected_message"),
    [
        (
            human_review_update("override"),
            "decision must be approve or reject",
        ),
        (
            human_review_update("reject"),
            "notes are required when rejecting",
        ),
        (
            human_review_update(
                "approve",
                reviewer_id=None,
                reviewer_label=None,
            ),
            "reviewer identity is required",
        ),
    ],
    ids=[
        "invalid-decision",
        "rejection-without-notes",
        "missing-reviewer-identity",
    ],
)
def test_temporal_rejects_an_invalid_human_review(
    rejected_review: HumanReviewUpdate,
    expected_message: str,
) -> None:
    activities = RecordingReviewActivities()

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> CaseReviewWorkflowResult:
        handle = await start_review_workflow(
            environment.client
        )

        await wait_for_phase(
            handle,
            "awaiting_human_review",
        )

        with pytest.raises(
            WorkflowUpdateFailedError
        ) as rejected_update:
            await handle.execute_update(
                CaseReviewWorkflow.submit_human_review,
                rejected_review,
            )

        assert expected_message in str(
            rejected_update.value.cause
        )

        description = await handle.describe()

        # A rejected Update must leave the run untouched and
        # still open for a valid decision.
        assert description.status == (
            WorkflowExecutionStatus.RUNNING
        )

        assert FINALIZE_REVIEW_ACTIVITY not in (
            activities.call_names
        )

        await handle.execute_update(
            CaseReviewWorkflow.submit_human_review,
            human_review_update("approve"),
        )

        return await handle.result()

    result = run_workflow_scenario(
        scenario,
        activities=activities,
    )

    assert result.status == "completed"


def test_temporal_rejects_a_second_human_review(
) -> None:
    finalize_gate = threading.Event()

    activities = RecordingReviewActivities(
        finalize_gate=finalize_gate,
    )

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> CaseReviewWorkflowResult:
        handle = await start_review_workflow(
            environment.client
        )

        await wait_for_phase(
            handle,
            "awaiting_human_review",
        )

        # Holding the run inside the finalize Activity is what
        # makes the duplicate arrive while the first decision is
        # still in flight. Time skipping stays off so the held
        # Activity cannot hit its start-to-close timeout.
        with environment.auto_time_skipping_disabled():
            await handle.execute_update(
                CaseReviewWorkflow.submit_human_review,
                human_review_update("approve"),
            )

            await wait_for_phase(handle, "finalizing")

            with pytest.raises(
                WorkflowUpdateFailedError
            ) as duplicate_update:
                await handle.execute_update(
                    (
                        CaseReviewWorkflow
                        .submit_human_review
                    ),
                    human_review_update("reject", "No."),
                )

            assert "decision already exists" in (
                str(duplicate_update.value.cause)
            )

            finalize_gate.set()

            return await handle.result()

    result = run_workflow_scenario(
        scenario,
        activities=activities,
    )

    assert result.status == "completed"

    # The duplicate never reached the Activity, so the run was
    # finalized exactly once, as an approval.
    finalize_input = activities.only_input_for(
        FINALIZE_REVIEW_ACTIVITY
    )

    assert finalize_input.decision == "approve"


def test_temporal_retries_a_transient_extraction_failure(
) -> None:
    activities = RecordingReviewActivities(
        failures={
            EXTRACT_DOCUMENT_ACTIVITY: [
                ApplicationError(
                    "Extraction provider is unavailable",
                    type="ExtractionProviderUnavailable",
                ),
            ],
        },
    )

    result = run_review_to_decision(
        activities,
        document_ids=[FIRST_DOCUMENT_ID],
    )

    assert result.status == "completed"

    # The AI retry policy allows one further attempt, and the
    # workflow carries on from it.
    assert activities.call_count(
        EXTRACT_DOCUMENT_ACTIVITY
    ) == 2


def test_temporal_retries_a_failing_control_activity(
) -> None:
    activities = RecordingReviewActivities(
        failures={
            START_REVIEW_ACTIVITY: [
                ApplicationError(
                    "Review run row is locked",
                    type="ReviewRunLocked",
                ),
                ApplicationError(
                    "Review run row is locked",
                    type="ReviewRunLocked",
                ),
            ],
        },
    )

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> CaseReviewWorkflowResult:
        handle = await start_review_workflow(
            environment.client,
            document_ids=[FIRST_DOCUMENT_ID],
        )

        # The Update handler is live from the start, so the
        # decision can be recorded while the run is still
        # retrying its first Activity.
        await handle.execute_update(
            CaseReviewWorkflow.submit_human_review,
            human_review_update("approve"),
        )

        return await handle.result()

    result = run_workflow_scenario(
        scenario,
        activities=activities,
    )

    assert result.status == "completed"

    # Two failures, then the third attempt succeeds, well inside
    # the control retry policy's five attempts.
    assert activities.call_count(
        START_REVIEW_ACTIVITY
    ) == 3


def test_temporal_fails_a_control_activity_that_never_recovers(
) -> None:
    activities = RecordingReviewActivities(
        failures={
            AWAIT_HUMAN_REVIEW_ACTIVITY: [
                ApplicationError(
                    "Review run row is locked",
                    type="ReviewRunLocked",
                )
                for _ in range(5)
            ],
        },
    )

    workflow_failure = run_review_expecting_failure(
        activities,
        document_ids=[FIRST_DOCUMENT_ID],
    )

    activity_failure = workflow_failure.cause

    assert isinstance(activity_failure, ActivityError)
    assert activity_failure.activity_type == (
        AWAIT_HUMAN_REVIEW_ACTIVITY
    )

    # The control retry policy gave up rather than retrying
    # forever, and never went past its five attempts.
    assert activity_failure.retry_state == (
        RetryState.MAXIMUM_ATTEMPTS_REACHED
    )

    attempts = activities.call_count(
        AWAIT_HUMAN_REVIEW_ACTIVITY
    )

    assert 2 <= attempts <= 5

    # The run is then marked failed rather than left waiting on
    # a reviewer who will never be asked.
    assert activities.call_count(
        FAIL_REVIEW_ACTIVITY
    ) == 1


def test_temporal_marks_the_run_failed_on_activity_error(
) -> None:
    activities = RecordingReviewActivities(
        failures={
            EXTRACT_DOCUMENT_ACTIVITY: [
                ApplicationError(
                    "Document could not be extracted",
                    type="ExtractionRejected",
                    non_retryable=True,
                ),
            ],
        },
    )

    workflow_failure = run_review_expecting_failure(
        activities,
        document_ids=[FIRST_DOCUMENT_ID],
    )

    activity_failure = workflow_failure.cause

    assert isinstance(activity_failure, ActivityError)
    assert activity_failure.activity_type == (
        EXTRACT_DOCUMENT_ACTIVITY
    )

    extraction_failure = activity_failure.cause

    assert isinstance(
        extraction_failure,
        ApplicationError,
    )

    assert extraction_failure.type == (
        "ExtractionRejected"
    )

    # The compensating Activity has to run before the workflow
    # is allowed to fail, otherwise the run is stranded.
    fail_input = activities.only_input_for(
        FAIL_REVIEW_ACTIVITY
    )

    assert fail_input == FailReviewActivityInput(
        review_run_id=REVIEW_RUN_ID,
        failure_code="review_workflow_failed",
    )

    assert FINALIZE_REVIEW_ACTIVITY not in (
        activities.call_names
    )


def test_temporal_reports_the_original_error_when_fail_fails(
) -> None:
    activities = RecordingReviewActivities(
        failures={
            EXTRACT_DOCUMENT_ACTIVITY: [
                ApplicationError(
                    "Document could not be extracted",
                    type="ExtractionRejected",
                    non_retryable=True,
                ),
            ],
            FAIL_REVIEW_ACTIVITY: [
                ApplicationError(
                    "Review run could not be marked failed",
                    type="ReviewRunLocked",
                    non_retryable=True,
                ),
            ],
        },
    )

    workflow_failure = run_review_expecting_failure(
        activities,
        document_ids=[FIRST_DOCUMENT_ID],
    )

    activity_failure = workflow_failure.cause

    assert isinstance(activity_failure, ActivityError)

    # A failing compensation must not mask what actually broke
    # the run, otherwise the cause is lost to operators.
    assert activity_failure.activity_type == (
        EXTRACT_DOCUMENT_ACTIVITY
    )

    assert activities.call_count(
        FAIL_REVIEW_ACTIVITY
    ) == 1


def test_temporal_handles_the_largest_allowed_review(
) -> None:
    activities = RecordingReviewActivities()

    document_ids = [
        str(uuid4())
        for _ in range(MAX_REVIEW_DOCUMENTS)
    ]

    result = run_review_to_decision(
        activities,
        document_ids=document_ids,
    )

    assert result.status == "completed"

    # Every document in the largest review the API accepts has
    # to be indexed and extracted exactly once.
    assert activities.document_ids_for(
        INDEX_DOCUMENT_ACTIVITY
    ) == set(document_ids)

    assert activities.document_ids_for(
        EXTRACT_DOCUMENT_ACTIVITY
    ) == set(document_ids)

    assert activities.call_count(
        INDEX_DOCUMENT_ACTIVITY
    ) == MAX_REVIEW_DOCUMENTS

    assert activities.call_count(
        EXTRACT_DOCUMENT_ACTIVITY
    ) == MAX_REVIEW_DOCUMENTS


def test_completed_workflow_history_replays(
) -> None:
    activities = RecordingReviewActivities()

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> WorkflowHistory:
        handle = await start_review_workflow(
            environment.client
        )

        await wait_for_phase(
            handle,
            "awaiting_human_review",
        )

        await handle.execute_update(
            CaseReviewWorkflow.submit_human_review,
            human_review_update("approve"),
        )

        await handle.result()

        return await handle.fetch_history()

    history = run_workflow_scenario(
        scenario,
        activities=activities,
    )

    # Replaying recorded history against the current workflow
    # code is what a worker does after a restart: it fails if
    # the workflow ever becomes non-deterministic.
    replayer = Replayer(
        workflows=[CaseReviewWorkflow]
    )

    asyncio.run(
        replayer.replay_workflow(history)
    )


def test_gateway_drives_the_workflow_through_temporal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activities = RecordingReviewActivities()
    gateway = TemporalReviewWorkflowGateway()
    workflow_id = f"case-review-{uuid4()}"

    workflow_input = CaseReviewWorkflowInput(
        review_run_id=REVIEW_RUN_ID,
        case_id=CASE_ID,
        document_ids=DOCUMENT_IDS,
    )

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> CaseReviewWorkflowResult:
        service_config = (
            environment.client.service_client.config
        )

        monkeypatch.setattr(
            settings,
            "temporal_address",
            service_config.target_host,
        )

        monkeypatch.setattr(
            settings,
            "temporal_namespace",
            environment.client.namespace,
        )

        # The gateway is synchronous and opens its own event
        # loop, so it has to run off this one.
        start_result = await asyncio.to_thread(
            gateway.start_review,
            workflow_id=workflow_id,
            workflow_input=workflow_input,
        )

        assert start_result == "started"

        restart_result = await asyncio.to_thread(
            gateway.start_review,
            workflow_id=workflow_id,
            workflow_input=workflow_input,
        )

        # Retrying the start command must not fork a second run.
        assert restart_result == "already_started"

        handle: ReviewWorkflowHandle = (
            environment.client.get_workflow_handle_for(
                CaseReviewWorkflow,
                workflow_id,
            )
        )

        await wait_for_phase(
            handle,
            "awaiting_human_review",
        )

        update_result = await asyncio.to_thread(
            gateway.submit_human_review,
            workflow_id=workflow_id,
            review=human_review_update("approve"),
        )

        assert update_result == "accepted"

        return await handle.result()

    result = run_workflow_scenario(
        scenario,
        activities=activities,
    )

    assert result.status == "completed"

    assert activities.call_count(
        START_REVIEW_ACTIVITY
    ) == 1


def test_worker_registers_every_workflow_activity(
) -> None:
    registered_names = {
        registered_activity_name(activity_callable)
        for activity_callable
        in build_review_activities(
            CaseReviewActivities(),
            ReviewProcessingActivities(),
        )
    }

    # An Activity the workflow schedules but the worker never
    # registers would retry until it timed out in production.
    assert WORKFLOW_ACTIVITY_NAMES <= registered_names


def test_worker_starts_with_the_production_activities(
) -> None:
    def unusable_session_factory():
        raise AssertionError(
            "Worker startup must not open a database session"
        )

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> None:
        with activity_thread_pool() as activity_executor:
            worker = Worker(
                environment.client,
                task_queue=TASK_QUEUE,
                workflows=[CaseReviewWorkflow],
                activities=build_review_activities(
                    CaseReviewActivities(
                        session_factory=(
                            unusable_session_factory
                        ),
                    ),
                    ReviewProcessingActivities(
                        session_factory=(
                            unusable_session_factory
                        ),
                    ),
                ),
                activity_executor=activity_executor,
            )

            # Temporal validates the registered workflow and
            # Activities as the worker starts polling, which it
            # does on its own task.
            async with worker:
                await wait_until(
                    lambda: worker.is_running,
                    "for the worker to start polling",
                )

        assert worker.is_shutdown

    run_in_test_environment(scenario)
