from dataclasses import dataclass, field


@dataclass
class CaseReviewWorkflowInput:
    review_run_id: str
    case_id: str
    document_ids: list[str] = field(
        default_factory=list
    )


@dataclass
class ReviewRunActivityInput:
    review_run_id: str


@dataclass
class HumanReviewUpdate:
    decision: str
    notes: str | None = None


@dataclass
class FinalizeReviewActivityInput:
    review_run_id: str
    decision: str
    notes: str | None = None


@dataclass
class FailReviewActivityInput:
    review_run_id: str
    failure_code: str


@dataclass
class CaseReviewWorkflowResult:
    review_run_id: str
    status: str