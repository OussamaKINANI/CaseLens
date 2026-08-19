import math
from collections.abc import Sequence

from openai import OpenAI, OpenAIError

from app.embedding_service import EmbeddingProviderError


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "text-embedding-3-small",
        dimensions: int = 1536,
        timeout_seconds: float = 120.0,
        client: OpenAI | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name cannot be blank")

        if dimensions <= 0:
            raise ValueError(
                "dimensions must be greater than zero"
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        if client is None and not api_key:
            raise ValueError(
                "An OpenAI API key is required"
            )

        self.model_name = model_name
        self.dimensions = dimensions

        self.client = client or OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
        )

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        input_texts = list(texts)

        if not input_texts:
            return []

        if any(not text.strip() for text in input_texts):
            raise EmbeddingProviderError(
                "Embedding inputs cannot be blank"
            )

        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=input_texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except OpenAIError as exc:
            raise EmbeddingProviderError(
                "OpenAI embedding request failed"
            ) from exc

        ordered_items = sorted(
            response.data,
            key=lambda item: item.index,
        )

        if len(ordered_items) != len(input_texts):
            raise EmbeddingProviderError(
                "OpenAI returned an unexpected number "
                "of embeddings"
            )

        returned_indices = [
            item.index
            for item in ordered_items
        ]

        expected_indices = list(
            range(len(input_texts))
        )

        if returned_indices != expected_indices:
            raise EmbeddingProviderError(
                "OpenAI returned invalid embedding indices"
            )

        vectors: list[list[float]] = []

        for item in ordered_items:
            try:
                vector = [
                    float(value)
                    for value in item.embedding
                ]
            except (TypeError, ValueError) as exc:
                raise EmbeddingProviderError(
                    "OpenAI returned a malformed embedding"
                ) from exc

            if len(vector) != self.dimensions:
                raise EmbeddingProviderError(
                    "OpenAI returned an embedding with "
                    "the wrong dimensions"
                )

            if any(
                not math.isfinite(value)
                for value in vector
            ):
                raise EmbeddingProviderError(
                    "OpenAI returned a non-finite embedding"
                )

            vectors.append(vector)

        return vectors