"""Authorized, audited workflows for emergency intake and assignment."""

from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
import sqlite3

from data_structures import DynamicArray
from database.transaction_manager import TransactionManager
from models import (
    AuditActorType,
    AuditLog,
    Doctor,
    EmergencyCase,
    UserRole,
)
from repositories.audit_log_repository import AuditLogRepository
from repositories.doctor_repository import DoctorRepository
from repositories.emergency_case_repository import EmergencyCaseRepository
from repositories.exceptions import PersistenceConflictError
from repositories.page import DEFAULT_PAGE_LIMIT, Page
from repositories.patient_repository import PatientRepository
from repositories.user_repository import UserRepository
from services.authorization_service import AuthorizationService, Permission


@dataclass(frozen=True, slots=True)
class EmergencyCaseIntakeView:
    """Administrative case fields that deliberately omit clinical content."""

    emergency_case_id: int
    case_number: str
    patient_id: int | None
    assigned_doctor_id: int | None
    status: str
    arrival_at: str
    created_at: str
    updated_at: str


class EmergencyCaseService:
    """Authorize emergency intake workflows and keep writes atomic."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        authorization_service: AuthorizationService,
    ) -> None:
        self.connection = connection
        self.transaction_manager = TransactionManager(connection)
        self.case_repository = EmergencyCaseRepository(connection)
        self.audit_log_repository = AuditLogRepository(connection)
        self.patient_repository = PatientRepository(connection)
        self.doctor_repository = DoctorRepository(connection)
        self.user_repository = UserRepository(connection)
        self.authorization_service = authorization_service

    def create_case(
        self,
        session_token: str,
        *,
        patient_id: int | None = None,
        intake_notes: str = "",
        assigned_doctor_id: int | None = None,
        assignment_reason: str | None = None,
    ) -> EmergencyCaseIntakeView:
        """Create a case and its immutable intake and optional assignment events."""
        self._validate_optional_id(patient_id, "patient_id")
        self._validate_optional_id(assigned_doctor_id, "assigned_doctor_id")
        if not isinstance(intake_notes, str):
            raise TypeError("intake_notes must be a string.")
        if assigned_doctor_id is not None:
            self._validate_reason(assignment_reason)

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_EMERGENCY_INTAKE,
            )
            if patient_id is not None and self.patient_repository.find_by_id(
                patient_id
            ) is None:
                raise ValueError("The selected patient does not exist.")
            if assigned_doctor_id is not None:
                self._require_active_doctor(assigned_doctor_id)

            event_at = self._now()
            case = self.case_repository.create(
                EmergencyCase(
                    case_number=self._new_case_number(event_at),
                    intake_user_id=actor.user_id,
                    status="Open",
                    arrival_at=event_at,
                    patient_id=patient_id,
                    intake_notes=intake_notes,
                )
            )
            audit_log = self._create_audit(
                actor.user_id,
                "emergency_case_created",
                int(case.emergency_case_id),
                event_at,
            )
            self.case_repository.record_case_created(
                case,
                actor_user_id=actor.user_id,
                audit_log_id=int(audit_log.audit_log_id),
                event_at=event_at,
            )

            if assigned_doctor_id is not None:
                case = self._record_assignment(
                    case,
                    assigned_doctor_id,
                    actor.user_id,
                    assignment_reason or "",
                    event_at,
                    first_assignment=True,
                )
            return self._view(case)

    def link_patient(
        self,
        emergency_case_id: int,
        patient_id: int,
        session_token: str,
        change_reason: str,
    ) -> EmergencyCaseIntakeView | None:
        """Link an existing patient, preserving intake snapshots and audit data."""
        self._validate_id(emergency_case_id, "emergency_case_id")
        self._validate_id(patient_id, "patient_id")
        self._validate_reason(change_reason)

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_EMERGENCY_INTAKE,
            )
            case = self.case_repository.find_by_id(emergency_case_id)
            if case is None:
                return None
            if self.patient_repository.find_by_id(patient_id) is None:
                return None
            if case.patient_id == patient_id:
                return self._view(case)

            event_at = self._now()
            audit_log = self._create_audit(
                actor.user_id,
                "patient_linked",
                emergency_case_id,
                event_at,
            )
            linked = self.case_repository.link_patient(
                emergency_case_id,
                patient_id,
                actor_user_id=actor.user_id,
                audit_log_id=int(audit_log.audit_log_id),
                change_reason=change_reason.strip(),
                event_at=event_at,
            )
            if linked is None:
                raise RuntimeError(
                    "Emergency case disappeared while its patient was being linked."
                )
            return self._view(linked)

    def assign_doctor(
        self,
        emergency_case_id: int,
        doctor_id: int,
        session_token: str,
        change_reason: str,
    ) -> EmergencyCaseIntakeView | None:
        """Assign or reassign a doctor with one audited history event."""
        self._validate_id(emergency_case_id, "emergency_case_id")
        self._validate_id(doctor_id, "doctor_id")
        self._validate_reason(change_reason)

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_EMERGENCY_INTAKE,
            )
            case = self.case_repository.find_by_id(emergency_case_id)
            if case is None:
                return None
            self._require_active_doctor(doctor_id)
            if case.assigned_doctor_id == doctor_id:
                return self._view(case)

            assigned = self._record_assignment(
                case,
                doctor_id,
                actor.user_id,
                change_reason.strip(),
                self._now(),
                first_assignment=case.assigned_doctor_id is None,
            )
            return self._view(assigned)

    def update_intake_notes(
        self,
        emergency_case_id: int,
        intake_notes: str,
        session_token: str,
        change_reason: str,
    ) -> EmergencyCaseIntakeView | None:
        """Record a reasoned notes correction without returning note contents."""
        self._validate_id(emergency_case_id, "emergency_case_id")
        if not isinstance(intake_notes, str):
            raise TypeError("intake_notes must be a string.")
        self._validate_reason(change_reason)

        with self.transaction_manager.transaction():
            principal = self.authorization_service.require_permission(
                session_token,
                Permission.VIEW_OWN_PROFILE,
            )
            if principal.role is UserRole.DOCTOR:
                actor = self.authorization_service.require_emergency_case_access(
                    session_token,
                    emergency_case_id,
                    write=True,
                )
            else:
                actor = self.authorization_service.require_permission(
                    session_token,
                    Permission.MANAGE_EMERGENCY_INTAKE,
                )
            case = self.case_repository.find_by_id(emergency_case_id)
            if case is None:
                return None
            if case.status == "Closed":
                raise ValueError(
                    "Intake notes cannot be updated after the case is closed."
                )
            if case.intake_notes == intake_notes:
                return self._view(case)

            event_at = self._now()
            audit_log = self._create_audit(
                actor.user_id,
                "emergency_intake_updated",
                emergency_case_id,
                event_at,
            )
            updated = self.case_repository.update_intake_notes(
                emergency_case_id,
                intake_notes,
                actor_user_id=actor.user_id,
                audit_log_id=int(audit_log.audit_log_id),
                change_reason=change_reason.strip(),
                event_at=event_at,
            )
            if updated is None:
                raise RuntimeError(
                    "Emergency case disappeared while its intake was being updated."
                )
            return self._view(updated)

    def find_case(
        self,
        emergency_case_id: int,
        session_token: str,
    ) -> EmergencyCaseIntakeView | None:
        """Read only the case fields safe for administrative intake screens."""
        self._validate_id(emergency_case_id, "emergency_case_id")
        with self.transaction_manager.transaction():
            principal = self.authorization_service.require_permission(
                session_token,
                Permission.VIEW_OWN_PROFILE,
            )
            if principal.role is UserRole.DOCTOR:
                self.authorization_service.require_emergency_case_access(
                    session_token,
                    emergency_case_id,
                    clinical=False,
                )
            else:
                self.authorization_service.require_permission(
                    session_token,
                    Permission.MANAGE_EMERGENCY_INTAKE,
                )
            case = self.case_repository.find_by_id(emergency_case_id)
            if case is None:
                return None
            return self._view(case)

    def search_cases(
        self,
        session_token: str,
        *,
        case_number: str | None = None,
        patient_id: int | None = None,
        assigned_doctor_id: int | None = None,
        arrival_date: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[EmergencyCaseIntakeView]:
        """Search cases with role-scoped access and bounded pagination."""
        if patient_id is not None:
            self._validate_id(patient_id, "patient_id")
        if assigned_doctor_id is not None:
            self._validate_id(assigned_doctor_id, "assigned_doctor_id")
        if case_number is not None and not case_number.strip():
            raise ValueError("case_number must not be empty.")
        if arrival_date is not None:
            try:
                datetime.strptime(arrival_date, "%Y-%m-%d")
            except ValueError as error:
                raise ValueError("arrival_date must use YYYY-MM-DD.") from error

        with self.transaction_manager.transaction():
            principal = self.authorization_service.require_permission(
                session_token,
                Permission.VIEW_OWN_PROFILE,
            )
            doctor_filter = assigned_doctor_id
            if principal.role is UserRole.DOCTOR:
                doctor = self.doctor_repository.find_by_user_id(principal.user_id)
                if doctor is None or not doctor.is_active:
                    raise PermissionError("An active doctor profile is required.")
                if (
                    assigned_doctor_id is not None
                    and assigned_doctor_id != doctor.doctor_id
                ):
                    raise PermissionError(
                        "Doctors may search only their own assigned cases."
                    )
                doctor_filter = doctor.doctor_id
            else:
                self.authorization_service.require_permission(
                    session_token,
                    Permission.MANAGE_EMERGENCY_INTAKE,
                )

            cases = self.case_repository.search(
                case_number=case_number.strip() if case_number else None,
                patient_id=patient_id,
                assigned_doctor_id=doctor_filter,
                arrival_date=arrival_date,
                status=status,
                limit=limit,
                offset=offset,
            )
            if principal.role is UserRole.DOCTOR:
                for case in cases.items:
                    self.authorization_service.require_emergency_case_access(
                        session_token,
                        int(case.emergency_case_id),
                        clinical=False,
                    )
            views: DynamicArray[EmergencyCaseIntakeView] = DynamicArray()
            for case in cases.items:
                views.append(self._view(case))
            return Page(
                items=views,
                total_count=cases.total_count,
                limit=cases.limit,
                offset=cases.offset,
            )

    def active_doctors(
        self,
        session_token: str,
    ) -> tuple[Doctor, ...]:
        """Return assignable doctors whose directory and user account are active."""
        self.authorization_service.require_permission(
            session_token,
            Permission.MANAGE_EMERGENCY_INTAKE,
        )
        page = self.doctor_repository.search(is_active=True, limit=200)
        return tuple(
            doctor
            for doctor in page.items
            if (user := self.user_repository.find_by_id(doctor.user_id)) is not None
            and user.is_active
        )

    def _record_assignment(
        self,
        case: EmergencyCase,
        doctor_id: int,
        actor_user_id: int,
        change_reason: str,
        event_at: str,
        *,
        first_assignment: bool,
    ) -> EmergencyCase:
        action = (
            "emergency_doctor_assigned"
            if first_assignment
            else "emergency_doctor_reassigned"
        )
        audit_log = self._create_audit(
            actor_user_id,
            action,
            int(case.emergency_case_id),
            event_at,
        )
        assigned = self.case_repository.record_doctor_assignment(
            int(case.emergency_case_id),
            doctor_id,
            actor_user_id=actor_user_id,
            audit_log_id=int(audit_log.audit_log_id),
            change_reason=change_reason,
            event_at=event_at,
        )
        if assigned is None:
            raise RuntimeError(
                "Emergency case disappeared while its doctor was being assigned."
            )
        return assigned

    def _require_active_doctor(self, doctor_id: int) -> Doctor:
        doctor = self.doctor_repository.find_by_id(doctor_id)
        if doctor is None or not doctor.is_active:
            raise ValueError("The selected doctor is not active.")
        user = self.user_repository.find_by_id(doctor.user_id)
        if user is None or not user.is_active:
            raise ValueError("The selected doctor's account is not active.")
        return doctor

    def _create_audit(
        self,
        actor_user_id: int,
        action: str,
        emergency_case_id: int,
        event_at: str,
    ) -> AuditLog:
        return self.audit_log_repository.create(
            AuditLog(
                actor_type=AuditActorType.USER,
                action=action,
                entity_type="emergency_case",
                user_id=actor_user_id,
                entity_id=str(emergency_case_id),
                occurred_at=event_at,
            )
        )

    @staticmethod
    def _view(case: EmergencyCase) -> EmergencyCaseIntakeView:
        if case.emergency_case_id is None or case.created_at is None:
            raise RuntimeError("Persisted emergency case identity is incomplete.")
        return EmergencyCaseIntakeView(
            emergency_case_id=case.emergency_case_id,
            case_number=case.case_number,
            patient_id=case.patient_id,
            assigned_doctor_id=case.assigned_doctor_id,
            status=case.status,
            arrival_at=case.arrival_at,
            created_at=case.created_at,
            updated_at=case.updated_at or case.created_at,
        )

    def _new_case_number(self, event_at: str) -> str:
        date_part = event_at[:10].replace("-", "")
        for _ in range(5):
            candidate = f"ER-{date_part}-{secrets.token_hex(8).upper()}"
            if self.case_repository.find_by_case_number(candidate) is None:
                return candidate
        raise PersistenceConflictError(
            "A unique emergency case number could not be allocated."
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")

    @staticmethod
    def _validate_id(value: int, name: str) -> None:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")

    @classmethod
    def _validate_optional_id(cls, value: int | None, name: str) -> None:
        if value is not None:
            cls._validate_id(value, name)

    @staticmethod
    def _validate_reason(reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A non-empty change reason is required.")
