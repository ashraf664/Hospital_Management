"""Service-layer authorization policies and access auditing."""

from enum import Enum
import sqlite3
from datetime import datetime, timezone

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, UserRole
from repositories.audit_log_repository import AuditLogRepository
from repositories.authorization_repository import AuthorizationRepository
from repositories.user_repository import UserRepository
from services.session import SessionRegistry
from repositories.user_summary import UserSummary


class Permission(str, Enum):
    VIEW_OWN_PROFILE = "view_own_profile"
    MANAGE_USERS = "manage_users"
    MANAGE_DEPARTMENTS = "manage_departments"
    MANAGE_DOCTORS = "manage_doctors"
    VIEW_DOCTOR_DIRECTORY = "view_doctor_directory"
    CREATE_PATIENT = "create_patient"
    VIEW_AUDIT_METADATA = "view_audit_metadata"
    MANAGE_PATIENT_DEMOGRAPHICS = "manage_patient_demographics"
    MANAGE_APPOINTMENTS = "manage_appointments"
    VIEW_OWN_SCHEDULE = "view_own_schedule"
    MANAGE_EMERGENCY_INTAKE = "manage_emergency_intake"
    VIEW_CLINICAL_CONTENT = "view_clinical_content"
    UPDATE_CLINICAL_CONTENT = "update_clinical_content"


_ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.OWNER: frozenset(
        {
            Permission.VIEW_OWN_PROFILE,
            Permission.MANAGE_USERS,
            Permission.MANAGE_DEPARTMENTS,
            Permission.MANAGE_DOCTORS,
            Permission.VIEW_DOCTOR_DIRECTORY,
            Permission.VIEW_AUDIT_METADATA,
            Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            Permission.CREATE_PATIENT,
            Permission.MANAGE_APPOINTMENTS,
            Permission.MANAGE_EMERGENCY_INTAKE,
        }
    ),
    UserRole.ADMIN: frozenset(
        {
            Permission.VIEW_OWN_PROFILE,
            Permission.MANAGE_USERS,
            Permission.MANAGE_DEPARTMENTS,
            Permission.MANAGE_DOCTORS,
            Permission.VIEW_DOCTOR_DIRECTORY,
            Permission.VIEW_AUDIT_METADATA,
            Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            Permission.CREATE_PATIENT,
            Permission.MANAGE_APPOINTMENTS,
            Permission.MANAGE_EMERGENCY_INTAKE,
        }
    ),
    UserRole.DOCTOR: frozenset(
        {
            Permission.VIEW_OWN_PROFILE,
            Permission.VIEW_OWN_SCHEDULE,
            Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            Permission.VIEW_CLINICAL_CONTENT,
            Permission.UPDATE_CLINICAL_CONTENT,
        }
    ),
    UserRole.RECEPTIONIST: frozenset(
        {
            Permission.VIEW_OWN_PROFILE,
            Permission.VIEW_DOCTOR_DIRECTORY,
            Permission.MANAGE_PATIENT_DEMOGRAPHICS,
            Permission.CREATE_PATIENT,
            Permission.MANAGE_APPOINTMENTS,
            Permission.MANAGE_EMERGENCY_INTAKE,
        }
    ),
}


class AuthorizationService:
    """Validate opaque sessions and enforce role and care-scope policies."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        session_registry: SessionRegistry,
    ) -> None:
        self.connection = connection
        self.transaction_manager = TransactionManager(connection)
        self.audit_repository = AuditLogRepository(connection)
        self.authorization_repository = AuthorizationRepository(connection)
        self.user_repository = UserRepository(connection)
        self.session_registry = session_registry

    def require_permission(
        self,
        session_token: str,
        permission: Permission,
    ) -> UserSummary:
        denied = False
        principal: UserSummary | None = None
        with self.transaction_manager.transaction():
            principal = self._resolve_principal(session_token, permission.value)
            if principal is None:
                denied = True
            elif permission not in _ROLE_PERMISSIONS[principal.role]:
                self._record_event(
                    principal.user_id,
                    "authorization_denied",
                    "permission",
                    permission.value,
                )
                denied = True
            else:
                self._record_event(
                    principal.user_id,
                    "authorization_granted",
                    "permission",
                    permission.value,
                )
        if denied or principal is None:
            raise PermissionError("The requested operation is not permitted.")
        return principal

    def require_patient_access(
        self,
        session_token: str,
        patient_id: int,
        *,
        clinical: bool = False,
        write: bool = False,
    ) -> UserSummary:
        denied = False
        principal: UserSummary | None = None
        with self.transaction_manager.transaction():
            principal = self._resolve_principal(
                session_token,
                f"patient:{patient_id}",
            )
            allowed = False
            if principal is None:
                denied = True
            elif principal.role is UserRole.DOCTOR:
                doctor_id = self.authorization_repository.doctor_id_for_user(
                    principal.user_id
                )
                allowed = doctor_id is not None and (
                    self.authorization_repository.doctor_is_active(doctor_id)
                    and
                    self.authorization_repository.patient_exists(patient_id)
                ) and (
                    self.authorization_repository.has_active_patient_assignment(
                        doctor_id,
                        patient_id,
                    )
                )
            elif not clinical and principal.role in {
                UserRole.OWNER,
                UserRole.ADMIN,
                UserRole.RECEPTIONIST,
            }:
                allowed = self.authorization_repository.patient_exists(patient_id)
            if principal is not None:
                self._record_access_result(
                    principal.user_id,
                    allowed,
                    "patient",
                    patient_id,
                    clinical,
                )
                denied = not allowed
        if denied or principal is None:
            raise PermissionError("Patient access is not permitted.")
        return principal

    def require_emergency_case_access(
        self,
        session_token: str,
        emergency_case_id: int,
        *,
        clinical: bool = False,
        write: bool = False,
    ) -> UserSummary:
        denied = False
        principal: UserSummary | None = None
        with self.transaction_manager.transaction():
            principal = self._resolve_principal(
                session_token,
                f"emergency_case:{emergency_case_id}",
            )
            if principal is None:
                denied = True
            elif principal.role is UserRole.DOCTOR:
                doctor_id = self.authorization_repository.doctor_id_for_user(
                    principal.user_id
                )
                allowed = doctor_id is not None and (
                    self.authorization_repository.emergency_case_exists(
                        emergency_case_id
                    )
                    and (
                        not write
                        or self.authorization_repository.doctor_is_active(doctor_id)
                    )
                ) and (
                    self.authorization_repository.has_emergency_case_relationship(
                        doctor_id,
                        emergency_case_id,
                        write=write,
                    )
                )
            else:
                allowed = (
                    not clinical
                    and principal.role
                    in {
                        UserRole.OWNER,
                        UserRole.ADMIN,
                        UserRole.RECEPTIONIST,
                    }
                )
                if allowed:
                    allowed = self.authorization_repository.emergency_case_exists(
                        emergency_case_id
                    )
            if principal is not None:
                self._record_access_result(
                    principal.user_id,
                    allowed,
                    "emergency_case",
                    emergency_case_id,
                    clinical,
                )
                denied = not allowed
        if denied or principal is None:
            raise PermissionError("Emergency-case access is not permitted.")
        return principal

    def require_medical_record_access(
        self,
        session_token: str,
        medical_record_id: int,
        *,
        write: bool = False,
    ) -> UserSummary:
        denied = False
        principal: UserSummary | None = None
        with self.transaction_manager.transaction():
            principal = self._resolve_principal(
                session_token,
                f"medical_record:{medical_record_id}",
            )
            scope = self.authorization_repository.medical_record_scope(
                medical_record_id
            )
            allowed = False
            if principal is None:
                denied = True
            elif scope is not None and principal.role is UserRole.DOCTOR:
                patient_id, record_doctor_id = scope
                doctor_id = self.authorization_repository.doctor_id_for_user(
                    principal.user_id
                )
                if doctor_id is not None:
                    allowed = (
                        self.authorization_repository.has_patient_care_relationship(
                            doctor_id,
                            patient_id,
                            write=write,
                        )
                        and (not write or record_doctor_id == doctor_id)
                    )
            if principal is not None:
                self._record_access_result(
                    principal.user_id,
                    allowed,
                    "medical_record",
                    medical_record_id,
                    True,
                )
                denied = not allowed
        if denied or principal is None:
            raise PermissionError("Medical-record access is not permitted.")
        return principal

    def require_appointment_access(
        self,
        session_token: str,
        appointment_id: int,
        *,
        update_clinical_status: bool = False,
    ) -> UserSummary:
        denied = False
        principal: UserSummary | None = None
        with self.transaction_manager.transaction():
            principal = self._resolve_principal(
                session_token,
                f"appointment:{appointment_id}",
            )
            scope = self.authorization_repository.appointment_scope(
                appointment_id
            )
            allowed = False
            if principal is not None and scope is not None:
                doctor_user_id, doctor_is_active = scope
                if principal.role is UserRole.DOCTOR:
                    allowed = (
                        doctor_user_id == principal.user_id
                        and doctor_is_active
                        and (
                            not update_clinical_status
                            or Permission.UPDATE_CLINICAL_CONTENT
                            in _ROLE_PERMISSIONS[principal.role]
                        )
                    )
                else:
                    required_permission = (
                        Permission.MANAGE_APPOINTMENTS
                        if not update_clinical_status
                        else Permission.UPDATE_CLINICAL_CONTENT
                    )
                    allowed = (
                        required_permission
                        in _ROLE_PERMISSIONS[principal.role]
                    )
            if principal is not None:
                self._record_access_result(
                    principal.user_id,
                    allowed,
                    "appointment",
                    appointment_id,
                    update_clinical_status,
                )
                denied = not allowed
        if denied or principal is None:
            raise PermissionError("Appointment access is not permitted.")
        return principal

    def require_appointment_schedule_access(
        self,
        session_token: str,
    ) -> UserSummary:
        """Authorize appointment management or a doctor's own schedule view."""
        denied = False
        principal: UserSummary | None = None
        with self.transaction_manager.transaction():
            principal = self._resolve_principal(session_token, "appointment_schedule")
            allowed = principal is not None and (
                Permission.MANAGE_APPOINTMENTS
                in _ROLE_PERMISSIONS[principal.role]
                or Permission.VIEW_OWN_SCHEDULE
                in _ROLE_PERMISSIONS[principal.role]
            )
            if principal is not None:
                self._record_access_result(
                    principal.user_id,
                    allowed,
                    "appointment_schedule",
                    principal.user_id,
                    False,
                )
                denied = not allowed
        if denied or principal is None:
            raise PermissionError("Appointment schedule access is not permitted.")
        return principal

    def _resolve_principal(
        self,
        session_token: str,
        resource: str,
    ) -> UserSummary | None:
        user_id = self.session_registry.resolve(session_token)
        if user_id is None:
            self._record_event(
                None,
                "authorization_denied",
                "session",
                None,
                f"resource={resource}",
            )
            return None
        principal = self.user_repository.find_by_id(user_id)
        if principal is None or not principal.is_active:
            self._record_event(
                user_id if principal is not None else None,
                "authorization_denied",
                "session",
                str(user_id),
                f"resource={resource}; reason=inactive_or_missing_account",
            )
            return None
        return principal

    def _record_access_result(
        self,
        user_id: int,
        allowed: bool,
        resource_type: str,
        resource_id: int,
        clinical: bool,
    ) -> None:
        action = (
            "clinical_data_access_granted"
            if allowed and clinical
            else "resource_access_granted"
            if allowed
            else "clinical_data_access_denied"
            if clinical
            else "resource_access_denied"
        )
        self._record_event(
            user_id,
            action,
            resource_type,
            str(resource_id),
        )

    def _record_event(
        self,
        user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: str = "",
    ) -> None:
        self.audit_repository.create(
            AuditLog(
                actor_type=(
                    AuditActorType.USER
                    if user_id is not None
                    else AuditActorType.ANONYMOUS
                ),
                action=action,
                entity_type=entity_type,
                user_id=user_id,
                entity_id=entity_id,
                details=details,
                occurred_at=datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ).replace("+00:00", "Z"),
            )
        )
