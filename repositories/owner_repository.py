"""Persistence for the unique Owner identity."""

from repositories.base_repository import BaseRepository


class OwnerRepository(BaseRepository):
    """Manage the single Owner marker without managing its transaction."""

    def has_owner(self) -> bool:
        row = self._fetchone("SELECT 1 FROM owner_accounts WHERE singleton_id = 1")
        return row is not None

    def is_owner(self, user_id: int) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM owner_accounts WHERE user_id = ?",
            (user_id,),
        )
        return row is not None

    def user_count(self) -> int:
        row = self._fetchone("SELECT COUNT(*) AS user_count FROM users")
        return int(row["user_count"]) if row is not None else 0

    def claim_first_owner(self, user_id: int) -> None:
        self._execute(
            "INSERT INTO owner_accounts (singleton_id, user_id) VALUES (1, ?)",
            (user_id,),
        )
