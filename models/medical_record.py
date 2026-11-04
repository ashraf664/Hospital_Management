"""Medical record domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class MedicalRecord:
    medical_record_id: int | None = None
    patient_id: int
    doctor_id: int
    record_type: str
    record_content: str
    appointment_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    is_amended: bool = False
