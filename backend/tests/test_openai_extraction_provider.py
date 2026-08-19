from types import SimpleNamespace
from uuid import uuid4

from app.extraction_schemas import ClinicalExtraction
from app.openai_extraction_provider import (
    OpenAIExtractionProvider,
)


class FakeResponses:
    def __init__(
        self,
        parsed: ClinicalExtraction,
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
        parsed: ClinicalExtraction,
    ) -> None:
        self.responses = FakeResponses(parsed)


def test_openai_provider_requests_structured_output() -> None:
    document_id = uuid4()

    expected = ClinicalExtraction(
        facts=[],
        missing_information=[
            "No supported facts were found."
        ],
        warnings=[],
    )

    client = FakeOpenAIClient(expected)

    provider = OpenAIExtractionProvider(
        api_key="synthetic-test-key",
        model_name="gpt-5-mini",
        client=client,
    )

    result = provider.extract(
        document_id=document_id,
        content="Synthetic clinical note.",
    )

    assert result == expected
    assert client.responses.request is not None
    assert client.responses.request["model"] == "gpt-5-mini"
    assert (
        client.responses.request["text_format"]
        is ClinicalExtraction
    )
    assert str(document_id) in str(
        client.responses.request["input"]
    )