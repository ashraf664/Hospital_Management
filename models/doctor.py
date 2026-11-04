"""Doctor directory domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class Doctor:
    doctor_id: int | None = None
    user_id: int
    department_id: int
    full_name: str
    specialty: str
    phone: str | None = None
    is_active: bool = True
