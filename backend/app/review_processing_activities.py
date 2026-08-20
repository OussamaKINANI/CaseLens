from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventType,
)
from app.database import SessionLocal
from app.document_indexing_service import (
    DocumentIndexingError,
    index_document,
)
from app.document_models import ClinicalDocumentRecord
from app.embedding_factory import (
    create_embedding_provider,
)
from app.embedding_service import (
    EmbeddingProvider,
    EmbeddingProviderError,
)
from app.extraction_models import (
    ClinicalExtractionRecord,
)
from app.extraction_provider_factory import (
    get_extraction_provider,
)
from app.extraction_service import (
    EvidenceVerificationError,
    ExtractionProvider,
    ExtractionProviderError,
    verify_extraction_evidence,
)
from app.models import CaseRecord  # noqa: F401
from app.review_models import CaseReviewRunRecord
from app.review_workflow import (
    EXTRACT_DOCUMENT_ACTIVITY,
    INDEX_DOCUMENT_ACTIVITY,
)
from app.temporal_models import (
    ReviewDocumentActivityInput,
    ReviewDocumentExtractionResult,
    ReviewDocumentIndexResult,
)


SessionFactory = Callable[[], Session]

EmbeddingProviderFactory = Callable[
    [],
    EmbeddingProvider,
]

ExtractionProviderFactory = Callable[
    [],
    ExtractionProvider,
]


class ReviewProcessingActivities:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        embedding_provider_factory: (
            EmbeddingProviderFactory
        ) = create_embedding_provider,
        extraction_provider_factory: (
            ExtractionProviderFactory
        ) = get_extraction_provider,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_provider_factory = (
            embedding_provider_factory
        )
        self.extraction_provider_factory = (
            extraction_provider_factory
        )

    def _parse_uuid(
        self,
        value: str,
        *,
        field_name: str,
    ) -> UUID:
        try:
            return UUID(value)
        except ValueError as error:
            raise ApplicationError(
                f"Invalid {field_name}",
                type="InvalidWorkflowInput",
                non_retryable=True,
            ) from error

    def _get_review_run(
        self,
        database: Session,
        review_run_id: str,
    ) -> CaseReviewRunRecord:
        parsed_id = self._parse_uuid(
            review_run_id,
            field_name="review-run identifier",
        )

        review_run = database.get(
            CaseReviewRunRecord,
            parsed_id,
        )

        if review_run is None:
            raise ApplicationError(
                "Review run was not found",
                type="ReviewRunNotFound",
                non_retryable=True,
            )

        return review_run

    def _get_scoped_document(
        self,
        database: Session,
        *,
        review_run: CaseReviewRunRecord,
        document_id: str,
    ) -> ClinicalDocumentRecord:
        parsed_document_id = self._parse_uuid(
            document_id,
            field_name="document identifier",
        )

        if (
            parsed_document_id
            not in review_run.document_ids
        ):
            raise ApplicationError(
                "Document is outside the review run",
                type="ReviewScopeMismatch",
                non_retryable=True,
            )

        statement = select(
            ClinicalDocumentRecord
        ).where(
            ClinicalDocumentRecord.id
            == parsed_document_id,
            ClinicalDocumentRecord.case_id
            == review_run.case_id,
        )

        document = database.scalar(statement)

        if document is None:
            raise ApplicationError(
                "Review document was not found",
                type="ReviewDocumentUnavailable",
                non_retryable=True,
            )

        return document

    def _find_existing_extraction(
        self,
        database: Session,
        *,
        document_id: UUID,
        provider: ExtractionProvider,
    ) -> ClinicalExtractionRecord | None:
        statement = select(
            ClinicalExtractionRecord
        ).where(
            ClinicalExtractionRecord.document_id
            == document_id,
            ClinicalExtractionRecord.provider_name
            == provider.provider_name,
            ClinicalExtractionRecord.model_name
            == provider.model_name,
            ClinicalExtractionRecord.schema_version
            == "1.0",
        )

        return database.scalar(statement)

    def _build_extraction_result(
        self,
        extraction: ClinicalExtractionRecord,
        *,
        reused_existing: bool,
    ) -> ReviewDocumentExtractionResult:
        facts = extraction.result.get(
            "facts",
            [],
        )

        return ReviewDocumentExtractionResult(
            document_id=str(
                extraction.document_id
            ),
            extraction_id=str(extraction.id),
            fact_count=len(facts),
            provider_name=(
                extraction.provider_name
            ),
            model_name=extraction.model_name,
            reused_existing=reused_existing,
        )

    @activity.defn(name=INDEX_DOCUMENT_ACTIVITY)
    def index_case_review_document(
        self,
        activity_input: ReviewDocumentActivityInput,
    ) -> ReviewDocumentIndexResult:
        try:
            provider = (
                self.embedding_provider_factory()
            )
        except EmbeddingProviderError as error:
            raise ApplicationError(
                "Unable to configure embedding provider",
                type="EmbeddingProviderUnavailable",
            ) from error

        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            document = self._get_scoped_document(
                database,
                review_run=review_run,
                document_id=activity_input.document_id,
            )

            try:
                result = index_document(
                    database,
                    document=document,
                    provider=provider,
                )
            except DocumentIndexingError as error:
                raise ApplicationError(
                    str(error),
                    type="DocumentIndexingFailed",
                    non_retryable=True,
                ) from error
            except EmbeddingProviderError as error:
                raise ApplicationError(
                    "Embedding provider failed",
                    type="EmbeddingProviderFailed",
                ) from error

            if not result.reused_existing:
                database.add(
                    AuditEventRecord(
                        case_id=review_run.case_id,
                        event_type=(
                            AuditEventType
                            .document_indexed
                            .value
                        ),
                        actor_type=(
                            AuditActorType
                            .system
                            .value
                        ),
                        details={
                            "review_run_id": str(
                                review_run.id
                            ),
                            "document_id": str(
                                document.id
                            ),
                            "chunk_count": len(
                                result.chunks
                            ),
                            "embedding_model": (
                                result.embedding_model
                            ),
                            "document_sha256": (
                                document.content_sha256
                            ),
                        },
                    )
                )

            database.commit()

            return ReviewDocumentIndexResult(
                document_id=str(document.id),
                chunk_count=len(result.chunks),
                embedding_model=(
                    result.embedding_model
                ),
                reused_existing=(
                    result.reused_existing
                ),
            )

    @activity.defn(name=EXTRACT_DOCUMENT_ACTIVITY)
    def extract_case_review_document(
        self,
        activity_input: ReviewDocumentActivityInput,
    ) -> ReviewDocumentExtractionResult:
        try:
            provider = (
                self.extraction_provider_factory()
            )
        except Exception as error:
            raise ApplicationError(
                "Unable to configure extraction provider",
                type="ExtractionProviderUnavailable",
            ) from error

        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            document = self._get_scoped_document(
                database,
                review_run=review_run,
                document_id=activity_input.document_id,
            )

            existing_extraction = (
                self._find_existing_extraction(
                    database,
                    document_id=document.id,
                    provider=provider,
                )
            )

            if existing_extraction is not None:
                return self._build_extraction_result(
                    existing_extraction,
                    reused_existing=True,
                )

            case_id = review_run.case_id
            document_id = document.id
            document_content = document.content
            source_sha256 = (
                document.content_sha256
            )

        try:
            extraction = provider.extract(
                document_id=document_id,
                content=document_content,
            )

            verify_extraction_evidence(
                extraction=extraction,
                documents={
                    document_id: document_content,
                },
            )
        except ExtractionProviderError as error:
            raise ApplicationError(
                "Extraction provider failed",
                type="ExtractionProviderFailed",
            ) from error
        except EvidenceVerificationError as error:
            raise ApplicationError(
                "Extraction evidence could not "
                "be verified",
                type="UnverifiableExtraction",
            ) from error

        with self.session_factory() as database:
            review_run = self._get_review_run(
                database,
                activity_input.review_run_id,
            )

            document = self._get_scoped_document(
                database,
                review_run=review_run,
                document_id=activity_input.document_id,
            )

            if (
                document.content_sha256
                != source_sha256
            ):
                raise ApplicationError(
                    "Document changed during extraction",
                    type="DocumentChanged",
                    non_retryable=True,
                )

            existing_extraction = (
                self._find_existing_extraction(
                    database,
                    document_id=document.id,
                    provider=provider,
                )
            )

            if existing_extraction is not None:
                return self._build_extraction_result(
                    existing_extraction,
                    reused_existing=True,
                )

            extraction_record = (
                ClinicalExtractionRecord(
                    case_id=case_id,
                    document_id=document.id,
                    provider_name=(
                        provider.provider_name
                    ),
                    model_name=provider.model_name,
                    schema_version=(
                        extraction.schema_version
                    ),
                    source_sha256=source_sha256,
                    result=extraction.model_dump(
                        mode="json"
                    ),
                )
            )

            started_event = AuditEventRecord(
                case_id=case_id,
                event_type=(
                    AuditEventType
                    .ai_review_started
                    .value
                ),
                actor_type=(
                    AuditActorType.system.value
                ),
                details={
                    "review_run_id": str(
                        review_run.id
                    ),
                    "document_id": str(
                        document.id
                    ),
                    "provider_name": (
                        provider.provider_name
                    ),
                    "model_name": (
                        provider.model_name
                    ),
                },
            )

            database.add(extraction_record)
            database.add(started_event)
            database.flush()

            completed_event = AuditEventRecord(
                case_id=case_id,
                event_type=(
                    AuditEventType
                    .ai_review_completed
                    .value
                ),
                actor_type=(
                    AuditActorType.system.value
                ),
                details={
                    "review_run_id": str(
                        review_run.id
                    ),
                    "document_id": str(
                        document.id
                    ),
                    "extraction_id": str(
                        extraction_record.id
                    ),
                    "fact_count": len(
                        extraction.facts
                    ),
                    "provider_name": (
                        provider.provider_name
                    ),
                    "model_name": (
                        provider.model_name
                    ),
                },
            )

            database.add(completed_event)

            try:
                database.commit()
            except IntegrityError as error:
                database.rollback()

                existing_extraction = (
                    self._find_existing_extraction(
                        database,
                        document_id=document.id,
                        provider=provider,
                    )
                )

                if existing_extraction is None:
                    raise ApplicationError(
                        "Extraction persistence conflict",
                        type="ExtractionConflict",
                    ) from error

                return self._build_extraction_result(
                    existing_extraction,
                    reused_existing=True,
                )

            return self._build_extraction_result(
                extraction_record,
                reused_existing=False,
            )