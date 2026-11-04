"""SQLite connection creation and per-connection safety configuration."""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator
import sqlite3


class ConnectionManager:
    """Creates configured SQLite connections for the local application."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        timeout: float = 5.0,
    ) -> None:
        self.database_path = Path(database_path)
        self.timeout = timeout

    def connect(self) -> sqlite3.Connection:
        """Open a connection with foreign-key enforcement enabled."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout,
            isolation_level=None,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)}")
            enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            if enabled != 1:
                raise sqlite3.DatabaseError(
                    "SQLite foreign-key enforcement could not be enabled."
                )
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a configured connection and always close it afterward."""
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()
