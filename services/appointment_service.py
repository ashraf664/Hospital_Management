"""Authorized appointment scheduling workflows."""

from datetime import datetime, timedelta, timezone
import sqlite3

from database.transaction_manager import TransactionManager
from models import Appointment, AuditActorType, AuditLog, UserRole
from repositories.appointment_repository import AppointmentRepository
from repositories.audit_log_repository import AuditLogRepository
from repositories.doctor_repository import DoctorRepository
from repositories.exceptions import PersistenceConstraintError
from repositories.page import DEFAULT_PAGE_LIMIT, Page
from repositories.patient_repository import PatientRepository
from repositories.user_summary import UserSummary
from repositories.user_repository import UserRepository
from services.authorization_service import AuthorizationService, Permission


_OVERLAP_ERROR = "Appointment overlaps an active appointment for this doctor."
_APPOINTMENT_STATUSES = (
    "Scheduled",
    "Confirmed",
    "Checked In",
    "In Progress",
    "Completed",
    "Cancelled",
    "No Show",
)
_STATUS_BY_CASEFOLD = {
    status.casefold(): status
    for status in _APPOINTMENT_STATUSES
}
_TERMINAL_STATUSES = frozenset({"Completed", "Cancelled", "No Show"})
_TRANSITIONS_BY_ROLE: dict[UserRole, dict[str, frozenset[str]]] = {
    UserRole.OWNER: {
        "Scheduled": frozenset({"Confirmed", "Checked In", "Cancelled", "No Show"}),
        "Confirmed": frozenset({"Checked In", "Cancelled", "No Show"}),
        "Checked In": frozenset({"Cancelled"}),
    },
    UserRole.ADMIN: {
        "Scheduled": frozenset({"Confirmed", "Checked In", "Cancelled", "No Show"}),
        "Confirmed": frozenset({"Checked In", "Cancelled", "No Show"}),
        "Checked In": frozenset({"Cancelled"}),
    },
    UserRole.RECEPTIONIST: {
        "Scheduled": frozenset({"Confirmed", "Checked In", "Cancelled", "No Show"}),
        "Confirmed": frozenset({"Checked In", "Cancelled", "No Show"}),
    },
    UserRole.DOCTOR: {
        "Checked In": frozenset({"In Progress"}),
        "In Progress": frozenset({"Completed"}),
    },
}


class AppointmentConflictError(ValueError):
    """Raised when an appointment overlaps another active appointment."""


class AppointmentService:
    """Validate, authorize, and audit appointment workflows."""

    STATUSES = _APPOINTMENT_STATUSES

    def __init__(
        self,
        connection: sqlite3.Connection,
        authorization_service: AuthorizationService,
        *,
        default_duration_minutes: int = 30,
    ) -> None:
        self._validate_duration(default_duration_minutes)
        self.default_duration_minutes = default_duration_minutes
        self.transaction_manager = TransactionManager(connection)
        self.authorization_service = authorization_service
        self.appointment_repository = AppointmentRepository(connection)
        self.patient_repository = PatientRepository(connection)
        self.doctor_repository = DoctorRepository(connection)
        self.user_repository = UserRepository(connection)
        self.audit_repository = AuditLogRepository(connection)

    def create(
        self,
        session_token: str,
        patient_id: int,
        doctor_id: int,
        scheduled_start: str,
        *,
        duration_minutes: int | None = None,
    ) -> Appointment:
        self._validate_id(patient_id, "patient_id")
        self._validate_id(doctor_id, "doctor_id")
        start = self._parse_timestamp(scheduled_start, "scheduled_start")
        duration = (
            self.default_duration_minutes
            if duration_minutes is None
            else duration_minutes
        )
        self._validate_duration(duration)
        try:
            end = self._format_timestamp(start + timedelta(minutes=duration))
        except OverflowError as error:
            raise ValueError("The requested appointment duration is too large.") from error

        try:
            with self.transaction_manager.transaction("IMMEDIATE"):
                actor = self.authorization_service.require_permission(
                    session_token,
                    Permission.MANAGE_APPOINTMENTS,
                )
                self._require_active_references(patient_id, doctor_id)
                created = self.appointment_repository.create(
                    Appointment(
                        patient_id=patient_id,
                        doctor_id=doctor_id,
                        scheduled_start=self._format_timestamp(start),
                        scheduled_end=end,
                        status="Scheduled",
                        created_by_user_id=actor.user_id,
                    )
                )
                self._audit(actor.user_id, "appointment_created", created.appointment_id)
                return created
        except PersistenceConstraintError as error:
            self._raise_if_overlap(error)
            raise

    def reschedule(
        self,
        session_token: str,
        appointment_id: int,
        scheduled_start: str,
        *,
        duration_minutes: int | None = None,
    ) -> Appointment | None:
        self._validate_id(appointment_id, "appointment_id")
        start = self._parse_timestamp(scheduled_start, "scheduled_start")
        duration = (
            self.default_duration_minutes
            if duration_minutes is None
            else duration_minutes
        )
        self._validate_duration(duration)
        try:
            end = self._format_timestamp(start + timedelta(minutes=duration))
        except OverflowError as error:
            raise ValueError("The requested appointment duration is too large.") from error

        try:
            with self.transaction_manager.transaction("IMMEDIATE"):
                actor = self.authorization_service.require_permission(
                    session_token,
                    Permission.MANAGE_APPOINTMENTS,
                )
                current = self.appointment_repository.find_by_id(appointment_id)
                if current is None:
                    return None
                current_status = self._canonical_status(current.status)
                if current_status in _TERMINAL_STATUSES:
                    raise ValueError(
                        "A terminal appointment cannot be rescheduled; "
                        "create a new appointment instead."
                    )
                self._require_active_references(
                    current.patient_id,
                    current.doctor_id,
                )
                updated = self.appointment_repository.reschedule(
                    appointment_id,
                    self._format_timestamp(start),
                    end,
                )
                if updated is not None:
                    self._audit(
                        actor.user_id,
                        "appointment_rescheduled",
                        appointment_id,
                    )
                return updated
        except PersistenceConstraintError as error:
            self._raise_if_overlap(error)
            raise

    def cancel(
        self,
        session_token: str,
        appointment_id: int,
        cancellation_reason: str | None = None,
    ) -> Appointment | None:
        self._validate_id(appointment_id, "appointment_id")
        normalized_reason = self._optional_text(
            cancellation_reason,
            "cancellation_reason",
        )
        if normalized_reason is None:
            raise ValueError("cancellation_reason is required.")
        with self.transaction_manager.transaction("IMMEDIATE"):
            actor, current = self._authorized_actor_and_appointment(
                session_token,
                appointment_id,
            )
            if current is None:
                return None
            self._require_transition(actor.role, current.status, "Cancelled")
            cancelled = self.appointment_repository.cancel(
                appointment_id,
                normalized_reason,
            )
            if cancelled is not None:
                self._audit(
                    actor.user_id,
                    "appointment_cancelled",
                    appointment_id,
                )
            return cancelled

    def update_status(
        self,
        session_token: str,
        appointment_id: int,
        status: str,
    ) -> Appointment | None:
        self._validate_id(appointment_id, "appointment_id")
        normalized_status = self._normalize_status(status)
        if normalized_status == "Cancelled":
            raise ValueError("Use the cancellation workflow to cancel an appointment.")

        with self.transaction_manager.transaction("IMMEDIATE"):
            actor, current = self._authorized_actor_and_appointment(
                session_token,
                appointment_id,
            )
            if current is None:
                return None
            self._require_transition(
                actor.role,
                current.status,
                normalized_status,
            )
            updated = self.appointment_repository.update_status(
                appointment_id,
                normalized_status,
            )
            if updated is not None:
                self._audit(
                    actor.user_id,
                    "appointment_status_updated",
                    appointment_id,
                )
            return updated

    def available_transitions(
        self,
        session_token: str,
        appointment_id: int,
    ) -> tuple[str, ...]:
        """Return transitions allowed for this actor and appointment state."""
        self._validate_id(appointment_id, "appointment_id")
        with self.transaction_manager.transaction():
            actor, current = self._authorized_actor_and_appointment(
                session_token,
                appointment_id,
            )
            if current is None:
                return ()
            current_status = self._canonical_status(current.status)
            return tuple(
                status
                for status in self.STATUSES
                if status
                in _TRANSITIONS_BY_ROLE.get(actor.role, {}).get(
                    current_status,
                    frozenset(),
                )
            )

    def find_by_id(
        self,
        session_token: str,
        appointment_id: int,
    ) -> Appointment | None:
        self._validate_id(appointment_id, "appointment_id")
        with self.transaction_manager.transaction():
            self.authorization_service.require_appointment_schedule_access(
                session_token
            )
            appointment = self.appointment_repository.find_by_id(appointment_id)
            if appointment is None:
                return None
            self.authorization_service.require_appointment_access(
                session_token,
                appointment_id,
            )
            return appointment

    def search(
        self,
        session_token: str,
        *,
        patient_id: int | None = None,
        doctor_id: int | None = None,
        start_from: str | None = None,
        start_to: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Appointment]:
        if patient_id is not None:
            self._validate_id(patient_id, "patient_id")
        if doctor_id is not None:
            self._validate_id(doctor_id, "doctor_id")
        parsed_start = (
            self._parse_timestamp(start_from, "start_from")
            if start_from is not None
            else None
        )
        parsed_end = (
            self._parse_timestamp(start_to, "start_to")
            if start_to is not None
            else None
        )
        if parsed_start is not None and parsed_end is not None:
            if parsed_start >= parsed_end:
                raise ValueError("start_from must be earlier than start_to.")
        normalized_start = (
            self._format_timestamp(parsed_start)
            if parsed_start is not None
            else None
        )
        normalized_end = (
            self._format_timestamp(parsed_end)
            if parsed_end is not None
            else None
        )
        normalized_status = (
            self._normalize_status(status)
            if status is not None
            else None
        )

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_appointment_schedule_access(
                session_token
            )
            if actor.role is UserRole.DOCTOR:
                own_doctor_id = (
                    self.authorization_service.authorization_repository
                    .doctor_id_for_user(actor.user_id)
                )
                if (
                    own_doctor_id is None
                    or not self.authorization_service.authorization_repository
                    .doctor_is_active(own_doctor_id)
                ):
                    raise PermissionError(
                        "An active doctor profile is required to view a schedule."
                    )
                if doctor_id is not None and doctor_id != own_doctor_id:
                    raise PermissionError(
                        "Doctors may view only their own appointments."
                    )
                doctor_id = own_doctor_id
            return self.appointment_repository.search(
                patient_id=patient_id,
                doctor_id=doctor_id,
                start_from=normalized_start,
                start_to=normalized_end,
                status=normalized_status,
                limit=limit,
                offset=offset,
            )

    def _authorized_actor_and_appointment(
        self,
        session_token: str,
        appointment_id: int,
    ) -> tuple[UserSummary, Appointment | None]:
        actor = self.authorization_service.require_appointment_schedule_access(
            session_token
        )
        appointment = self.appointment_repository.find_by_id(appointment_id)
        if appointment is None:
            return actor, None
        if actor.role is UserRole.DOCTOR:
            doctor_id = (
                self.authorization_service.authorization_repository
                .doctor_id_for_user(actor.user_id)
            )
            if (
                doctor_id is None
                or doctor_id != appointment.doctor_id
                or not self.authorization_service.authorization_repository
                .doctor_is_active(doctor_id)
            ):
                raise PermissionError(
                    "Doctors may update only appointments assigned to them."
                )
        return actor, appointment

    @classmethod
    def _normalize_status(cls, status: str) -> str:
        normalized = cls._required_text(status, "status")
        if normalized not in cls.STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(cls.STATUSES)}."
            )
        return normalized

    @staticmethod
    def _canonical_status(status: str) -> str:
        canonical = _STATUS_BY_CASEFOLD.get(status.strip().casefold())
        if canonical is None:
            raise ValueError(
                f"The current appointment status is not recognized: {status!r}."
            )
        return canonical

    @staticmethod
    def _require_transition(
        role: UserRole,
        current_status: str,
        next_status: str,
    ) -> None:
        current_canonical = _STATUS_BY_CASEFOLD.get(
            current_status.strip().casefold()
        )
        if current_canonical is None:
            raise ValueError(
                f"The current appointment status is not recognized: {current_status!r}."
            )
        allowed = _TRANSITIONS_BY_ROLE.get(role, {}).get(
            current_canonical,
            frozenset(),
        )
        if next_status not in allowed:
            raise PermissionError(
                f"{role.value} cannot transition an appointment from "
                f"{current_canonical} to {next_status}."
            )

    def _require_active_references(self, patient_id: int, doctor_id: int) -> None:
        patient = self.patient_repository.find_by_id(patient_id)
        if patient is None:
            raise ValueError("The selected patient does not exist.")
        if not patient.is_active:
            raise ValueError("Appointments require an active patient.")

        doctor = self.doctor_repository.find_by_id(doctor_id)
        if doctor is None:
            raise ValueError("The selected doctor does not exist.")
        linked_user = self.user_repository.find_by_id(doctor.user_id)
        if not doctor.is_active or linked_user is None or not linked_user.is_active:
            raise ValueError("Appointments require an active doctor account.")

    def _audit(self, user_id: int, action: str, appointment_id: int | None) -> None:
        self.audit_repository.create(
            AuditLog(
                actor_type=AuditActorType.USER,
                action=action,
                entity_type="appointment",
                user_id=user_id,
                entity_id=(
                    str(appointment_id)
                    if appointment_id is not None
                    else None
                ),
            )
        )

    @classmethod
    def _parse_timestamp(cls, value: str, field_name: str) -> datetime:
        normalized = cls._required_text(value, field_name)
        try:
            parsed = datetime.fromisoformat(
                normalized[:-1] + "+00:00"
                if normalized.endswith("Z")
                else normalized
            )
        except ValueError as error:
            raise ValueError(
                f"{field_name} must be a valid ISO 8601 timestamp with a timezone."
            ) from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(
                f"{field_name} must include an explicit timezone."
            )
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _format_timestamp(value: datetime) -> str:
        timespec = "microseconds" if value.microsecond else "seconds"
        return value.isoformat(timespec=timespec).replace("+00:00", "Z")

    @staticmethod
    def _validate_id(value: int, field_name: str) -> None:
        if type(value) is not int or value < 1:
            raise ValueError(f"{field_name} must be a positive integer.")

    @staticmethod
    def _validate_duration(value: int) -> None:
        if type(value) is not int or value < 1:
            raise ValueError("duration_minutes must be a positive integer.")

    @classmethod
    def _required_text(cls, value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized

    @classmethod
    def _optional_text(cls, value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string or None.")
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _raise_if_overlap(error: PersistenceConstraintError) -> None:
        original_cause = error.original_cause
        if original_cause is not None and _OVERLAP_ERROR in str(original_cause):
            raise AppointmentConflictError(
                "The doctor already has an overlapping active appointment."
            ) from error
