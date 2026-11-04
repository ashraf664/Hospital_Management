"""Domain models.

Date-only values use YYYY-MM-DD strings. Timestamp values use UTC ISO 8601
strings ending in Z, matching the SQLite schema. A None generated identifier
or database-default timestamp denotes a model that has not been persisted yet.
"""

from models.appointment import Appointment
from models.audit_log import AuditLog
from models.department import Department
from models.doctor import Doctor
from models.doctor_patient_assignment import DoctorPatientAssignment
from models.emergency_case import EmergencyCase
from models.enums import AuditActorType, UserRole
from models.medical_record import MedicalRecord
from models.medical_record_version import MedicalRecordVersion
from models.patient import Patient
from models.user import User

__all__ = [
    "Appointment",
    "AuditActorType",
    "AuditLog",
    "Department",
    "Doctor",
    "DoctorPatientAssignment",
    "EmergencyCase",
    "MedicalRecord",
    "MedicalRecordVersion",
    "Patient",
    "User",
    "UserRole",
]
