"""SQLite repository for user accounts."""

import sqlite3

from models import User, UserRole
from repositories.base_repository import BaseRepository, SQLiteParameter
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page
from repositories.user_summary import UserSummary


_USER_SUMMARY_COLUMNS = "user_id, username, role, is_active"
_AUTHENTICATION_COLUMNS = (
    "user_id, username, password_hash, role, is_active, created_at, updated_at"
)


class UserRepository(BaseRepository):
    """Persist user accounts without exposing password hashes in listings."""

    def create(self, user: User) -> UserSummary:
        """Insert an account and return only display-safe database values."""
        if user.role is UserRole.OWNER:
            raise ValueError("Owner accounts can only be created during first setup.")
        cursor = self._execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (?, ?, ?, ?)
            """,
            (
                user.username,
                user.password_hash,
                user.role.value,
                int(user.is_active),
            ),
        )
        row = self._fetchone(
            f"""
            SELECT {_USER_SUMMARY_COLUMNS}, 0 AS is_owner
            FROM users
            WHERE user_id = ?
            """,
            (int(cursor.lastrowid),),
        )
        if row is None:
            raise PersistenceIntegrityError(
                "Inserted user could not be read back from SQLite."
            )
        return self._summary_from_row(row)

    def update_account(
        self,
        user_id: int,
        username: str,
        role: UserRole,
    ) -> UserSummary | None:
        """Update account identity and role without changing its password hash."""
        if role is UserRole.OWNER:
            raise ValueError("Owner role cannot be assigned through account management.")
        cursor = self._execute(
            """
            UPDATE users
            SET username = ?,
                role = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE user_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM owner_accounts
                  WHERE owner_accounts.user_id = users.user_id
              )
            """,
            (username, role.value, user_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(user_id)

    def deactivate(self, user_id: int) -> UserSummary | None:
        """Deactivate an account without deleting its history."""
        cursor = self._execute(
            """
            UPDATE users
            SET is_active = 0,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE user_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM owner_accounts
                  WHERE owner_accounts.user_id = users.user_id
              )
            """,
            (user_id,),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(user_id)

    def activate(self, user_id: int) -> UserSummary | None:
        """Reactivate a retained non-Owner account."""
        cursor = self._execute(
            """
            UPDATE users
            SET is_active = 1,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE user_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM owner_accounts
                  WHERE owner_accounts.user_id = users.user_id
              )
            """,
            (user_id,),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(user_id)

    def find_by_id(self, user_id: int) -> UserSummary | None:
        """Find display-safe account fields without selecting password_hash."""
        row = self._fetchone(
            f"""
            SELECT {_USER_SUMMARY_COLUMNS},
                   EXISTS (
                       SELECT 1 FROM owner_accounts
                       WHERE owner_accounts.user_id = users.user_id
                   ) AS is_owner
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )
        return self._summary_from_row(row) if row is not None else None

    def find_for_authentication(self, username: str) -> User | None:
        """Fetch an account including its hash for internal authentication."""
        row = self._fetchone(
            f"""
            SELECT {_AUTHENTICATION_COLUMNS},
                   EXISTS (
                       SELECT 1 FROM owner_accounts
                       WHERE owner_accounts.user_id = users.user_id
                   ) AS is_owner
            FROM users
            WHERE username = ?
            """,
            (username,),
        )
        return self._user_from_row(row) if row is not None else None

    def has_admin_account(self) -> bool:
        """Return whether any Admin account exists, active or inactive."""
        row = self._fetchone(
            """
            SELECT 1
            FROM users
            WHERE role = ?
                AND NOT EXISTS (
                    SELECT 1 FROM owner_accounts
                    WHERE owner_accounts.user_id = users.user_id
                )
            LIMIT 1
            """,
            (UserRole.ADMIN.value,),
        )
        return row is not None

    def search(
        self,
        username: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[UserSummary]:
        """Search accounts with bounded results that never select password_hash."""
        Page[UserSummary](limit=limit, offset=offset)
        clauses: tuple[str, ...] = ()
        parameters: tuple[SQLiteParameter, ...] = ()
        if username is not None:
            clauses += ("username = ?",)
            parameters += (username,)
        if role is not None:
            if role is UserRole.OWNER:
                clauses += (
                    "EXISTS (SELECT 1 FROM owner_accounts "
                    "WHERE owner_accounts.user_id = users.user_id)",
                )
            else:
                clauses += (
                    "role = ? AND NOT EXISTS (SELECT 1 FROM owner_accounts "
                    "WHERE owner_accounts.user_id = users.user_id)",
                )
                parameters += (role.value,)
        if is_active is not None:
            clauses += ("is_active = ?",)
            parameters += (int(is_active),)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        count_row = self._fetchone(
            f"SELECT COUNT(*) AS total_count FROM users{where_sql}",
            parameters,
        )
        total_count = int(count_row["total_count"]) if count_row is not None else 0
        rows = self._fetchall(
            f"""
            SELECT {_USER_SUMMARY_COLUMNS},
                   EXISTS (
                       SELECT 1 FROM owner_accounts
                       WHERE owner_accounts.user_id = users.user_id
                   ) AS is_owner
            FROM users{where_sql}
            ORDER BY user_id ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        )
        items = Page[UserSummary](limit=limit, offset=offset).items
        for row in rows:
            items.append(self._summary_from_row(row))
        return Page(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> UserSummary:
        return UserSummary(
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            role=(
                UserRole.OWNER
                if bool(row["is_owner"])
                else UserRole(row["role"])
            ),
            is_active=bool(row["is_active"]),
        )

    @staticmethod
    def _user_from_row(row: sqlite3.Row) -> User:
        return User(
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            role=(
                UserRole.OWNER
                if bool(row["is_owner"])
                else UserRole(row["role"])
            ),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
