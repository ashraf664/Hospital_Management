"""Persistence repositories and shared repository components."""

from repositories.base_repository import BaseRepository
from repositories.exceptions import (
    PersistenceConflictError,
    PersistenceConstraintError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceTransactionError,
    PersistenceUnavailableError,
)
from repositories.page import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from repositories.appointment_repository import AppointmentRepository
from repositories.audit_log_repository import AuditLogRepository
from repositories.department_repository import DepartmentRepository
from repositories.doctor_repository import DoctorRepository
from repositories.emergency_case_repository import EmergencyCaseRepository
from repositories.patient_repository import PatientRepository
from repositories.user_repository import UserRepository
from repositories.user_summary import UserSummary

__all__ = [
    "BaseRepository",
    "AppointmentRepository",
    "AuditLogRepository",
    "DEFAULT_PAGE_LIMIT",
    "DepartmentRepository",
    "DoctorRepository",
    "EmergencyCaseRepository",
    "MAX_PAGE_LIMIT",
    "Page",
    "PatientRepository",
    "PersistenceConflictError",
    "PersistenceConstraintError",
    "PersistenceError",
    "PersistenceIntegrityError",
    "PersistenceTransactionError",
    "PersistenceUnavailableError",
    "UserRepository",
    "UserSummary",
]
