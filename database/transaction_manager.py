"""Explicit SQLite transactions with nested savepoint support."""

from contextlib import contextmanager
from itertools import count
from typing import Generator, Literal
import sqlite3


TransactionMode = Literal["DEFERRED", "IMMEDIATE", "EXCLUSIVE"]


class TransactionManager:
    """Runs atomic operations on one SQLite connection.

    A manager is intended for a single connection and must not be shared
    concurrently between threads.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._savepoint_ids = count(1)

    @contextmanager
    def transaction(
        self,
        mode: TransactionMode = "IMMEDIATE",
    ) -> Generator[sqlite3.Connection, None, None]:
        """Commit on success and roll back on every exceptional exit."""
        if mode not in ("DEFERRED", "IMMEDIATE", "EXCLUSIVE"):
            raise ValueError(f"Unsupported SQLite transaction mode: {mode!r}")

        if self.connection.in_transaction:
            with self._run_nested():
                yield self.connection
            return

        self.connection.execute(f"BEGIN {mode}")
        try:
            yield self.connection
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
        else:
            try:
                self.connection.commit()
            except BaseException:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise

    @contextmanager
    def _run_nested(self) -> Generator[None, None, None]:
        savepoint = f"hms_savepoint_{next(self._savepoint_ids)}"
        self.connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield
        except BaseException:
            self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        else:
            self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
