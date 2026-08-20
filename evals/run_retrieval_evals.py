import argparse
import math
import sys
from pathlib import Path
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_ROOT))


from app.chunking import chunk_text
from app.config import settings
from app.embedding_service import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
)
from app.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from app.retrieval_evaluation import (
    RankedDocument,
    RetrievalEvaluationDataset,
    RetrievalQueryEvaluation,
    cosine_similarity,
    evaluate_ranked_documents,
    select_candidate_threshold,
)


DATASET_PATH = (
    PROJECT_ROOT
    / "evals"
    / "datasets"
    / "clinical_retrieval_v1.json"
)


def build_provider(
    provider_name: str,
) -> EmbeddingProvider:
    if provider_name == "fake":
        return FakeEmbeddingProvider(
            dimensions=settings.embedding_dimensions
        )

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for "
            "OpenAI retrieval evaluations"
        )

    return OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model_name=settings.openai_embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.openai_timeout_seconds,
    )


def load_dataset() -> RetrievalEvaluationDataset:
    return RetrievalEvaluationDataset.model_validate_json(
        DATASET_PATH.read_text(encoding="utf-8")
    )


def average(
    values: list[float],
) -> float:
    return sum(values) / len(values)


def describe_scores(
    label: str,
    scores: list[float],
) -> None:
    print(
        f"{label}: "
        f"min={min(scores):.3f} "
        f"mean={average(scores):.3f} "
        f"max={max(scores):.3f}"
    )


def short_id(
    document_id: UUID,
) -> str:
    return str(document_id)[-3:]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run CaseLens retrieval evaluations"
    )

    parser.add_argument(
        "--provider",
        choices=["fake", "openai"],
        default="fake",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
    )

    arguments = parser.parse_args()

    if arguments.top_k <= 0:
        raise ValueError(
            "--top-k must be greater than zero"
        )

    provider = build_provider(arguments.provider)
    dataset = load_dataset()

    chunk_sources: list[tuple[UUID, str]] = []

    for document in dataset.documents:
        chunks = chunk_text(document.content)

        for chunk in chunks:
            chunk_sources.append(
                (
                    document.id,
                    chunk.content,
                )
            )

    if not chunk_sources:
        raise RuntimeError(
            "Evaluation dataset produced no chunks"
        )

    chunk_vectors = provider.embed([
        content
        for _, content in chunk_sources
    ])

    query_vectors = provider.embed([
        query.question
        for query in dataset.queries
    ])

    if len(chunk_vectors) != len(chunk_sources):
        raise RuntimeError(
            "Provider returned the wrong number "
            "of document embeddings"
        )

    if len(query_vectors) != len(dataset.queries):
        raise RuntimeError(
            "Provider returned the wrong number "
            "of query embeddings"
        )

    evaluations: list[
        RetrievalQueryEvaluation
    ] = []

    print(
        f"Provider: "
        f"{provider.provider_name}/"
        f"{provider.model_name}/"
        f"{provider.dimensions}"
    )
    print(f"Dataset: {DATASET_PATH.name}")
    print(f"Documents: {len(dataset.documents)}")
    print(f"Chunks: {len(chunk_sources)}")
    print(f"Queries: {len(dataset.queries)}")
    print(f"Top-k: {arguments.top_k}")
    print()

    for query, query_vector in zip(
        dataset.queries,
        query_vectors,
        strict=True,
    ):
        document_scores = {
            document.id: -math.inf
            for document in dataset.documents
        }

        for (
            document_id,
            _,
        ), chunk_vector in zip(
            chunk_sources,
            chunk_vectors,
            strict=True,
        ):
            similarity = cosine_similarity(
                query_vector,
                chunk_vector,
            )

            document_scores[document_id] = max(
                document_scores[document_id],
                similarity,
            )

        ranked_documents = [
            RankedDocument(
                document_id=document_id,
                similarity=similarity,
            )
            for document_id, similarity in sorted(
                document_scores.items(),
                key=lambda item: (
                    -item[1],
                    str(item[0]),
                ),
            )
        ]

        evaluation = evaluate_ranked_documents(
            query,
            ranked_documents,
            top_k=arguments.top_k,
        )

        evaluations.append(evaluation)

        top_result = ranked_documents[0]

        if evaluation.answerable:
            print(
                f"{query.name}: "
                f"top={short_id(top_result.document_id)} "
                f"score={top_result.similarity:.3f} "
                f"hit@1={evaluation.hit_at_1:.0f} "
                f"hit@{arguments.top_k}="
                f"{evaluation.hit_at_k:.0f} "
                f"rr={evaluation.reciprocal_rank:.3f}"
            )
        else:
            print(
                f"{query.name}: "
                f"top={short_id(top_result.document_id)} "
                f"score={top_result.similarity:.3f} "
                "expected=unanswerable"
            )

    answerable = [
        evaluation
        for evaluation in evaluations
        if evaluation.answerable
    ]

    unanswerable = [
        evaluation
        for evaluation in evaluations
        if not evaluation.answerable
    ]

    print()
    print("Retrieval metrics")
    print(
        "hit_at_1: "
        f"{average([
            evaluation.hit_at_1
            for evaluation in answerable
            if evaluation.hit_at_1 is not None
        ]):.3f}"
    )
    print(
        f"hit_at_{arguments.top_k}: "
        f"{average([
            evaluation.hit_at_k
            for evaluation in answerable
            if evaluation.hit_at_k is not None
        ]):.3f}"
    )
    print(
        "mean_reciprocal_rank: "
        f"{average([
            evaluation.reciprocal_rank
            for evaluation in answerable
            if evaluation.reciprocal_rank is not None
        ]):.3f}"
    )

    print()
    print("Top-similarity distributions")

    describe_scores(
        "answerable",
        [
            evaluation.top_similarity
            for evaluation in answerable
        ],
    )

    describe_scores(
        "unanswerable",
        [
            evaluation.top_similarity
            for evaluation in unanswerable
        ],
    )

    selected = select_candidate_threshold(
        evaluations
    )

    print()
    print("Candidate threshold")
    print(f"threshold: {selected.threshold:.6f}")
    print(f"precision: {selected.precision:.3f}")
    print(f"recall: {selected.recall:.3f}")
    print(f"f1: {selected.f1:.3f}")
    print(
        "false_positive_rate: "
        f"{selected.false_positive_rate:.3f}"
    )
    print(
        "confusion: "
        f"tp={selected.true_positives} "
        f"fp={selected.false_positives} "
        f"tn={selected.true_negatives} "
        f"fn={selected.false_negatives}"
    )


if __name__ == "__main__":
    main()