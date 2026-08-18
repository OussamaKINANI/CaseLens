from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClinicalDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    content_sha256: str
    uploaded_at: datetime