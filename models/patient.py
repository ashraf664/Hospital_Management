"""Patient demographic domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class Patient:
    patient_id: int | None = None
    patient_number: str
    full_name: str
    date_of_birth: str
    sex: str | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
