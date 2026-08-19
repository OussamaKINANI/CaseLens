from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.extraction_service import ExtractionProviderError
from app.openai_extraction_provider import (
    OpenAIExtractionProvider,
)
from app.openai_extraction_schemas import (
    OpenAIExtractionResponse,
)


class FakeResponses:
    def __init__(
        self,
        parsed: OpenAIExtractionResponse,
    ) -> None:
        self.parsed = parsed
        self.request: dict | None = None

    def parse(self, **kwargs):
        self.request = kwargs

        return SimpleNamespace(
            output_parsed=self.parsed,
        )


class FakeOpenAIClient:
    def __init__(
        self,
        parsed: OpenAIExtractionResponse,
    ) -> None:
        self.responses = FakeResponses(parsed)


def test_openai_provider_anchors_quote_in_document() -> None:
    document_id = uuid4()
    content = "Lower back pain is present."

    raw_response = OpenAIExtractionResponse.model_validate(
        {
            "facts": [
                {
                    "fact_type": "symptom",
                    "name": "Lower back pain",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": content,
                        }
                    ],
                }
            ]
        }
    )

    client = FakeOpenAIClient(raw_response)

    provider = OpenAIExtractionProvider(
        api_key="synthetic-test-key",
        model_name="gpt-5-mini",
        client=client,
    )

    result = provider.extract(
        document_id=document_id,
        content=content,
    )

    citation = result.facts[0].evidence[0]

    assert citation.start_char == 0
    assert citation.end_char == len(content)
    assert citation.exact_quote == content

    assert client.responses.request is not None
    assert (
        client.responses.request["text_format"]
        is OpenAIExtractionResponse
    )


def test_openai_provider_rejects_missing_quote() -> None:
    document_id = uuid4()

    raw_response = OpenAIExtractionResponse.model_validate(
        {
            "facts": [
                {
                    "fact_type": "condition",
                    "name": "Diabetes",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": "Diabetes",
                        }
                    ],
                }
            ]
        }
    )

    provider = OpenAIExtractionProvider(
        api_key="synthetic-test-key",
        model_name="gpt-5-mini",
        client=FakeOpenAIClient(raw_response),
    )

    with pytest.raises(
        ExtractionProviderError,
        match="not found",
    ):
        provider.extract(
            document_id=document_id,
            content="No supported condition is documented.",
        )