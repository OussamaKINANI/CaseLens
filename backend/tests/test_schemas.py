import pytest
from pydantic import ValidationError

from app.schemas import CaseCreate, CasePriority


def test_case_create_accepts_valid_data() -> None:
    case = CaseCreate(
        patient_external_id="  SYNTH-001  ",
        requested_service="Lumbar spine MRI",
        priority="urgent",
    )

    assert case.patient_external_id == "SYNTH-001"
    assert case.priority == CasePriority.urgent


def test_case_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CaseCreate(
            patient_external_id="SYNTH-001",
            requested_service="Lumbar spine MRI",
            unexpected_field="not allowed",
        )