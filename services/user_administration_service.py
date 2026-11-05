"""Authorized account-management workflows."""

import sqlite3

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, User, UserRole
from repositories.audit_log_repository import AuditLogRepository
from repositories.user_repository import UserRepository
from repositories.user_summary import UserSummary
from services.authorization_service import AuthorizationService, Permission
from services.password_hasher import PasswordHasher


class UserAdministrationService:
    """Create and manage non-Owner accounts under an authenticated Admin."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        authorization_service: AuthorizationService,
        *,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.transaction_manager = TransactionManager(connection)
        self.authorization_service = authorization_service
        self.audit_repository = AuditLogRepository(connection)
        self.user_repository = UserRepository(connection)
        self.password_hasher = password_hasher or PasswordHasher()

    def create_user(
        self,
        session_token: str,
        username: str,
        password: str,
        role: UserRole,
    ) -> UserSummary:
        if not username.strip():
            raise ValueError("Username must not be empty.")
        if role is UserRole.OWNER:
            raise PermissionError(
                "The Owner role cannot be assigned through account management."
            )
        password_hash = self.password_hasher.hash_password(password)
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_USERS,
            )
            created = self.user_repository.create(
                User(
                    username=username,
                    password_hash=password_hash,
                    role=role,
                    is_active=True,
                )
            )
            self.audit_repository.create(
                AuditLog(
                    actor_type=AuditActorType.USER,
                    action="user_created",
                    entity_type="user",
                    user_id=actor.user_id,
                    entity_id=str(created.user_id),
                    details=f"role={role.value}",
                )
            )
            return created

    def update_user(
        self,
        session_token: str,
        user_id: int,
        username: str,
        role: UserRole,
    ) -> UserSummary | None:
        if not username.strip():
            raise ValueError("Username must not be empty.")
        if role is UserRole.OWNER:
            raise PermissionError(
                "The Owner role cannot be assigned through account management."
            )
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_USERS,
            )
            target = self.user_repository.find_by_id(user_id)
            if target is None:
                return None
            if target.role is UserRole.OWNER:
                raise PermissionError("The Owner account is separately protected.")
            if actor.user_id == user_id and role is not actor.role:
                raise PermissionError("An account cannot change its own role.")
            updated = self.user_repository.update_account(user_id, username, role)
            if updated is not None:
                self.audit_repository.create(
                    AuditLog(
                        actor_type=AuditActorType.USER,
                        action="user_account_updated",
                        entity_type="user",
                        user_id=actor.user_id,
                        entity_id=str(user_id),
                        details=f"role={role.value}",
                    )
                )
            return updated

    def deactivate_user(
        self,
        session_token: str,
        user_id: int,
    ) -> UserSummary | None:
        with self.transaction_manager.transaction():
            actor = self.authorization_service.require_permission(
                session_token,
                Permission.MANAGE_USERS,
            )
            if actor.user_id == user_id:
                raise PermissionError("An account cannot deactivate itself.")
            target = self.user_repository.find_by_id(user_id)
            if target is None:
                return None
            if target.role is UserRole.OWNER:
                raise PermissionError("The Owner account is separately protected.")
            deactivated = self.user_repository.deactivate(user_id)
            if deactivated is not None:
                self.audit_repository.create(
                    AuditLog(
                        actor_type=AuditActorType.USER,
                        action="user_deactivated",
                        entity_type="user",
                        user_id=actor.user_id,
                        entity_id=str(user_id),
                    )
                )
            return deactivated
