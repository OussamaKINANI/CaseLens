import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot produce valid vectors."""


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimensions: int

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Convert text strings into embedding vectors."""
        ...


class FakeEmbeddingProvider:
    """
    Deterministic local provider for tests and development.

    This does not understand clinical meaning. It creates stable vectors
    from token hashes so the surrounding RAG pipeline can be tested
    without network calls or API charges.
    """

    provider_name = "fake"
    model_name = "deterministic-hash-v1"

    def __init__(
        self,
        *,
        dimensions: int = 1536,
    ) -> None:
        if dimensions <= 0:
            raise ValueError(
                "dimensions must be greater than zero"
            )

        self.dimensions = dimensions

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        if any(not text.strip() for text in texts):
            raise EmbeddingProviderError(
                "Embedding inputs cannot be blank"
            )

        return [
            self._embed_one(text)
            for text in texts
        ]

    def _embed_one(
        self,
        text: str,
    ) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _TOKEN_PATTERN.findall(text.lower())

        for token in tokens:
            digest = hashlib.sha256(
                token.encode("utf-8")
            ).digest()

            vector_index = (
                int.from_bytes(
                    digest[:8],
                    byteorder="big",
                )
                % self.dimensions
            )

            sign = (
                1.0
                if digest[8] % 2 == 0
                else -1.0
            )

            vector[vector_index] += sign

        magnitude = math.sqrt(
            sum(value * value for value in vector)
        )

        if magnitude == 0:
            raise EmbeddingProviderError(
                "Embedding input contains no searchable tokens"
            )

        return [
            value / magnitude
            for value in vector
        ]