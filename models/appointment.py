"""Appointment domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class Appointment:
    appointment_id: int | None = None
    patient_id: int
    doctor_id: int
    scheduled_start: str
    scheduled_end: str
    status: str
    created_by_user_id: int
    reason: str | None = None
    cancellation_reason: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
