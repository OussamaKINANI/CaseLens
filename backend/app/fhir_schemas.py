from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.document_schemas import ClinicalDocumentRead


class FHIRBundleEntry(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )

    full_url: str = Field(
        alias="fullUrl",
        min_length=1,
    )
    resource: dict[str, Any]

    @field_validator("resource")
    @classmethod
    def validate_resource_type(
        cls,
        resource: dict[str, Any],
    ) -> dict[str, Any]:
        resource_type = resource.get("resourceType")

        if not isinstance(resource_type, str) or not resource_type:
            raise ValueError(
                "Every FHIR resource must have a resourceType"
            )

        return resource


class FHIRBundle(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )

    resource_type: Literal["Bundle"] = Field(alias="resourceType")
    id: str | None = None
    type: Literal["collection"]
    entry: list[FHIRBundleEntry] = Field(min_length=1)


class FHIRImportRead(BaseModel):
    document: ClinicalDocumentRead
    bundle_type: str
    resource_counts: dict[str, int]