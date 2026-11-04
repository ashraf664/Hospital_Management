"""Non-sensitive user data for account lists and search results."""

from dataclasses import dataclass

from models.enums import UserRole


@dataclass(slots=True)
class UserSummary:
    """User fields suitable for display without authentication secrets."""

    user_id: int
    username: str
    role: UserRole
    is_active: bool
