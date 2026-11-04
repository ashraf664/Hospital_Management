"""Immutable prior-state snapshot for a medical record."""

from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class MedicalRecordVersion:
    version_id: int | None = None
    medical_record_id: int
    patient_id_snapshot: int
    doctor_id_snapshot: int
    appointment_id_snapshot: int | None
    record_type_snapshot: str
    record_content_snapshot: str
    created_at_snapshot: str
    updated_at_snapshot: str
    is_amended_snapshot: bool
    modified_by_user_id: int
    modified_at: str
