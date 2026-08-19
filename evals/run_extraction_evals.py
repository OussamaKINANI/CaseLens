import argparse
import sys
from pathlib import Path

from pydantic import TypeAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_ROOT))


from app.config import settings
from app.extraction_evaluation import (
    ExtractionEvaluation,
    ExtractionEvaluationCase,
    evaluate_extraction,
)
from app.extraction_service import (
    ExtractionProvider,
    FakeExtractionProvider,
)
from app.openai_extraction_provider import (
    OpenAIExtractionProvider,
)


DATASET_PATH = (
    PROJECT_ROOT
    / "evals"
    / "datasets"
    / "clinical_extraction_v1.json"
)


def build_provider(
    provider_name: str,
) -> ExtractionProvider:
    if provider_name == "fake":
        return FakeExtractionProvider()

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for OpenAI evaluations"
        )

    return OpenAIExtractionProvider(
        api_key=settings.openai_api_key,
        model_name=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )


def load_dataset() -> list[ExtractionEvaluationCase]:
    adapter = TypeAdapter(
        list[ExtractionEvaluationCase]
    )

    return adapter.validate_json(
        DATASET_PATH.read_text(encoding="utf-8")
    )


def average_metric(
    results: list[ExtractionEvaluation],
    metric_name: str,
) -> float:
    return sum(
        getattr(result, metric_name)
        for result in results
    ) / len(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run CaseLens extraction evaluations"
    )

    parser.add_argument(
        "--provider",
        choices=["fake", "openai"],
        default="fake",
    )

    parser.add_argument(
        "--show-outputs",
        action="store_true",
        help="Print each provider extraction as JSON",
    )

    arguments = parser.parse_args()

    provider = build_provider(arguments.provider)
    cases = load_dataset()
    results: list[ExtractionEvaluation] = []

    print(
        f"Provider: "
        f"{provider.provider_name}/"
        f"{provider.model_name}"
    )

    print(f"Dataset: {DATASET_PATH.name}")
    print(f"Cases: {len(cases)}")
    print()

    for case in cases:
        extraction = provider.extract(
            document_id=case.document_id,
            content=case.content,
        )
        extraction = provider.extract(
            document_id=case.document_id,
            content=case.content,
        )

        if arguments.show_outputs:
            print()
            print(f"Raw extraction for {case.name}")
            print(
                extraction.model_dump_json(
                    indent=2,
                )
            )

        evaluation = evaluate_extraction(
            extraction=extraction,
            expected_facts=case.expected_facts,
            documents={
                case.document_id: case.content,
            },
        )

        results.append(evaluation)

        print(
            f"{case.name}: "
            f"precision={evaluation.precision:.3f} "
            f"recall={evaluation.recall:.3f} "
            f"f1={evaluation.f1:.3f} "
            f"classification="
            f"{evaluation.classification_accuracy:.3f} "
            f"unsupported="
            f"{evaluation.unsupported_fact_rate:.3f} "
            f"citations="
            f"{evaluation.citation_validity:.3f}"
        )

    print()
    print("Macro averages")

    for metric_name in [
        "precision",
        "recall",
        "f1",
        "classification_accuracy",
        "unsupported_fact_rate",
        "citation_validity",
    ]:
        value = average_metric(
            results,
            metric_name,
        )

        print(f"{metric_name}: {value:.3f}")


if __name__ == "__main__":
    main()