"""Password authentication, first-Owner setup, and session lifecycle."""

import secrets
import sqlite3
from datetime import datetime, timezone

from database.transaction_manager import TransactionManager
from models import AuditActorType, AuditLog, User, UserRole
from repositories.audit_log_repository import AuditLogRepository
from repositories.owner_repository import OwnerRepository
from repositories.user_repository import UserRepository
from services.password_hasher import PasswordHasher
from services.session import AuthenticatedSession, SessionRegistry


class AuthenticationError(Exception):
    """Raised when credentials or an authenticated session are invalid."""


class AuthenticationService:
    """Authenticate active accounts and persist security events atomically."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        session_registry: SessionRegistry | None = None,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.connection = connection
        self.transaction_manager = TransactionManager(connection)
        self.audit_repository = AuditLogRepository(connection)
        self.owner_repository = OwnerRepository(connection)
        self.user_repository = UserRepository(connection)
        self.session_registry = session_registry or SessionRegistry()
        self.password_hasher = password_hasher or PasswordHasher()
        self._dummy_hash = self.password_hasher.hash_password(
            secrets.token_urlsafe(24)
        )

    def first_owner_setup_available(self) -> bool:
        return (
            not self.owner_repository.has_owner()
            and self.owner_repository.user_count() == 0
        )

    def create_first_owner(self, username: str, password: str) -> int:
        """Create the sole Owner during a genuinely empty first-run setup."""
        self._validate_username(username)
        password_hash = self.password_hasher.hash_password(password)
        with self.transaction_manager.transaction("EXCLUSIVE"):
            if not self.first_owner_setup_available():
                raise PermissionError(
                    "First Owner setup is unavailable after account creation."
                )
            created = self.user_repository.create(
                User(
                    username=username,
                    password_hash=password_hash,
                    role=UserRole.ADMIN,
                    is_active=True,
                )
            )
            self.owner_repository.claim_first_owner(created.user_id)
            self.audit_repository.create(
                AuditLog(
                    actor_type=AuditActorType.FIRST_ADMIN_SETUP,
                    action="first_owner_created",
                    entity_type="owner_account",
                    entity_id="1",
                    details="Initial Owner account configured.",
                )
            )
            return created.user_id

    def login(self, username: str, password: str) -> AuthenticatedSession:
        """Validate credentials and audit the result before granting a session."""
        if not isinstance(username, str):
            raise TypeError("username must be a string.")
        user = None
        succeeded = False
        with self.transaction_manager.transaction():
            user = self.user_repository.find_for_authentication(username)
            encoded_hash = user.password_hash if user is not None else self._dummy_hash
            password_matches = self.password_hasher.verify_password(
                password,
                encoded_hash,
            )
            succeeded = user is not None and user.is_active and password_matches
            event_at = self._now()
            if succeeded:
                self.audit_repository.create(
                    AuditLog(
                        actor_type=AuditActorType.USER,
                        action="authentication_succeeded",
                        entity_type="user",
                        user_id=user.user_id,
                        entity_id=str(user.user_id),
                        occurred_at=event_at,
                    )
                )
            else:
                self.audit_repository.create(
                    AuditLog(
                        actor_type=AuditActorType.ANONYMOUS,
                        action="authentication_failed",
                        entity_type="user",
                        details=(
                            f"attempted_username={username}; "
                            "reason=invalid_credentials"
                        ),
                        occurred_at=event_at,
                    )
                )

        if not succeeded or user is None or user.user_id is None:
            raise AuthenticationError("Invalid username or password.")
        token = self.session_registry.issue(user.user_id)
        return AuthenticatedSession(
            session_token=token,
            user_id=user.user_id,
            username=user.username,
            role=user.role,
        )

    def logout(self, session_token: str) -> None:
        user_id = self.session_registry.resolve(session_token)
        if user_id is None:
            raise AuthenticationError("The session is invalid or has expired.")
        try:
            with self.transaction_manager.transaction():
                self.audit_repository.create(
                    AuditLog(
                        actor_type=AuditActorType.USER,
                        action="session_ended",
                        entity_type="user",
                        user_id=user_id,
                        entity_id=str(user_id),
                        occurred_at=self._now(),
                    )
                )
        finally:
            self.session_registry.revoke(session_token)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")

    @staticmethod
    def _validate_username(username: str) -> None:
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Username must not be empty.")
