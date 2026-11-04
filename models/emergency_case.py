"""Emergency case domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class EmergencyCase:
    emergency_case_id: int | None = None
    case_number: str
    intake_user_id: int
    status: str
    arrival_at: str
    patient_id: int | None = None
    assigned_doctor_id: int | None = None
    triage_category: str | None = None
    closed_at: str | None = None
    intake_notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None
