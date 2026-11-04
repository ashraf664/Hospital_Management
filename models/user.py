"""User account domain model."""

from dataclasses import dataclass

from models.enums import UserRole


@dataclass(kw_only=True)
class User:
    user_id: int | None = None
    username: str
    password_hash: str
    role: UserRole
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
