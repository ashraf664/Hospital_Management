"""Doctor-to-patient care assignment domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class DoctorPatientAssignment:
    assignment_id: int | None = None
    doctor_id: int
    patient_id: int
    assigned_by_user_id: int
    assigned_at: str | None = None
    ended_by_user_id: int | None = None
    ended_at: str | None = None
    end_reason: str | None = None
