import asyncio
from typing import Protocol

from temporalio.exceptions import (
    WorkflowAlreadyStartedError,
)

from app.config import settings
from app.review_workflow import CaseReviewWorkflow
from app.temporal_client import connect_temporal_client
from app.temporal_models import (
    CaseReviewWorkflowInput,
    HumanReviewUpdate,
)


class ReviewWorkflowGatewayError(RuntimeError):
    pass


class ReviewWorkflowGateway(Protocol):
    def start_review(
        self,
        *,
        workflow_id: str,
        workflow_input: CaseReviewWorkflowInput,
    ) -> str:
        ...

    def submit_human_review(
        self,
        *,
        workflow_id: str,
        review: HumanReviewUpdate,
    ) -> str:
        ...


class TemporalReviewWorkflowGateway:
    def start_review(
        self,
        *,
        workflow_id: str,
        workflow_input: CaseReviewWorkflowInput,
    ) -> str:
        async def start() -> str:
            client = await connect_temporal_client()

            try:
                await client.start_workflow(
                    CaseReviewWorkflow.run,
                    workflow_input,
                    id=workflow_id,
                    task_queue=(
                        settings.temporal_task_queue
                    ),
                )
            except WorkflowAlreadyStartedError:
                return "already_started"

            return "started"

        try:
            return asyncio.run(start())
        except Exception as error:
            raise ReviewWorkflowGatewayError(
                "Unable to start Temporal workflow"
            ) from error

    def submit_human_review(
        self,
        *,
        workflow_id: str,
        review: HumanReviewUpdate,
    ) -> str:
        async def submit() -> str:
            client = await connect_temporal_client()

            handle = (
                client.get_workflow_handle_for(
                    CaseReviewWorkflow,
                    workflow_id,
                )
            )

            return await handle.execute_update(
                CaseReviewWorkflow.submit_human_review,
                review,
            )

        try:
            return asyncio.run(submit())
        except Exception as error:
            raise ReviewWorkflowGatewayError(
                "Unable to submit human review"
            ) from error


class FakeReviewWorkflowGateway:
    def __init__(self) -> None:
        self.started_workflows: list[
            tuple[str, CaseReviewWorkflowInput]
        ] = []

        self.human_reviews: list[
            tuple[str, HumanReviewUpdate]
        ] = []

    def start_review(
        self,
        *,
        workflow_id: str,
        workflow_input: CaseReviewWorkflowInput,
    ) -> str:
        self.started_workflows.append(
            (
                workflow_id,
                workflow_input,
            )
        )

        return "started"

    def submit_human_review(
        self,
        *,
        workflow_id: str,
        review: HumanReviewUpdate,
    ) -> str:
        self.human_reviews.append(
            (
                workflow_id,
                review,
            )
        )

        return "accepted"


def get_review_workflow_gateway(
) -> ReviewWorkflowGateway:
    return TemporalReviewWorkflowGateway()