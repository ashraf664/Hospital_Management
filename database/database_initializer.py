"""Versioned initialization of the local SQLite database."""

from pathlib import Path
import re
import sqlite3

from database.connection_manager import ConnectionManager
from database.transaction_manager import TransactionManager


_MIGRATION_PATTERN = re.compile(r"(?P<version>\d{4})_[a-z0-9_]+\.sql\Z")
_INITIAL_SCHEMA_VERSION = 2


class DatabaseInitializer:
    """Creates the schema and applies ordered SQL migrations atomically."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        schema_path: str | Path | None = None,
        migrations_dir: str | Path | None = None,
    ) -> None:
        self.connection_manager = ConnectionManager(database_path)
        database_directory = Path(__file__).parent
        self.schema_path = Path(schema_path or database_directory / "schema.sql")
        self.migrations_dir = Path(
            migrations_dir or database_directory / "migrations"
        )

    def initialize(self) -> int:
        """Initialize or upgrade the database and return its schema version."""
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        migrations = self._load_migrations()

        with self.connection_manager.connection() as connection:
            transaction_manager = TransactionManager(connection)
            with transaction_manager.transaction("EXCLUSIVE"):
                current_version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                latest_version = max(
                    [_INITIAL_SCHEMA_VERSION, *(version for version, _ in migrations)]
                )
                if current_version > latest_version:
                    raise RuntimeError(
                        f"Database schema version {current_version} is newer than "
                        f"the supported version {latest_version}."
                    )

                if current_version == 0:
                    self._execute_script(connection, schema_sql)
                    current_version = _INITIAL_SCHEMA_VERSION
                    connection.execute(f"PRAGMA user_version = {current_version}")

                for version, migration_sql in migrations:
                    if version <= current_version:
                        continue
                    if version != current_version + 1:
                        raise RuntimeError(
                            "Database migration versions must be contiguous; "
                            f"expected {current_version + 1}, found {version}."
                        )
                    self._execute_script(connection, migration_sql)
                    current_version = version
                    connection.execute(f"PRAGMA user_version = {current_version}")

                self._validate_database(connection)

            return current_version

    def _load_migrations(self) -> list[tuple[int, str]]:
        if not self.migrations_dir.exists():
            return []

        migrations: list[tuple[int, str]] = []
        for path in sorted(self.migrations_dir.glob("*.sql")):
            match = _MIGRATION_PATTERN.fullmatch(path.name)
            if match is None:
                raise ValueError(
                    f"Migration filename must use NNNN_name.sql format: {path.name}"
                )
            migrations.append(
                (int(match.group("version")), path.read_text(encoding="utf-8"))
            )

        versions = [version for version, _ in migrations]
        if len(versions) != len(set(versions)):
            raise ValueError("Migration version numbers must be unique.")
        return migrations

    @staticmethod
    def _execute_script(connection: sqlite3.Connection, script: str) -> None:
        """Execute complete SQL statements without executescript's implicit commit."""
        pending = ""
        for line in script.splitlines(keepends=True):
            pending += line
            if sqlite3.complete_statement(pending):
                statement = pending.strip()
                if statement:
                    connection.execute(statement)
                pending = ""

        if pending.strip():
            raise sqlite3.DatabaseError("SQL script ends with an incomplete statement.")

    @staticmethod
    def _validate_database(connection: sqlite3.Connection) -> None:
        integrity_results = [
            row[0] for row in connection.execute("PRAGMA integrity_check")
        ]
        if integrity_results != ["ok"]:
            details = "; ".join(integrity_results) or "no result returned"
            raise sqlite3.DatabaseError(
                f"SQLite integrity_check failed: {details}"
            )

        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if foreign_key_violations:
            details = "; ".join(
                f"table={row[0]}, rowid={row[1]}, parent={row[2]}, "
                f"fkid={row[3]}"
                for row in foreign_key_violations
            )
            raise sqlite3.DatabaseError(
                f"SQLite foreign_key_check failed: {details}"
            )
