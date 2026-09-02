"""Shared machinery for running workflows inside Temporal.

Tests that need the workflow executed by Temporal rather than
called as plain Python build on the helpers here: a test server
and worker (run_workflow_scenario), stand-in Activities that
record what Temporal dispatched (RecordingReviewActivities), and
the small client helpers used to start a run and watch it.

The suite does not use pytest-asyncio, so every entry point here
is synchronous and owns its event loop.
"""

import asyncio
import os
import threading
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from app.config import settings
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
from app.temporal_models import (
    CaseReviewWorkflowInput,
    CaseReviewWorkflowResult,
    FailReviewActivityInput,
    FinalizeReviewActivityInput,
    HumanReviewUpdate,
    ReviewDocumentActivityInput,
    ReviewDocumentExtractionResult,
    ReviewDocumentIndexResult,
    ReviewRunActivityInput,
)
from temporalio import activity
from temporalio.client import (
    Client,
    WorkflowFailureError,
    WorkflowHandle,
)
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

REVIEWER_ID = "11111111-1111-4111-8111-111111111111"
REVIEWER_LABEL = "Test Reviewer"

REVIEW_RUN_ID = "33333333-3333-4333-8333-333333333333"
CASE_ID = "44444444-4444-4444-8444-444444444444"

FIRST_DOCUMENT_ID = (
    "55555555-5555-4555-8555-555555555555"
)

SECOND_DOCUMENT_ID = (
    "66666666-6666-4666-8666-666666666666"
)

DOCUMENT_IDS = [
    FIRST_DOCUMENT_ID,
    SECOND_DOCUMENT_ID,
]

# The gateway starts workflows on the configured queue, so test
# workers listen on the same one.
TASK_QUEUE = settings.temporal_task_queue

# Pinned rather than left at "default", so a run downloads a
# known test server instead of whatever the download service
# resolves to that day. Bumping this invalidates the CI cache.
TEST_SERVER_VERSION = "v1.38.0"

WORKFLOW_ACTIVITY_NAMES = {
    START_REVIEW_ACTIVITY,
    VALIDATE_DOCUMENTS_ACTIVITY,
    INDEX_DOCUMENT_ACTIVITY,
    EXTRACT_DOCUMENT_ACTIVITY,
    AWAIT_HUMAN_REVIEW_ACTIVITY,
    FINALIZE_REVIEW_ACTIVITY,
    FAIL_REVIEW_ACTIVITY,
}

ScenarioResult = TypeVar("ScenarioResult")

ReviewWorkflowHandle = WorkflowHandle[
    CaseReviewWorkflow,
    CaseReviewWorkflowResult,
]

Scenario = Callable[
    [WorkflowEnvironment],
    Awaitable[ScenarioResult],
]


class RecordingReviewActivities:
    """Stand-ins for the real database-backed Activities.

    They are registered under the same Activity names the
    workflow schedules, so Temporal still resolves and dispatches
    every Activity exactly as it does in production.

    `failures` queues exceptions per Activity name: each call
    consumes the next one, so a queue of two failures makes the
    first two attempts fail and lets the third succeed.
    `finalize_gate` holds a run inside finalization until the
    test releases it.
    """

    def __init__(
        self,
        *,
        failures: dict[str, list[Exception]] | None = None,
        finalize_gate: threading.Event | None = None,
    ) -> None:
        # Indexing and extraction fan out across worker threads.
        self._lock = threading.Lock()
        self._calls: list[tuple[str, object]] = []

        self._failures = {
            activity_name: list(pending_failures)
            for activity_name, pending_failures
            in (failures or {}).items()
        }

        self._finalize_gate = finalize_gate

    def registered(self) -> list[Callable]:
        return [
            self.start_case_review,
            self.validate_case_review_documents,
            self.index_case_review_document,
            self.extract_case_review_document,
            self.mark_case_review_awaiting_human,
            self.finalize_case_review,
            self.fail_case_review,
        ]

    @property
    def call_names(self) -> list[str]:
        with self._lock:
            return [
                activity_name
                for activity_name, _ in self._calls
            ]

    def call_count(self, activity_name: str) -> int:
        return self.call_names.count(activity_name)

    def inputs_for(
        self,
        activity_name: str,
    ) -> list[object]:
        with self._lock:
            return [
                activity_input
                for recorded_name, activity_input
                in self._calls
                if recorded_name == activity_name
            ]

    def only_input_for(
        self,
        activity_name: str,
    ) -> object:
        activity_inputs = self.inputs_for(activity_name)

        assert len(activity_inputs) == 1, (
            f"{activity_name} ran "
            f"{len(activity_inputs)} times"
        )

        return activity_inputs[0]

    def document_ids_for(
        self,
        activity_name: str,
    ) -> set[str]:
        return {
            activity_input.document_id
            for activity_input
            in self.inputs_for(activity_name)
        }

    def _record(
        self,
        activity_name: str,
        activity_input: object,
    ) -> None:
        with self._lock:
            self._calls.append(
                (activity_name, activity_input)
            )

            pending_failures = self._failures.get(
                activity_name
            )

            failure = (
                pending_failures.pop(0)
                if pending_failures
                else None
            )

        if failure is not None:
            raise failure

    @activity.defn(name=START_REVIEW_ACTIVITY)
    def start_case_review(
        self,
        activity_input: ReviewRunActivityInput,
    ) -> str:
        self._record(
            START_REVIEW_ACTIVITY,
            activity_input,
        )

        return "running"

    @activity.defn(name=VALIDATE_DOCUMENTS_ACTIVITY)
    def validate_case_review_documents(
        self,
        activity_input: CaseReviewWorkflowInput,
    ) -> str:
        self._record(
            VALIDATE_DOCUMENTS_ACTIVITY,
            activity_input,
        )

        return "validated"

    @activity.defn(name=INDEX_DOCUMENT_ACTIVITY)
    def index_case_review_document(
        self,
        activity_input: ReviewDocumentActivityInput,
    ) -> ReviewDocumentIndexResult:
        self._record(
            INDEX_DOCUMENT_ACTIVITY,
            activity_input,
        )

        return ReviewDocumentIndexResult(
            document_id=activity_input.document_id,
            chunk_count=3,
            embedding_model="fake-embedding-model",
            reused_existing=False,
        )

    @activity.defn(name=EXTRACT_DOCUMENT_ACTIVITY)
    def extract_case_review_document(
        self,
        activity_input: ReviewDocumentActivityInput,
    ) -> ReviewDocumentExtractionResult:
        self._record(
            EXTRACT_DOCUMENT_ACTIVITY,
            activity_input,
        )

        return ReviewDocumentExtractionResult(
            document_id=activity_input.document_id,
            extraction_id=str(uuid4()),
            fact_count=2,
            provider_name="fake",
            model_name="fake-extraction-model",
            reused_existing=False,
        )

    @activity.defn(name=AWAIT_HUMAN_REVIEW_ACTIVITY)
    def mark_case_review_awaiting_human(
        self,
        activity_input: ReviewRunActivityInput,
    ) -> str:
        self._record(
            AWAIT_HUMAN_REVIEW_ACTIVITY,
            activity_input,
        )

        return "awaiting_human_review"

    @activity.defn(name=FINALIZE_REVIEW_ACTIVITY)
    def finalize_case_review(
        self,
        activity_input: FinalizeReviewActivityInput,
    ) -> CaseReviewWorkflowResult:
        self._record(
            FINALIZE_REVIEW_ACTIVITY,
            activity_input,
        )

        if self._finalize_gate is not None:
            assert self._finalize_gate.wait(
                timeout=10.0
            ), "Finalize gate was never released"

        return CaseReviewWorkflowResult(
            review_run_id=activity_input.review_run_id,
            status=(
                "completed"
                if activity_input.decision == "approve"
                else "rejected"
            ),
        )

    @activity.defn(name=FAIL_REVIEW_ACTIVITY)
    def fail_case_review(
        self,
        activity_input: FailReviewActivityInput,
    ) -> str:
        self._record(
            FAIL_REVIEW_ACTIVITY,
            activity_input,
        )

        return "failed"


def human_review_update(
    decision: str,
    notes: str | None = None,
    *,
    reviewer_id: str | None = REVIEWER_ID,
    reviewer_label: str | None = REVIEWER_LABEL,
) -> HumanReviewUpdate:
    return HumanReviewUpdate(
        decision=decision,
        notes=notes,
        reviewer_id=reviewer_id,
        reviewer_label=reviewer_label,
    )


def test_server_cache_dir() -> str | None:
    """Directory the test server binary is kept in, if set.

    Returning None leaves the SDK's own temporary directory in
    place, which is the sensible default for a workstation. CI
    sets TEMPORAL_TEST_SERVER_DIR to a cached path so the binary
    is downloaded once rather than once per run.
    """
    configured_dir = os.environ.get(
        "TEMPORAL_TEST_SERVER_DIR"
    )

    if not configured_dir:
        return None

    cache_dir = Path(configured_dir).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    return str(cache_dir)


def run_in_test_environment(
    scenario: Scenario,
) -> ScenarioResult:
    """Run `scenario` against a Temporal test server.

    The time-skipping server is ephemeral and local, so no
    external Temporal service is needed.
    """

    async def run() -> ScenarioResult:
        environment = await (
            WorkflowEnvironment.start_time_skipping(
                test_server_download_version=(
                    TEST_SERVER_VERSION
                ),
                download_dest_dir=test_server_cache_dir(),
            )
        )

        async with environment:
            return await scenario(environment)

    return asyncio.run(run())


def activity_thread_pool() -> ThreadPoolExecutor:
    """Executor for Activities, as app.temporal_worker uses.

    The real Activities are synchronous database calls, so
    Temporal has to run them off the workflow's event loop.
    """
    return ThreadPoolExecutor(
        max_workers=8,
        thread_name_prefix="caselens-test-activity",
    )


def run_workflow_scenario(
    scenario: Scenario,
    *,
    activities: RecordingReviewActivities,
) -> ScenarioResult:
    """Run `scenario` with a worker serving the review workflow."""

    async def with_worker(
        environment: WorkflowEnvironment,
    ) -> ScenarioResult:
        with activity_thread_pool() as activity_executor:
            async with Worker(
                environment.client,
                task_queue=TASK_QUEUE,
                workflows=[CaseReviewWorkflow],
                activities=activities.registered(),
                activity_executor=activity_executor,
            ):
                return await scenario(environment)

    return run_in_test_environment(with_worker)


async def start_review_workflow(
    client: Client,
    *,
    document_ids: list[str] | None = None,
) -> ReviewWorkflowHandle:
    return await client.start_workflow(
        CaseReviewWorkflow.run,
        CaseReviewWorkflowInput(
            review_run_id=REVIEW_RUN_ID,
            case_id=CASE_ID,
            document_ids=(
                DOCUMENT_IDS
                if document_ids is None
                else document_ids
            ),
        ),
        id=f"case-review-{uuid4()}",
        task_queue=TASK_QUEUE,
    )


async def wait_until(
    condition: Callable[[], bool],
    description: str,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if condition():
            return

        await asyncio.sleep(0.05)

    raise AssertionError(f"Timed out waiting {description}")


async def wait_for_phase(
    handle: ReviewWorkflowHandle,
    expected_phase: str,
    *,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    phase = None

    while time.monotonic() < deadline:
        phase = await handle.query(
            CaseReviewWorkflow.current_phase
        )

        if phase == expected_phase:
            return

        await asyncio.sleep(0.05)

    raise AssertionError(
        f"Workflow never reached phase "
        f"{expected_phase!r}, last phase was {phase!r}"
    )


def run_review_to_decision(
    activities: RecordingReviewActivities,
    *,
    review: HumanReviewUpdate | None = None,
    document_ids: list[str] | None = None,
) -> CaseReviewWorkflowResult:
    """Run a review through to its finalized result.

    Covers the common shape: start the run, wait at the human
    checkpoint, submit a decision, return what the workflow
    finished with. The decision defaults to an approval.
    """

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> CaseReviewWorkflowResult:
        handle = await start_review_workflow(
            environment.client,
            document_ids=document_ids,
        )

        await wait_for_phase(
            handle,
            "awaiting_human_review",
        )

        await handle.execute_update(
            CaseReviewWorkflow.submit_human_review,
            (
                human_review_update("approve")
                if review is None
                else review
            ),
        )

        return await handle.result()

    return run_workflow_scenario(
        scenario,
        activities=activities,
    )


def run_review_expecting_failure(
    activities: RecordingReviewActivities,
    *,
    document_ids: list[str] | None = None,
) -> WorkflowFailureError:
    """Run a review that is expected to fail, and return why."""

    async def scenario(
        environment: WorkflowEnvironment,
    ) -> WorkflowFailureError:
        handle = await start_review_workflow(
            environment.client,
            document_ids=document_ids,
        )

        try:
            result = await handle.result()
        except WorkflowFailureError as workflow_failure:
            return workflow_failure

        raise AssertionError(
            f"Workflow completed with {result} "
            f"instead of failing"
        )

    return run_workflow_scenario(
        scenario,
        activities=activities,
    )


def registered_activity_name(
    activity_callable: Callable,
) -> str:
    # @activity.defn records the registered name on the callable
    # itself; this is how the worker resolves it.
    definition = activity._Definition.from_callable(
        activity_callable
    )

    assert definition is not None, (
        f"{activity_callable!r} is not an Activity"
    )

    return definition.name
