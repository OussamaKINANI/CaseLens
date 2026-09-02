import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from app.config import settings
from app.review_activities import CaseReviewActivities
from app.review_processing_activities import (
    ReviewProcessingActivities,
)
from app.review_workflow import CaseReviewWorkflow
from app.temporal_client import connect_temporal_client

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "%(name)s %(message)s"
    ),
)


def build_review_activities(
    activities: CaseReviewActivities,
    processing_activities: ReviewProcessingActivities,
) -> list[Callable]:
    """Return every activity scheduled by the review workflow."""
    return [
        activities.start_case_review,
        activities.validate_case_review_documents,
        processing_activities.index_case_review_document,
        processing_activities.extract_case_review_document,
        activities.mark_case_review_awaiting_human,
        activities.finalize_case_review,
        activities.fail_case_review,
    ]


async def run_worker() -> None:
    client = await connect_temporal_client()
    activities = CaseReviewActivities()
    processing_activities = (
        ReviewProcessingActivities()
    )

    with ThreadPoolExecutor(
        max_workers=8,
        thread_name_prefix=(
            "caselens-temporal-activity"
        ),
    ) as activity_executor:
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[
                CaseReviewWorkflow,
            ],
            activities=build_review_activities(
                activities,
                processing_activities,
            ),
            activity_executor=activity_executor,
        )

        print(
            "CaseLens Temporal worker started.\n"
            f"Namespace: {settings.temporal_namespace}\n"
            f"Task queue: {settings.temporal_task_queue}",
            flush=True,
        )

        await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
