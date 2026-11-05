"""Opaque authenticated-session values and in-process session registry."""

from dataclasses import dataclass, field
import secrets
from threading import RLock

from models.enums import UserRole


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session_token: str = field(repr=False)
    user_id: int
    username: str
    role: UserRole


class SessionRegistry:
    """Keep revocable session tokens in memory rather than persistent storage."""

    def __init__(self) -> None:
        self._user_ids: dict[str, int] = {}
        self._lock = RLock()

    def issue(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._user_ids[token] = user_id
        return token

    def resolve(self, token: str) -> int | None:
        with self._lock:
            return self._user_ids.get(token)

    def revoke(self, token: str) -> None:
        with self._lock:
            self._user_ids.pop(token, None)

    def revoke_user(self, user_id: int) -> None:
        with self._lock:
            revoked = [
                token
                for token, session_user_id in self._user_ids.items()
                if session_user_id == user_id
            ]
            for token in revoked:
                del self._user_ids[token]
