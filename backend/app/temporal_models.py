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
class ReviewDocumentActivityInput:
    review_run_id: str
    document_id: str


@dataclass
class ReviewDocumentIndexResult:
    document_id: str
    chunk_count: int
    embedding_model: str
    reused_existing: bool


@dataclass
class ReviewDocumentExtractionResult:
    document_id: str
    extraction_id: str
    fact_count: int
    provider_name: str
    model_name: str
    reused_existing: bool


@dataclass
class HumanReviewUpdate:
    decision: str
    notes: str | None = None
    reviewer_id: str | None = None
    reviewer_label: str | None = None


@dataclass
class FinalizeReviewActivityInput:
    review_run_id: str
    decision: str
    notes: str | None = None
    reviewer_id: str | None = None
    reviewer_label: str | None = None


@dataclass
class FailReviewActivityInput:
    review_run_id: str
    failure_code: str


@dataclass
class CaseReviewWorkflowResult:
    review_run_id: str
    status: str
