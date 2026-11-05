"""Authorized doctor-directory workflows."""

import sqlite3

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, Doctor, UserRole
from repositories.audit_log_repository import AuditLogRepository
from repositories.department_repository import DepartmentRepository
from repositories.doctor_repository import DoctorRepository
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page
from repositories.user_repository import UserRepository
from services.authorization_service import AuthorizationService, Permission


class DoctorService:
    """Manage a nonclinical doctor directory under service authorization."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        authorization_service: AuthorizationService,
    ) -> None:
        self.transaction_manager = TransactionManager(connection)
        self.authorization_service = authorization_service
        self.doctor_repository = DoctorRepository(connection)
        self.department_repository = DepartmentRepository(connection)
        self.user_repository = UserRepository(connection)
        self.audit_repository = AuditLogRepository(connection)

    def create(
        self,
        session_token: str,
        user_id: int,
        department_id: int,
        full_name: str,
        specialty: str,
        phone: str | None = None,
    ) -> Doctor:
        self._validate_id(user_id, "user_id")
        self._validate_id(department_id, "department_id")
        normalized_name = self._required_text(full_name, "full_name")
        normalized_specialty = self._required_text(specialty, "specialty")
        normalized_phone = self._optional_text(phone, "phone")

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DOCTORS,
            )
            linked_user = self.user_repository.find_by_id(user_id)
            if (
                linked_user is None
                or not linked_user.is_active
                or linked_user.role is not UserRole.DOCTOR
            ):
                raise ValueError(
                    "A linked, active Doctor account is required."
                )
            if self.doctor_repository.find_by_user_id(user_id) is not None:
                raise ValueError("This user already has a doctor profile.")
            department = self.department_repository.find_by_id(department_id)
            if department is None or not department.is_active:
                raise ValueError("An active department is required.")

            created = self.doctor_repository.create(
                Doctor(
                    user_id=user_id,
                    department_id=department_id,
                    full_name=normalized_name,
                    specialty=normalized_specialty,
                    phone=normalized_phone,
                )
            )
            self._audit(actor.user_id, "doctor_created", created.doctor_id)
            return created

    def update(
        self,
        session_token: str,
        doctor_id: int,
        department_id: int,
        full_name: str,
        specialty: str,
        phone: str | None = None,
    ) -> Doctor | None:
        self._validate_id(doctor_id, "doctor_id")
        self._validate_id(department_id, "department_id")
        normalized_name = self._required_text(full_name, "full_name")
        normalized_specialty = self._required_text(specialty, "specialty")
        normalized_phone = self._optional_text(phone, "phone")

        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DOCTORS,
            )
            department = self.department_repository.find_by_id(department_id)
            if department is None or not department.is_active:
                raise ValueError("An active department is required.")
            updated = self.doctor_repository.update_details(
                doctor_id,
                department_id,
                normalized_name,
                normalized_specialty,
                normalized_phone,
            )
            if updated is not None:
                self._audit(actor.user_id, "doctor_updated", doctor_id)
            return updated

    def set_active(
        self,
        session_token: str,
        doctor_id: int,
        is_active: bool,
    ) -> Doctor | None:
        self._validate_id(doctor_id, "doctor_id")
        if type(is_active) is not bool:
            raise TypeError("is_active must be a boolean.")
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DOCTORS,
            )
            current = self.doctor_repository.find_by_id(doctor_id)
            if current is None:
                return None
            linked_user = self.user_repository.find_by_id(current.user_id)
            if linked_user is None:
                raise PersistenceIntegrityError(
                    "Doctor directory entry has no linked user account."
                )
            if current.is_active is is_active:
                return current

            if is_active:
                account_was_active = (
                    self.doctor_repository
                    .linked_user_was_active_before_deactivation(doctor_id)
                )
                updated = self.doctor_repository.activate(doctor_id)
            else:
                account_was_active = linked_user.is_active
                updated = self.doctor_repository.deactivate(
                    doctor_id,
                    linked_user_was_active=account_was_active,
                )
            if updated is not None:
                if (
                    is_active
                    and account_was_active is True
                    and not linked_user.is_active
                ):
                    account = self.user_repository.activate(current.user_id)
                    if account is None:
                        raise PersistenceIntegrityError(
                            "Doctor account could not be updated with its profile."
                        )
                    self._audit(
                        actor.user_id,
                        "doctor_account_activated",
                        current.user_id,
                        entity_type="user",
                    )
                elif not is_active and linked_user.is_active:
                    account = self.user_repository.deactivate(current.user_id)
                    if account is None:
                        raise PersistenceIntegrityError(
                            "Doctor account could not be updated with its profile."
                        )
                    self._audit(
                        actor.user_id,
                        "doctor_account_deactivated",
                        current.user_id,
                        entity_type="user",
                    )
                action = "doctor_activated" if is_active else "doctor_deactivated"
                self._audit(actor.user_id, action, doctor_id)
            return updated

    def find_by_id(
        self,
        session_token: str,
        doctor_id: int,
    ) -> Doctor | None:
        self._validate_id(doctor_id, "doctor_id")
        with self.transaction_manager.transaction():
            self.authorization_service.require_permission(
                session_token,
                Permission.VIEW_DOCTOR_DIRECTORY,
            )
            return self.doctor_repository.find_by_id(doctor_id)

    def find_my_profile(self, session_token: str) -> Doctor | None:
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.VIEW_OWN_PROFILE,
            )
            if actor.role is not UserRole.DOCTOR:
                raise PermissionError("Only a Doctor has a doctor profile.")
            return self.doctor_repository.find_by_user_id(actor.user_id)

    def search(
        self,
        session_token: str,
        *,
        department_id: int | None = None,
        full_name: str | None = None,
        specialty: str | None = None,
        is_active: bool | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Doctor]:
        if department_id is not None:
            self._validate_id(department_id, "department_id")
        normalized_name = (
            self._optional_text(full_name, "full_name")
            if full_name is not None
            else None
        )
        normalized_specialty = (
            self._optional_text(specialty, "specialty")
            if specialty is not None
            else None
        )
        if is_active is not None and type(is_active) is not bool:
            raise TypeError("is_active must be a boolean or None.")

        with self.transaction_manager.transaction():
            self.authorization_service.require_permission(
                session_token,
                Permission.VIEW_DOCTOR_DIRECTORY,
            )
            return self.doctor_repository.search(
                department_id=department_id,
                full_name=normalized_name,
                specialty=normalized_specialty,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )

    def _audit(
        self,
        user_id: int,
        action: str,
        entity_id: int | None,
        *,
        entity_type: str = "doctor",
    ) -> None:
        self.audit_repository.create(
            AuditLog(
                actor_type=AuditActorType.USER,
                action=action,
                entity_type=entity_type,
                user_id=user_id,
                entity_id=str(entity_id) if entity_id is not None else None,
            )
        )

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized

    @staticmethod
    def _optional_text(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string or None.")
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _validate_id(value: int, field_name: str) -> None:
        if type(value) is not int or value < 1:
            raise ValueError(f"{field_name} must be a positive integer.")
