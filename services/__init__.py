"""Application services coordinating authorization and persistence workflows."""

from repositories.exceptions import (
    PersistenceConflictError,
    PersistenceConstraintError,
    PersistenceError,
)
from services.appointment_service import (
    AppointmentConflictError,
    AppointmentService,
)
from services.emergency_case_service import (
    EmergencyCaseIntakeView,
    EmergencyCaseService,
)
from services.authentication_service import AuthenticationError, AuthenticationService
from services.authorization_service import AuthorizationService, Permission
from services.department_service import DepartmentService
from services.doctor_service import DoctorService
from services.patient_service import PatientService
from services.session import AuthenticatedSession, SessionRegistry
from services.user_administration_service import UserAdministrationService

__all__ = [
    "AuthenticatedSession",
    "AuthenticationError",
    "AuthenticationService",
    "AppointmentConflictError",
    "AppointmentService",
    "AuthorizationService",
    "DepartmentService",
    "DoctorService",
    "EmergencyCaseService",
    "EmergencyCaseIntakeView",
    "PatientService",
    "PersistenceConflictError",
    "PersistenceConstraintError",
    "PersistenceError",
    "Permission",
    "SessionRegistry",
    "UserAdministrationService",
]
