from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai import OpenAIError

from app.embedding_service import EmbeddingProviderError
from app.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)


def make_provider(
    response_data: list[SimpleNamespace],
) -> tuple[OpenAIEmbeddingProvider, Mock]:
    client = Mock()
    client.embeddings.create.return_value = (
        SimpleNamespace(data=response_data)
    )

    provider = OpenAIEmbeddingProvider(
        model_name="text-embedding-3-small",
        dimensions=3,
        client=client,
    )

    return provider, client


def test_openai_provider_batches_inputs_and_orders_results() -> None:
    provider, client = make_provider([
        SimpleNamespace(
            index=1,
            embedding=[0.0, 1.0, 0.0],
        ),
        SimpleNamespace(
            index=0,
            embedding=[1.0, 0.0, 0.0],
        ),
    ])

    vectors = provider.embed([
        "Lower back pain",
        "Physical therapy",
    ])

    assert vectors == [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]

    client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input=[
            "Lower back pain",
            "Physical therapy",
        ],
        dimensions=3,
        encoding_format="float",
    )


def test_openai_provider_accepts_empty_batch() -> None:
    provider, client = make_provider([])

    assert provider.embed([]) == []
    client.embeddings.create.assert_not_called()


def test_openai_provider_rejects_blank_input() -> None:
    provider, client = make_provider([])

    with pytest.raises(EmbeddingProviderError):
        provider.embed(["   "])

    client.embeddings.create.assert_not_called()


def test_openai_provider_rejects_missing_result() -> None:
    provider, _ = make_provider([
        SimpleNamespace(
            index=0,
            embedding=[1.0, 0.0, 0.0],
        ),
    ])

    with pytest.raises(
        EmbeddingProviderError,
        match="unexpected number",
    ):
        provider.embed([
            "First document",
            "Second document",
        ])


def test_openai_provider_rejects_invalid_indices() -> None:
    provider, _ = make_provider([
        SimpleNamespace(
            index=2,
            embedding=[1.0, 0.0, 0.0],
        ),
    ])

    with pytest.raises(
        EmbeddingProviderError,
        match="invalid embedding indices",
    ):
        provider.embed(["Synthetic note"])


def test_openai_provider_rejects_wrong_dimensions() -> None:
    provider, _ = make_provider([
        SimpleNamespace(
            index=0,
            embedding=[1.0, 0.0],
        ),
    ])

    with pytest.raises(
        EmbeddingProviderError,
        match="wrong dimensions",
    ):
        provider.embed(["Synthetic note"])


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_openai_provider_rejects_nonfinite_values(
    invalid_value: float,
) -> None:
    provider, _ = make_provider([
        SimpleNamespace(
            index=0,
            embedding=[1.0, invalid_value, 0.0],
        ),
    ])

    with pytest.raises(
        EmbeddingProviderError,
        match="non-finite",
    ):
        provider.embed(["Synthetic note"])


def test_openai_provider_translates_api_errors() -> None:
    client = Mock()
    client.embeddings.create.side_effect = (
        OpenAIError("Provider unavailable")
    )

    provider = OpenAIEmbeddingProvider(
        dimensions=3,
        client=client,
    )

    with pytest.raises(
        EmbeddingProviderError,
        match="request failed",
    ):
        provider.embed(["Synthetic note"])


def test_openai_provider_requires_key_without_client() -> None:
    with pytest.raises(
        ValueError,
        match="API key",
    ):
        OpenAIEmbeddingProvider()