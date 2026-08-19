import math

import pytest

from app.embedding_service import (
    EmbeddingProviderError,
    FakeEmbeddingProvider,
)


def test_fake_provider_returns_expected_dimensions() -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    vectors = provider.embed([
        "Lower back pain is present."
    ])

    assert len(vectors) == 1
    assert len(vectors[0]) == 1536


def test_fake_provider_is_deterministic() -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    first = provider.embed([
        "Physical therapy did not improve symptoms."
    ])
    second = provider.embed([
        "Physical therapy did not improve symptoms."
    ])

    assert first == second


def test_fake_provider_is_case_insensitive() -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    lowercase = provider.embed([
        "penicillin allergy"
    ])
    uppercase = provider.embed([
        "PENICILLIN ALLERGY"
    ])

    assert lowercase == uppercase


def test_fake_provider_normalizes_vectors() -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    vector = provider.embed([
        "Synthetic clinical note"
    ])[0]

    magnitude = math.sqrt(
        sum(value * value for value in vector)
    )

    assert magnitude == pytest.approx(1.0)


def test_fake_provider_returns_one_vector_per_input() -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    vectors = provider.embed([
        "Lower back pain",
        "Penicillin allergy",
        "Physical therapy",
    ])

    assert len(vectors) == 3


def test_fake_provider_accepts_empty_batch() -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    assert provider.embed([]) == []


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\n\t",
        "---",
    ],
)
def test_fake_provider_rejects_unsearchable_input(
    text: str,
) -> None:
    provider = FakeEmbeddingProvider(
        dimensions=1536
    )

    with pytest.raises(EmbeddingProviderError):
        provider.embed([text])


@pytest.mark.parametrize(
    "dimensions",
    [
        0,
        -1,
    ],
)
def test_fake_provider_rejects_invalid_dimensions(
    dimensions: int,
) -> None:
    with pytest.raises(ValueError):
        FakeEmbeddingProvider(
            dimensions=dimensions
        )