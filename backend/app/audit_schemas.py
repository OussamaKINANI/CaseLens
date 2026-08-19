from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventType(str, Enum):
    case_created = "case_created"
    status_changed = "status_changed"
    ai_review_started = "ai_review_started"
    ai_review_completed = "ai_review_completed"
    human_review_completed = "human_review_completed"
    processing_failed = "processing_failed"
    document_uploaded = "document_uploaded"
    document_indexed = "document_indexed"


class AuditActorType(str, Enum):
    system = "system"
    reviewer = "reviewer"


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    event_type: AuditEventType
    actor_type: AuditActorType
    details: dict[str, Any]
    created_at: datetime