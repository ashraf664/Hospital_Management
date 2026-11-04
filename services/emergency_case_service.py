"""Authorized emergency-case workflows."""

from datetime import datetime, timezone
import sqlite3

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, EmergencyCase, UserRole
from repositories.audit_log_repository import AuditLogRepository
from repositories.emergency_case_repository import EmergencyCaseRepository
from repositories.patient_repository import PatientRepository
from repositories.user_repository import UserRepository


class EmergencyCaseService:
    """Authorize emergency-case workflows and keep their writes atomic."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.transaction_manager = TransactionManager(connection)
        self.case_repository = EmergencyCaseRepository(connection)
        self.audit_log_repository = AuditLogRepository(connection)
        self.patient_repository = PatientRepository(connection)
        self.user_repository = UserRepository(connection)

    def link_patient(
        self,
        emergency_case_id: int,
        patient_id: int,
        actor_user_id: int,
        change_reason: str,
    ) -> EmergencyCase | None:
        """Link an existing patient using one authorized, audited transaction."""
        if not change_reason.strip():
            raise ValueError("change_reason must not be empty.")

        with self.transaction_manager.transaction():
            actor = self.user_repository.find_by_id(actor_user_id)
            if (
                actor is None
                or not actor.is_active
                or actor.role not in (UserRole.ADMIN, UserRole.RECEPTIONIST)
            ):
                raise PermissionError(
                    "Only active Admin or Receptionist users may link a patient."
                )

            case = self.case_repository.find_by_id(emergency_case_id)
            if case is None:
                return None

            patient = self.patient_repository.find_by_id(patient_id)
            if patient is None:
                return None

            if case.patient_id == patient_id:
                return case

            event_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            audit_log = self.audit_log_repository.create(
                AuditLog(
                    actor_type=AuditActorType.USER,
                    action="patient_linked",
                    entity_type="emergency_case",
                    user_id=actor_user_id,
                    entity_id=str(emergency_case_id),
                    occurred_at=event_at,
                )
            )
            linked = self.case_repository.link_patient(
                emergency_case_id,
                patient_id,
                actor_user_id=actor_user_id,
                audit_log_id=int(audit_log.audit_log_id),
                change_reason=change_reason,
                event_at=event_at,
            )
            if linked is None:
                raise RuntimeError(
                    "Emergency case disappeared while its patient was being linked."
                )
            return linked
