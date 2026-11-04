"""Exceptions raised by the SQLite persistence layer."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base error for failures while reading or writing persisted data."""

    def __init__(
        self,
        message: str,
        *,
        original_cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.original_cause = original_cause


class PersistenceConstraintError(PersistenceError):
    """A database constraint rejected a persistence operation."""


class PersistenceConflictError(PersistenceConstraintError):
    """A write conflicts with an existing persisted record."""


class PersistenceUnavailableError(PersistenceError):
    """The database cannot currently complete the requested operation."""


class PersistenceIntegrityError(PersistenceError):
    """The database reported corruption or invalid persistent structure."""


class PersistenceTransactionError(PersistenceError):
    """A transaction could not be started, committed, or rolled back."""
