"""Shared SQLite connection and error handling for repositories."""

import sqlite3
from collections.abc import Sequence

from repositories.exceptions import (
    PersistenceConflictError,
    PersistenceConstraintError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceUnavailableError,
)


SQLiteParameter = str | bytes | int | float | None


class BaseRepository:
    """Use a caller-owned SQLite connection without managing its transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def _execute(
        self,
        sql: str,
        parameters: Sequence[SQLiteParameter] = (),
    ) -> sqlite3.Cursor:
        """Execute a parameterized statement on the shared connection."""
        try:
            return self.connection.execute(sql, parameters)
        except sqlite3.Error as error:
            translated = self._translate_sqlite_error(error)
            raise translated from error

    def _fetchone(
        self,
        sql: str,
        parameters: Sequence[SQLiteParameter] = (),
    ) -> sqlite3.Row | None:
        """Fetch one row while translating SQLite failures."""
        cursor = self._execute(sql, parameters)
        try:
            return cursor.fetchone()
        except sqlite3.Error as error:
            translated = self._translate_sqlite_error(error)
            raise translated from error

    def _fetchall(
        self,
        sql: str,
        parameters: Sequence[SQLiteParameter] = (),
    ) -> tuple[sqlite3.Row, ...]:
        """Fetch all rows while translating SQLite failures."""
        cursor = self._execute(sql, parameters)
        try:
            return tuple(cursor.fetchall())
        except sqlite3.Error as error:
            translated = self._translate_sqlite_error(error)
            raise translated from error

    @staticmethod
    def _translate_sqlite_error(error: sqlite3.Error) -> PersistenceError:
        """Map known SQLite error classes while retaining the original error."""
        error_code = getattr(error, "sqlite_errorcode", None)
        primary_code = error_code & 0xFF if isinstance(error_code, int) else None

        if isinstance(error, sqlite3.IntegrityError):
            if error_code in (
                getattr(sqlite3, "SQLITE_CONSTRAINT_UNIQUE", -1),
                getattr(sqlite3, "SQLITE_CONSTRAINT_PRIMARYKEY", -1),
            ):
                return PersistenceConflictError(
                    "The operation conflicts with an existing record.",
                    original_cause=error,
                )
            return PersistenceConstraintError(
                "A database constraint rejected the operation.",
                original_cause=error,
            )

        if primary_code in {
            getattr(sqlite3, "SQLITE_BUSY", -1),
            getattr(sqlite3, "SQLITE_LOCKED", -1),
            getattr(sqlite3, "SQLITE_CANTOPEN", -1),
            getattr(sqlite3, "SQLITE_IOERR", -1),
            getattr(sqlite3, "SQLITE_READONLY", -1),
        }:
            return PersistenceUnavailableError(
                "The SQLite database is currently unavailable.",
                original_cause=error,
            )

        if primary_code in {
            getattr(sqlite3, "SQLITE_CORRUPT", -1),
            getattr(sqlite3, "SQLITE_NOTADB", -1),
        }:
            return PersistenceIntegrityError(
                "The SQLite database reported an integrity failure.",
                original_cause=error,
            )

        return PersistenceError(
            "The SQLite persistence operation failed.",
            original_cause=error,
        )
