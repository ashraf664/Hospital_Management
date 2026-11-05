"""Authorized department directory workflows."""

import sqlite3

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, Department
from repositories.audit_log_repository import AuditLogRepository
from repositories.department_repository import DepartmentRepository
from repositories.page import DEFAULT_PAGE_LIMIT, Page
from services.authorization_service import AuthorizationService, Permission


class DepartmentService:
    """Validate, authorize, and audit department directory operations."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        authorization_service: AuthorizationService,
    ) -> None:
        self.transaction_manager = TransactionManager(connection)
        self.authorization_service = authorization_service
        self.department_repository = DepartmentRepository(connection)
        self.audit_repository = AuditLogRepository(connection)

    def create(
        self,
        session_token: str,
        name: str,
        description: str = "",
    ) -> Department:
        normalized_name = self._required_text(name, "name")
        normalized_description = self._optional_text(description, "description")
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DEPARTMENTS,
            )
            created = self.department_repository.create(
                Department(
                    name=normalized_name,
                    description=normalized_description or "",
                )
            )
            self._audit(actor.user_id, "department_created", created.department_id)
            return created

    def update(
        self,
        session_token: str,
        department_id: int,
        name: str,
        description: str,
    ) -> Department | None:
        self._validate_id(department_id, "department_id")
        normalized_name = self._required_text(name, "name")
        normalized_description = self._optional_text(description, "description")
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DEPARTMENTS,
            )
            updated = self.department_repository.update_details(
                department_id,
                normalized_name,
                normalized_description or "",
            )
            if updated is not None:
                self._audit(actor.user_id, "department_updated", department_id)
            return updated

    def set_active(
        self,
        session_token: str,
        department_id: int,
        is_active: bool,
    ) -> Department | None:
        self._validate_id(department_id, "department_id")
        if type(is_active) is not bool:
            raise TypeError("is_active must be a boolean.")
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DEPARTMENTS,
            )
            updated = (
                self.department_repository.activate(department_id)
                if is_active
                else self.department_repository.deactivate(department_id)
            )
            if updated is not None:
                action = (
                    "department_activated"
                    if is_active
                    else "department_deactivated"
                )
                self._audit(actor.user_id, action, department_id)
            return updated

    def find_by_id(
        self,
        session_token: str,
        department_id: int,
    ) -> Department | None:
        self._validate_id(department_id, "department_id")
        with self.transaction_manager.transaction():
            self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DEPARTMENTS,
            )
            return self.department_repository.find_by_id(department_id)

    def search(
        self,
        session_token: str,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Department]:
        normalized_name = (
            self._optional_text(name, "name") if name is not None else None
        )
        self._validate_active_filter(is_active)
        with self.transaction_manager.transaction():
            self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_DEPARTMENTS,
            )
            return self.department_repository.search(
                name=normalized_name,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )

    def _audit(self, user_id: int, action: str, department_id: int | None) -> None:
        self.audit_repository.create(
            AuditLog(
                actor_type=AuditActorType.USER,
                action=action,
                entity_type="department",
                user_id=user_id,
                entity_id=(
                    str(department_id) if department_id is not None else None
                ),
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

    @staticmethod
    def _validate_active_filter(is_active: bool | None) -> None:
        if is_active is not None and type(is_active) is not bool:
            raise TypeError("is_active must be a boolean or None.")
