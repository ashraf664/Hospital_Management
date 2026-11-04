"""Integration tests for SQLite schema, constraints, and transactions."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import sqlite3
import tempfile
from threading import Barrier
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from database.transaction_manager import TransactionManager


INITIAL_SCHEMA_TABLES = {
    "users",
    "departments",
    "doctors",
    "patients",
    "doctor_patient_assignments",
    "appointments",
    "emergency_cases",
    "medical_records",
    "medical_record_versions",
    "audit_logs",
}
EMERGENCY_HISTORY_TABLES = {
    "emergency_doctor_assignments",
    "emergency_triage_history",
    "emergency_outcome_versions",
    "emergency_status_history",
    "emergency_intake_history",
    "emergency_closure_versions",
}
EXPECTED_TABLES = INITIAL_SCHEMA_TABLES | EMERGENCY_HISTORY_TABLES
SCHEMA_DEFINITION_PATTERN = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?(TABLE|INDEX|TRIGGER)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
SQL_KEYWORDS = {
    "abort",
    "action",
    "after",
    "all",
    "alter",
    "and",
    "as",
    "asc",
    "before",
    "begin",
    "between",
    "by",
    "cascade",
    "case",
    "cast",
    "check",
    "collate",
    "column",
    "commit",
    "conflict",
    "constraint",
    "create",
    "cross",
    "current_date",
    "current_time",
    "current_timestamp",
    "database",
    "default",
    "deferrable",
    "delete",
    "desc",
    "distinct",
    "drop",
    "each",
    "else",
    "end",
    "escape",
    "except",
    "exists",
    "explain",
    "fail",
    "for",
    "foreign",
    "from",
    "full",
    "glob",
    "group",
    "having",
    "if",
    "ignore",
    "immediate",
    "in",
    "index",
    "initially",
    "inner",
    "insert",
    "instead",
    "intersect",
    "into",
    "is",
    "isnull",
    "join",
    "key",
    "left",
    "like",
    "limit",
    "match",
    "natural",
    "no",
    "not",
    "notnull",
    "null",
    "of",
    "offset",
    "on",
    "or",
    "order",
    "outer",
    "plan",
    "pragma",
    "primary",
    "query",
    "raise",
    "recursive",
    "references",
    "regexp",
    "reindex",
    "release",
    "rename",
    "replace",
    "restrict",
    "right",
    "rollback",
    "row",
    "savepoint",
    "select",
    "set",
    "table",
    "temp",
    "temporary",
    "then",
    "to",
    "transaction",
    "trigger",
    "union",
    "unique",
    "update",
    "using",
    "vacuum",
    "values",
    "view",
    "when",
    "where",
    "with",
}


def normalize_sql(sql: str) -> str:
    token_pattern = re.compile(
        r"'(?:''|[^'])*'"
        r'|"(?:[^"]|"")*"'
        r"|`(?:[^`]|``)*`"
        r"|\[(?:[^\]])*\]"
        r"|--[^\r\n]*"
        r"|/\*.*?\*/"
        r"|\s+"
        r"|[A-Za-z_][A-Za-z0-9_$]*"
        r"|[0-9]+(?:\.[0-9]*)?"
        r"|<=|>=|<>|!=|==|->>|->"
        r"|.",
        re.DOTALL,
    )
    tokens = []
    for match in token_pattern.finditer(sql):
        token = match.group()
        if token.isspace() or token.startswith("--") or token.startswith("/*"):
            continue
        if token.startswith("'"):
            tokens.append(f"STRING:{token}")
        elif token.startswith('"') or token.startswith("`") or token.startswith("["):
            quote = token[0]
            identifier = token[1:-1]
            if quote == '"':
                identifier = identifier.replace('""', '"')
            elif quote == "`":
                identifier = identifier.replace("``", "`")
            tokens.append(f"IDENT:{identifier.casefold()}")
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", token):
            normalized = token.casefold()
            kind = "KEYWORD" if normalized in SQL_KEYWORDS else "IDENT"
            tokens.append(f"{kind}:{normalized}")
        else:
            tokens.append(f"SYNTAX:{token}")
    return " ".join(tokens)


def schema_snapshot(connection: sqlite3.Connection) -> dict[str, object]:
    tables: dict[str, object] = {}
    table_names = [
        row["name"]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]
    for table_name in table_names:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()["sql"]
        columns = tuple(
            tuple(row)
            for row in connection.execute(
                f'PRAGMA table_info("{table_name}")'
            ).fetchall()
        )
        foreign_keys = tuple(
            tuple(row)
            for row in connection.execute(
                f'PRAGMA foreign_key_list("{table_name}")'
            ).fetchall()
        )
        indexes = []
        for index in connection.execute(
            f'PRAGMA index_list("{table_name}")'
        ).fetchall():
            index_name = index["name"]
            index_columns = tuple(
                tuple(row)
                for row in connection.execute(
                    f'PRAGMA index_xinfo("{index_name}")'
                ).fetchall()
            )
            index_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                (index_name,),
            ).fetchone()
            index_sql = index_sql_row["sql"] if index_sql_row else None
            indexes.append(
                (
                    index_name,
                    index["unique"],
                    index["origin"],
                    index["partial"],
                    index_columns,
                    normalize_sql(index_sql) if index_sql else None,
                )
            )
        tables[table_name] = (
            normalize_sql(table_sql),
            columns,
            foreign_keys,
            tuple(sorted(indexes)),
        )

    triggers = {
        row["name"]: normalize_sql(row["sql"])
        for row in connection.execute(
            """
            SELECT name, sql FROM sqlite_master
            WHERE type = 'trigger'
            ORDER BY name
            """
        )
    }
    return {"tables": tables, "triggers": triggers}


class DatabaseFoundationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "hms_test.db"
        self.initializer = DatabaseInitializer(self.database_path)
        self.connection_manager = ConnectionManager(self.database_path)
        self.assertEqual(self.initializer.initialize(), 3)
        self.connection = self.connection_manager.connect()
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.connection.close)

    def insert_user(self, username: str, role: str) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
            """,
            (username, "test-only-hash", role),
        )
        return int(cursor.lastrowid)

    def insert_department(self, name: str = "General") -> int:
        cursor = self.connection.execute(
            "INSERT INTO departments (name) VALUES (?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def insert_doctor(self, user_id: int, department_id: int) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO doctors (user_id, department_id, full_name, specialty)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, department_id, "Synthetic Doctor", "Unspecified"),
        )
        return int(cursor.lastrowid)

    def insert_patient(self, patient_number: str = "TEST-001") -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO patients (patient_number, full_name, date_of_birth)
            VALUES (?, ?, ?)
            """,
            (patient_number, "Synthetic Patient", "1980-01-02"),
        )
        return int(cursor.lastrowid)

    def insert_assignment(
        self,
        doctor_id: int,
        patient_id: int,
        assigned_by_user_id: int,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO doctor_patient_assignments
                (doctor_id, patient_id, assigned_by_user_id)
            VALUES (?, ?, ?)
            """,
            (doctor_id, patient_id, assigned_by_user_id),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def create_v1_database(database_path: Path) -> None:
        """Build a full v1 database by reversing the changes in migration 0002."""
        empty_migrations = database_path.parent / "empty-migrations"
        empty_migrations.mkdir()
        DatabaseInitializer(
            database_path,
            migrations_dir=empty_migrations,
        ).initialize()
        legacy_emergency_table = """
        CREATE TABLE emergency_cases_v1 (
            emergency_case_id INTEGER PRIMARY KEY,
            case_number TEXT NOT NULL UNIQUE
                CHECK (length(trim(case_number)) > 0),
            patient_id INTEGER REFERENCES patients(patient_id)
                ON DELETE RESTRICT ON UPDATE RESTRICT,
            assigned_doctor_id INTEGER REFERENCES doctors(doctor_id)
                ON DELETE RESTRICT ON UPDATE RESTRICT,
            intake_user_id INTEGER NOT NULL REFERENCES users(user_id)
                ON DELETE RESTRICT ON UPDATE RESTRICT,
            triage_category TEXT,
            status TEXT NOT NULL CHECK (length(trim(status)) > 0),
            arrival_at TEXT NOT NULL,
            closed_at TEXT,
            intake_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                CHECK (length(trim(created_at)) > 0),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                CHECK (length(trim(updated_at)) > 0)
        );
        INSERT INTO emergency_cases_v1 (
            emergency_case_id, case_number, patient_id, assigned_doctor_id,
            intake_user_id, triage_category, status, arrival_at, closed_at,
            intake_notes, created_at, updated_at
        )
        SELECT
            emergency_case_id, case_number, patient_id, assigned_doctor_id,
            intake_user_id, triage_category, status, arrival_at, closed_at,
            intake_notes, created_at, updated_at
        FROM emergency_cases;
        DROP TABLE emergency_cases;
        ALTER TABLE emergency_cases_v1 RENAME TO emergency_cases;
        CREATE INDEX idx_emergency_patient_arrival
            ON emergency_cases(patient_id, arrival_at);
        CREATE INDEX idx_emergency_doctor_status
            ON emergency_cases(assigned_doctor_id, status, arrival_at);
        CREATE INDEX idx_emergency_status_arrival
            ON emergency_cases(status, arrival_at);
        CREATE TRIGGER emergency_cases_no_delete
        BEFORE DELETE ON emergency_cases
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'Emergency cases cannot be permanently deleted.');
        END;
        INSERT INTO users (username, password_hash, role)
            VALUES ('legacy-test-user', 'test-only-hash', 'Receptionist');
        INSERT INTO emergency_cases (
            case_number, intake_user_id, status, arrival_at,
            created_at, updated_at
        ) VALUES (
            'ER-LEGACY-001', 1, 'Open', '2026-01-02T00:00:00Z',
            '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z'
        );
        """
        with ConnectionManager(database_path).connection() as connection:
            with TransactionManager(connection).transaction("EXCLUSIVE"):
                for trigger_name in (
                    "users_no_delete",
                    "departments_no_delete",
                    "doctors_no_delete",
                    "patients_no_delete",
                ):
                    connection.execute(f"DROP TRIGGER {trigger_name}")
                DatabaseInitializer._execute_script(connection, legacy_emergency_table)
                connection.execute("PRAGMA user_version = 1")

    def test_initializer_creates_all_tables_and_no_default_users(self) -> None:
        tables = {
            row["name"]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertTrue(EXPECTED_TABLES.issubset(tables))
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("PRAGMA user_version").fetchone()[0],
            3,
        )

    def test_schema_has_no_duplicate_table_index_or_trigger_definitions(self) -> None:
        schema = self.initializer.schema_path.read_text(encoding="utf-8")
        definitions = [
            (kind.lower(), name.lower())
            for kind, name in SCHEMA_DEFINITION_PATTERN.findall(schema)
        ]
        self.assertTrue(definitions)
        self.assertEqual(len(definitions), len(set(definitions)))

        schema_tables = {
            name for kind, name in definitions if kind == "table"
        }
        self.assertEqual(schema_tables, INITIAL_SCHEMA_TABLES)

        for object_type in ("index", "trigger"):
            names = [
                name
                for kind, name in definitions
                if kind == object_type
            ]
            self.assertEqual(len(names), len(set(names)))

        database_objects = self.connection.execute(
            """
            SELECT type, name FROM sqlite_master
            WHERE type IN ('table', 'index', 'trigger')
                AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        object_keys = [
            (row["type"], row["name"].lower())
            for row in database_objects
        ]
        self.assertEqual(len(object_keys), len(set(object_keys)))

    def test_initializer_applies_numbered_migrations_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            migration_directory = root / "migrations"
            migration_directory.mkdir()
            (migration_directory / "0003_test_marker.sql").write_text(
                """
                CREATE TABLE migration_marker (marker_id INTEGER PRIMARY KEY);
                INSERT INTO migration_marker DEFAULT VALUES;
                """,
                encoding="utf-8",
            )
            database_path = root / "migrated.db"
            initializer = DatabaseInitializer(
                database_path,
                migrations_dir=migration_directory,
            )
            self.assertEqual(initializer.initialize(), 3)
            self.assertEqual(initializer.initialize(), 3)

            with ConnectionManager(database_path).connection() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    3,
                )
                self.assertIsNotNone(
                    connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'migration_marker'
                        """
                    ).fetchone()
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM migration_marker"
                    ).fetchone()[0],
                    1,
                )

    def test_new_and_migrated_databases_have_identical_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fresh_path = root / "fresh.db"
            legacy_path = root / "legacy.db"
            self.assertEqual(DatabaseInitializer(fresh_path).initialize(), 3)
            self.create_v1_database(legacy_path)
            migration_directory = (
                Path(__file__).resolve().parents[2] / "database" / "migrations"
            )
            self.assertEqual(
                DatabaseInitializer(
                    legacy_path,
                    migrations_dir=migration_directory,
                ).initialize(),
                3,
            )

            with (
                ConnectionManager(fresh_path).connection() as fresh_connection,
                ConnectionManager(legacy_path).connection() as migrated_connection,
            ):
                fresh_schema = schema_snapshot(fresh_connection)
                migrated_schema = schema_snapshot(migrated_connection)
                self.assertEqual(fresh_schema, migrated_schema)
                self.assertEqual(
                    set(fresh_schema["tables"]),
                    EXPECTED_TABLES,
                )
                emergency_table_sql = fresh_schema["tables"]["emergency_cases"][0]
                self.assertIn(
                    "IDENT:julianday SYNTAX:( IDENT:created_at",
                    emergency_table_sql,
                )
                self.assertIn(
                    "IDENT:julianday SYNTAX:( IDENT:updated_at",
                    emergency_table_sql,
                )
                for table_name in (
                    "users",
                    "departments",
                    "doctors",
                    "patients",
                    "emergency_cases",
                ):
                    self.assertIn(f"{table_name}_no_delete", fresh_schema["triggers"])

    def test_normalize_sql_preserves_literals_and_behavioral_differences(self) -> None:
        formatted_table = """
            CREATE TABLE "Cases" (
                "Status" TEXT CHECK ("Status" = 'Open')
            );
        """
        equivalent_table = (
            "create table cases(status text check(status='Open'));"
        )
        changed_check = (
            "create table cases(status text check(status <> 'Open'));"
        )
        self.assertEqual(
            normalize_sql(formatted_table),
            normalize_sql(equivalent_table),
        )
        self.assertNotEqual(
            normalize_sql(formatted_table),
            normalize_sql(changed_check),
        )
        self.assertNotEqual(
            normalize_sql(formatted_table),
            normalize_sql(equivalent_table.replace("'Open'", "'open'")),
        )

        formatted_trigger = """
            CREATE TRIGGER "Cases_Insert"
            BEFORE INSERT ON "Cases"
            FOR EACH ROW
            WHEN NEW."Status" = 'Open'
            BEGIN
                SELECT RAISE(ABORT, 'Case status denied');
            END;
        """
        equivalent_trigger = """
            create trigger cases_insert before insert on cases
            for each row when new.status='Open'
            begin select raise(abort,'Case status denied'); end;
        """
        changed_trigger = equivalent_trigger.replace(
            "'Case status denied'", "'Case status rejected'"
        )
        self.assertEqual(
            normalize_sql(formatted_trigger),
            normalize_sql(equivalent_trigger),
        )
        self.assertNotEqual(
            normalize_sql(formatted_trigger),
            normalize_sql(changed_trigger),
        )

    def test_failed_migration_rolls_back_schema_data_and_user_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            migration_directory = root / "migrations"
            migration_directory.mkdir()
            (migration_directory / "0003_failing_migration.sql").write_text(
                """
                CREATE TABLE migration_partial (value TEXT NOT NULL);
                INSERT INTO migration_partial (value) VALUES ('temporary');
                THIS IS NOT VALID SQL;
                """,
                encoding="utf-8",
            )
            database_path = root / "failed-migration.db"
            empty_migrations = root / "empty-migrations"
            empty_migrations.mkdir()
            DatabaseInitializer(
                database_path,
                migrations_dir=empty_migrations,
            ).initialize()
            initializer = DatabaseInitializer(
                database_path,
                migrations_dir=migration_directory,
            )

            with self.assertRaises(sqlite3.OperationalError):
                initializer.initialize()

            with ConnectionManager(database_path).connection() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    2,
                )
                self.assertIsNone(
                    connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'migration_partial'
                        """
                    ).fetchone()
                )
                self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
                connection.execute(
                    """
                    INSERT INTO patients (patient_number, full_name, date_of_birth)
                    VALUES ('AFTER-ROLLBACK', 'Synthetic Patient', '1980-01-02')
                    """
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT patient_number FROM patients
                        WHERE patient_number = 'AFTER-ROLLBACK'
                        """
                    ).fetchone()[0],
                    "AFTER-ROLLBACK",
                )

    def test_concurrent_initialization_serializes_schema_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "concurrent-legacy.db"
            self.create_v1_database(database_path)
            migration_directory = (
                Path(__file__).resolve().parents[2] / "database" / "migrations"
            )
            initializers = [
                DatabaseInitializer(
                    database_path,
                    migrations_dir=migration_directory,
                )
                for _ in range(2)
            ]
            start_together = Barrier(2)

            def initialize_after_barrier(
                initializer: DatabaseInitializer,
            ) -> int:
                start_together.wait(timeout=5)
                return initializer.initialize()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(initialize_after_barrier, initializers)
                )

            self.assertEqual(results, [3, 3])
            with ConnectionManager(database_path).connection() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    3,
                )
                migration_objects = connection.execute(
                    """
                    SELECT COUNT(*) FROM sqlite_master
                    WHERE name IN (
                        'users_no_delete', 'departments_no_delete',
                        'doctors_no_delete', 'patients_no_delete'
                    )
                    """
                ).fetchone()[0]
                self.assertEqual(migration_objects, 4)
                self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
                connection.execute(
                    """
                    INSERT INTO patients (patient_number, full_name, date_of_birth)
                    VALUES ('AFTER-ROLLBACK', 'Synthetic Patient', '1980-01-02')
                    """
                )
                self.assertEqual(
                    connection.execute(
                        "PRAGMA integrity_check"
                    ).fetchone()[0],
                    "ok",
                )

    def test_migration_version_gap_rolls_back_prior_migration_in_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            migration_directory = root / "migrations"
            migration_directory.mkdir()
            (migration_directory / "0003_valid_step.sql").write_text(
                "CREATE TABLE migration_before_gap (value TEXT);\n",
                encoding="utf-8",
            )
            (migration_directory / "0005_skipped_step.sql").write_text(
                "CREATE TABLE migration_after_gap (value TEXT);\n",
                encoding="utf-8",
            )
            database_path = root / "migration-gap.db"
            empty_migrations = root / "empty-migrations"
            empty_migrations.mkdir()
            DatabaseInitializer(
                database_path,
                migrations_dir=empty_migrations,
            ).initialize()
            initializer = DatabaseInitializer(
                database_path,
                migrations_dir=migration_directory,
            )

            with self.assertRaisesRegex(RuntimeError, "expected 4, found 5"):
                initializer.initialize()

            with ConnectionManager(database_path).connection() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    2,
                )
                self.assertIsNone(
                    connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'migration_before_gap'
                        """
                    ).fetchone()
                )
                self.assertIsNone(
                    connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'migration_after_gap'
                        """
                    ).fetchone()
                )

    def test_initializer_rejects_integrity_check_violations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "integrity-failure.db"
            initializer = DatabaseInitializer(database_path)
            initializer.initialize()

            with ConnectionManager(database_path).connection() as connection:
                connection.execute("PRAGMA ignore_check_constraints = ON")
                connection.execute(
                    """
                    INSERT INTO users (username, password_hash, role)
                    VALUES ('invalid-role', 'test-only-hash', 'Invalid')
                    """
                )

            with self.assertRaisesRegex(
                sqlite3.DatabaseError, "integrity_check failed"
            ):
                initializer.initialize()

    def test_initializer_rejects_foreign_key_check_violations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "foreign-key-failure.db"
            initializer = DatabaseInitializer(database_path)
            initializer.initialize()

            with ConnectionManager(database_path).connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (username, password_hash, role)
                    VALUES ('orphan-doctor', 'test-only-hash', 'Doctor')
                    """
                )
                user_id = int(cursor.lastrowid)
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute(
                    """
                    INSERT INTO doctors (user_id, department_id, full_name, specialty)
                    VALUES (?, 9999, 'Synthetic Doctor', 'Unspecified')
                    """,
                    (user_id,),
                )

            with self.assertRaisesRegex(
                sqlite3.DatabaseError, "foreign_key_check failed"
            ):
                initializer.initialize()

    def test_v1_database_migration_adds_delete_guards_and_emergency_timestamp_checks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "legacy.db"
            self.create_v1_database(database_path)

            migration_directory = (
                Path(__file__).resolve().parents[2] / "database" / "migrations"
            )

            initializer = DatabaseInitializer(
                database_path,
                migrations_dir=migration_directory,
            )
            with ConnectionManager(database_path).connection() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    {
                        row["name"]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        )
                    }
                    & EXPECTED_TABLES,
                    INITIAL_SCHEMA_TABLES,
                )
                legacy_emergency_sql = connection.execute(
                    """
                    SELECT sql FROM sqlite_master
                    WHERE type = 'table' AND name = 'emergency_cases'
                    """
                ).fetchone()["sql"]
                self.assertNotIn("julianday(created_at)", legacy_emergency_sql)
                self.assertIsNone(
                    connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'trigger' AND name = 'users_no_delete'
                        """
                    ).fetchone()
                )

            self.assertEqual(initializer.initialize(), 3)
            self.assertEqual(initializer.initialize(), 3)

            with ConnectionManager(database_path).connection() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    3,
                )
                trigger_names = {
                    row["name"]
                    for row in connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'trigger'
                        """
                    )
                }
                for trigger_name in (
                    "users_no_delete",
                    "departments_no_delete",
                    "doctors_no_delete",
                    "patients_no_delete",
                ):
                    self.assertIn(trigger_name, trigger_names)

                emergency_sql = connection.execute(
                    """
                    SELECT sql FROM sqlite_master
                    WHERE type = 'table' AND name = 'emergency_cases'
                    """
                ).fetchone()["sql"]
                self.assertIn("julianday(created_at)", emergency_sql)
                self.assertIn("julianday(updated_at)", emergency_sql)
                self.assertEqual(
                    tuple(
                        connection.execute(
                            """
                            SELECT case_number, created_at, updated_at
                            FROM emergency_cases
                            """
                        ).fetchone()
                    ),
                    (
                        "ER-LEGACY-001",
                        "2026-01-02T00:00:00Z",
                        "2026-01-02T00:00:00Z",
                    ),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        UPDATE emergency_cases SET updated_at = 'not-a-timestamp'
                        WHERE case_number = 'ER-LEGACY-001'
                        """
                    )

    def test_initializer_sql_parser_handles_comments_and_multiline_triggers(
        self,
    ) -> None:
        script = """
        -- Semicolons in comments must not end a statement; ;
        CREATE TABLE script_source (source_id INTEGER PRIMARY KEY);
        /* A block comment spanning lines;
           its semicolon is not SQL either. */
        CREATE TABLE script_events (message TEXT NOT NULL);
        CREATE TRIGGER script_source_after_insert
        AFTER INSERT ON script_source
        FOR EACH ROW
        BEGIN
            INSERT INTO script_events (message) VALUES ('trigger; fired');
            -- An internal comment; still part of the trigger statement.
        END;
        """
        with TransactionManager(self.connection).transaction():
            DatabaseInitializer._execute_script(self.connection, script)

        self.connection.execute("INSERT INTO script_source DEFAULT VALUES")
        self.assertEqual(
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT message FROM script_events"
                ).fetchall()
            ],
            [("trigger; fired",)],
        )

    def test_each_connection_enables_foreign_keys(self) -> None:
        second_connection = self.connection_manager.connect()
        try:
            self.assertEqual(
                second_connection.execute("PRAGMA foreign_keys").fetchone()[0],
                1,
            )
        finally:
            second_connection.close()
        self.assertEqual(
            self.connection.execute("PRAGMA foreign_keys").fetchone()[0],
            1,
        )

    def test_foreign_keys_and_role_relationship_are_enforced(self) -> None:
        foreign_keys = self.connection.execute(
            "PRAGMA foreign_key_list(doctor_patient_assignments)"
        ).fetchall()
        self.assertEqual(
            {row["table"] for row in foreign_keys},
            {"doctors", "patients", "users"},
        )

        department_id = self.insert_department()
        admin_id = self.insert_user("admin", "Admin")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_doctor(admin_id, department_id)

        doctor_user_id = self.insert_user("doctor", "Doctor")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_assignment(doctor_id, 9999, admin_id)

    def test_required_unique_check_constraints_and_indexes(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('bad-role', 'test-hash', 'Patient')
                """
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active)
                VALUES ('bad-active', 'test-hash', 'Admin', 2)
                """
            )

        self.insert_user("unique-user", "Admin")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_user("UNIQUE-USER", "Admin")

        self.insert_patient()
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_patient()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO patients (patient_number, full_name, date_of_birth)
                VALUES ('TEST-BAD-DATE', 'Synthetic Patient', '1980-13-40')
                """
            )

        indexes = {
            row["name"]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        self.assertIn("uq_assignments_active_pair", indexes)
        self.assertIn("idx_appointments_doctor_start_status", indexes)
        self.assertIn("idx_emergency_status_arrival", indexes)
        self.assertIn("idx_medical_record_versions_record_time", indexes)
        partial_index = self.connection.execute(
            "PRAGMA index_list(doctor_patient_assignments)"
        ).fetchall()
        self.assertTrue(
            any(
                row["name"] == "uq_assignments_active_pair" and row["partial"] == 1
                for row in partial_index
            )
        )

    def test_active_assignment_is_unique_and_can_be_reassigned_after_ending(self) -> None:
        department_id = self.insert_department()
        doctor_user_id = self.insert_user("doctor-assignment", "Doctor")
        admin_id = self.insert_user("assigning-admin", "Admin")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        patient_id = self.insert_patient()
        assignment_id = self.insert_assignment(doctor_id, patient_id, admin_id)

        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_assignment(doctor_id, patient_id, admin_id)

        self.connection.execute(
            """
            UPDATE doctor_patient_assignments
            SET ended_by_user_id = ?, ended_at = '2099-01-02T00:00:00Z'
            WHERE assignment_id = ?
            """,
            (admin_id, assignment_id),
        )
        new_assignment_id = self.insert_assignment(
            doctor_id,
            patient_id,
            admin_id,
        )
        self.assertNotEqual(assignment_id, new_assignment_id)
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM doctor_patient_assignments
                WHERE doctor_id = ? AND patient_id = ?
                """,
                (doctor_id, patient_id),
            ).fetchone()[0],
            2,
        )

    def test_emergency_case_can_be_created_without_a_patient(self) -> None:
        receptionist_id = self.insert_user("reception", "Receptionist")
        self.connection.execute(
            """
            INSERT INTO emergency_cases
                (case_number, patient_id, intake_user_id, status, arrival_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            ("ER-TEST-001", receptionist_id, "Open", "2026-01-02T00:00:00Z"),
        )
        row = self.connection.execute(
            "SELECT patient_id FROM emergency_cases WHERE case_number = ?",
            ("ER-TEST-001",),
        ).fetchone()
        self.assertIsNone(row["patient_id"])

    def test_emergency_created_and_updated_timestamps_validate_iso_utc(self) -> None:
        receptionist_id = self.insert_user("reception-timestamps", "Receptionist")
        cursor = self.connection.execute(
            """
            INSERT INTO emergency_cases
                (case_number, patient_id, intake_user_id, status, arrival_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (
                "ER-TIME-001",
                receptionist_id,
                "Open",
                "2026-01-02T00:00:00Z",
            ),
        )
        case_id = int(cursor.lastrowid)

        valid_timestamp = "2026-01-02T03:04:05.123Z"
        for column in ("created_at", "updated_at"):
            with self.subTest(column=column, valid_timestamp=valid_timestamp):
                self.connection.execute(
                    f"UPDATE emergency_cases SET {column} = ? "
                    "WHERE emergency_case_id = ?",
                    (valid_timestamp, case_id),
                )
                stored = self.connection.execute(
                    f"SELECT {column} FROM emergency_cases "
                    "WHERE emergency_case_id = ?",
                    (case_id,),
                ).fetchone()[0]
                self.assertEqual(stored, valid_timestamp)

            for invalid_timestamp in (
                "not-a-timestamp",
                "2026-02-30T03:04:05Z",
                "2026-01-02 03:04:05Z",
            ):
                with self.subTest(column=column, invalid_timestamp=invalid_timestamp):
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.connection.execute(
                            f"UPDATE emergency_cases SET {column} = ? "
                            "WHERE emergency_case_id = ?",
                            (invalid_timestamp, case_id),
                        )

        for column in ("created_at", "updated_at"):
            self.assertIn(
                f"julianday({column})",
                self.connection.execute(
                    """
                    SELECT sql FROM sqlite_master
                    WHERE type = 'table' AND name = 'emergency_cases'
                    """
                ).fetchone()["sql"],
            )

    def test_users_departments_doctors_and_patients_cannot_be_deleted_but_can_be_updated(self) -> None:
        admin_id = self.insert_user("protected-admin", "Admin")
        doctor_user_id = self.insert_user("protected-doctor", "Doctor")
        department_id = self.insert_department("Protected Department")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        patient_id = self.insert_patient("PROTECTED-001")

        delete_statements = (
            ("users", "user_id", admin_id),
            ("departments", "department_id", department_id),
            ("doctors", "doctor_id", doctor_id),
            ("patients", "patient_id", patient_id),
        )
        for table, primary_key, row_id in delete_statements:
            with self.subTest(table=table):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(
                        f"DELETE FROM {table} WHERE {primary_key} = ?",
                        (row_id,),
                    )

        self.connection.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (admin_id,),
        )
        self.connection.execute(
            "UPDATE departments SET name = ?, is_active = 0 WHERE department_id = ?",
            ("Renamed Protected Department", department_id),
        )
        self.connection.execute(
            "UPDATE doctors SET full_name = ?, is_active = 0 WHERE doctor_id = ?",
            ("Updated Synthetic Doctor", doctor_id),
        )
        self.connection.execute(
            """
            UPDATE patients
            SET full_name = ?, is_active = 0
            WHERE patient_id = ?
            """,
            ("Updated Synthetic Patient", patient_id),
        )

        self.assertEqual(
            self.connection.execute(
                "SELECT is_active FROM users WHERE user_id = ?", (admin_id,)
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT is_active FROM departments WHERE department_id = ?",
                (department_id,),
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT is_active FROM doctors WHERE doctor_id = ?", (doctor_id,)
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT is_active FROM patients WHERE patient_id = ?", (patient_id,)
            ).fetchone()[0],
            0,
        )

    def test_transaction_rolls_back_all_changes_on_failure(self) -> None:
        transaction_manager = TransactionManager(self.connection)
        with self.assertRaisesRegex(RuntimeError, "forced failure"):
            with transaction_manager.transaction():
                self.insert_patient("ROLLBACK-001")
                raise RuntimeError("forced failure")

        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM patients WHERE patient_number = ?",
                ("ROLLBACK-001",),
            ).fetchone()[0],
            0,
        )
        self.assertFalse(self.connection.in_transaction)

    def test_nested_transaction_uses_savepoint_without_losing_outer_work(self) -> None:
        transaction_manager = TransactionManager(self.connection)
        with transaction_manager.transaction():
            self.insert_patient("OUTER-001")
            with self.assertRaisesRegex(ValueError, "nested failure"):
                with transaction_manager.transaction():
                    self.insert_patient("INNER-001")
                    raise ValueError("nested failure")

        patient_numbers = {
            row["patient_number"]
            for row in self.connection.execute(
                "SELECT patient_number FROM patients"
            )
        }
        self.assertIn("OUTER-001", patient_numbers)
        self.assertNotIn("INNER-001", patient_numbers)

    def test_nested_transactions_rollback_at_multiple_savepoint_levels(self) -> None:
        transaction_manager = TransactionManager(self.connection)
        with transaction_manager.transaction():
            self.insert_patient("LEVEL-OUTER-001")

            with transaction_manager.transaction():
                self.insert_patient("LEVEL-ONE-001")

                with self.assertRaisesRegex(ValueError, "deepest failure"):
                    with transaction_manager.transaction():
                        self.insert_patient("LEVEL-TWO-001")
                        with transaction_manager.transaction():
                            self.insert_patient("LEVEL-THREE-ROLLBACK")
                            raise ValueError("deepest failure")

                self.insert_patient("LEVEL-ONE-AFTER-ROLLBACK")

            with self.assertRaisesRegex(RuntimeError, "middle failure"):
                with transaction_manager.transaction():
                    self.insert_patient("MIDDLE-ROLLBACK")
                    with transaction_manager.transaction():
                        self.insert_patient("INNER-ROLLBACK")
                    raise RuntimeError("middle failure")

            self.insert_patient("LEVEL-OUTER-AFTER-ROLLBACK")

        patient_numbers = {
            row["patient_number"]
            for row in self.connection.execute(
                "SELECT patient_number FROM patients"
            )
        }
        self.assertEqual(
            patient_numbers,
            {
                "LEVEL-OUTER-001",
                "LEVEL-ONE-001",
                "LEVEL-ONE-AFTER-ROLLBACK",
                "LEVEL-OUTER-AFTER-ROLLBACK",
            },
        )

    def test_audit_failure_rolls_back_record_version_and_update(self) -> None:
        department_id = self.insert_department()
        doctor_user_id = self.insert_user("doctor-version", "Doctor")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        patient_id = self.insert_patient("VERSION-001")
        record_cursor = self.connection.execute(
            """
            INSERT INTO medical_records (patient_id, doctor_id, record_type, record_content)
            VALUES (?, ?, 'test', 'original synthetic content')
            """,
            (patient_id, doctor_id),
        )
        record_id = int(record_cursor.lastrowid)

        transaction_manager = TransactionManager(self.connection)
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction_manager.transaction():
                self.connection.execute(
                    """
                    INSERT INTO medical_record_versions (
                        medical_record_id, patient_id_snapshot, doctor_id_snapshot,
                        appointment_id_snapshot, record_type_snapshot,
                        record_content_snapshot, created_at_snapshot,
                        updated_at_snapshot, is_amended_snapshot,
                        modified_by_user_id, modified_at
                    )
                    SELECT medical_record_id, patient_id, doctor_id,
                        appointment_id, record_type, record_content, created_at,
                        updated_at, is_amended, ?, '2026-01-03T00:00:00Z'
                    FROM medical_records
                    WHERE medical_record_id = ?
                    """,
                    (doctor_user_id, record_id),
                )
                self.connection.execute(
                    """
                    INSERT INTO audit_logs
                        (user_id, actor_type, action, entity_type)
                    VALUES (?, 'invalid-actor', 'record.update', 'medical_record')
                    """,
                    (doctor_user_id,),
                )
                self.connection.execute(
                    """
                    UPDATE medical_records
                    SET record_content = 'changed synthetic content',
                        updated_at = '2026-01-03T00:00:00Z',
                        is_amended = 1
                    WHERE medical_record_id = ?
                    """,
                    (record_id,),
                )

        record = self.connection.execute(
            "SELECT record_content, is_amended FROM medical_records WHERE medical_record_id = ?",
            (record_id,),
        ).fetchone()
        self.assertEqual(record["record_content"], "original synthetic content")
        self.assertEqual(record["is_amended"], 0)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM medical_record_versions WHERE medical_record_id = ?",
                (record_id,),
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM audit_logs
                WHERE entity_type = 'medical_record'
                """
            ).fetchone()[0],
            0,
        )

    def test_record_version_audit_and_record_update_commit_in_one_transaction(self) -> None:
        department_id = self.insert_department()
        doctor_user_id = self.insert_user("doctor-atomic-update", "Doctor")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        patient_id = self.insert_patient("ATOMIC-001")
        record_cursor = self.connection.execute(
            """
            INSERT INTO medical_records (patient_id, doctor_id, record_type, record_content)
            VALUES (?, ?, 'test', 'original synthetic content')
            """,
            (patient_id, doctor_id),
        )
        record_id = int(record_cursor.lastrowid)
        original_record = self.connection.execute(
            """
            SELECT medical_record_id, patient_id, doctor_id, appointment_id,
                record_type, record_content, created_at, updated_at, is_amended
            FROM medical_records
            WHERE medical_record_id = ?
            """,
            (record_id,),
        ).fetchone()

        with TransactionManager(self.connection).transaction():
            self.connection.execute(
                """
                INSERT INTO medical_record_versions (
                    medical_record_id, patient_id_snapshot, doctor_id_snapshot,
                    appointment_id_snapshot, record_type_snapshot,
                    record_content_snapshot, created_at_snapshot,
                    updated_at_snapshot, is_amended_snapshot,
                    modified_by_user_id, modified_at
                )
                SELECT medical_record_id, patient_id, doctor_id,
                    appointment_id, record_type, record_content, created_at,
                    updated_at, is_amended, ?, '2026-01-05T00:00:00Z'
                FROM medical_records
                WHERE medical_record_id = ?
                """,
                (doctor_user_id, record_id),
            )
            self.connection.execute(
                """
                INSERT INTO audit_logs
                    (user_id, actor_type, action, entity_type, entity_id)
                VALUES (?, 'user', 'record.update', 'medical_record', ?)
                """,
                (doctor_user_id, str(record_id)),
            )
            self.connection.execute(
                """
                UPDATE medical_records
                SET record_content = 'updated synthetic content',
                    updated_at = '2026-01-05T00:00:00Z',
                    is_amended = 1
                WHERE medical_record_id = ?
                """,
                (record_id,),
            )

        version = self.connection.execute(
            """
            SELECT medical_record_id, patient_id_snapshot, doctor_id_snapshot,
                appointment_id_snapshot, record_type_snapshot,
                record_content_snapshot, created_at_snapshot, updated_at_snapshot,
                is_amended_snapshot, modified_by_user_id, modified_at
            FROM medical_record_versions
            WHERE medical_record_id = ?
            """,
            (record_id,),
        ).fetchone()
        self.assertEqual(version["medical_record_id"], original_record["medical_record_id"])
        self.assertEqual(version["patient_id_snapshot"], original_record["patient_id"])
        self.assertEqual(version["doctor_id_snapshot"], original_record["doctor_id"])
        self.assertEqual(
            version["appointment_id_snapshot"], original_record["appointment_id"]
        )
        self.assertEqual(version["record_type_snapshot"], original_record["record_type"])
        self.assertEqual(
            version["record_content_snapshot"], original_record["record_content"]
        )
        self.assertEqual(
            version["created_at_snapshot"], original_record["created_at"]
        )
        self.assertEqual(
            version["updated_at_snapshot"], original_record["updated_at"]
        )
        self.assertEqual(
            version["is_amended_snapshot"], original_record["is_amended"]
        )
        self.assertEqual(version["modified_by_user_id"], doctor_user_id)
        self.assertEqual(version["modified_at"], "2026-01-05T00:00:00Z")

        updated_record = self.connection.execute(
            """
            SELECT record_content, is_amended
            FROM medical_records
            WHERE medical_record_id = ?
            """,
            (record_id,),
        ).fetchone()
        self.assertEqual(updated_record["record_content"], "updated synthetic content")
        self.assertEqual(updated_record["is_amended"], 1)

        audit_event = self.connection.execute(
            """
            SELECT action, entity_id
            FROM audit_logs
            WHERE entity_type = 'medical_record' AND entity_id = ?
            """,
            (str(record_id),),
        ).fetchone()
        self.assertIsNotNone(audit_event)
        self.assertEqual(audit_event["action"], "record.update")

    def test_first_admin_audit_can_be_atomic_without_default_credentials(self) -> None:
        transaction_manager = TransactionManager(self.connection)
        with transaction_manager.transaction():
            cursor = self.connection.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('first-admin-test', 'test-only-hash', 'Admin')
                """
            )
            user_id = int(cursor.lastrowid)
            self.connection.execute(
                """
                INSERT INTO audit_logs (user_id, actor_type, action, entity_type, entity_id)
                VALUES (NULL, 'first_admin_setup', 'account.created', 'user', ?)
                """,
                (str(user_id),),
            )

        event = self.connection.execute(
            """
            SELECT user_id, actor_type FROM audit_logs
            WHERE entity_id = ?
            """,
            (str(user_id),),
        ).fetchone()
        self.assertIsNone(event["user_id"])
        self.assertEqual(event["actor_type"], "first_admin_setup")

    def test_historical_rows_cannot_be_deleted_or_rewritten(self) -> None:
        department_id = self.insert_department()
        doctor_user_id = self.insert_user("doctor-history", "Doctor")
        admin_id = self.insert_user("admin-history", "Admin")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        patient_id = self.insert_patient("HISTORY-001")
        assignment_id = self.insert_assignment(doctor_id, patient_id, admin_id)
        record_cursor = self.connection.execute(
            """
            INSERT INTO medical_records (patient_id, doctor_id, record_type, record_content)
            VALUES (?, ?, 'test', 'synthetic history')
            """,
            (patient_id, doctor_id),
        )
        record_id = int(record_cursor.lastrowid)
        self.connection.execute(
            """
            INSERT INTO medical_record_versions (
                medical_record_id, patient_id_snapshot, doctor_id_snapshot,
                record_type_snapshot, record_content_snapshot,
                created_at_snapshot, updated_at_snapshot, is_amended_snapshot,
                modified_by_user_id, modified_at
            )
            SELECT medical_record_id, patient_id, doctor_id, record_type,
                record_content, created_at, updated_at, is_amended, ?,
                '2026-01-04T00:00:00Z'
            FROM medical_records WHERE medical_record_id = ?
            """,
            (doctor_user_id, record_id),
        )
        audit_cursor = self.connection.execute(
            """
            INSERT INTO audit_logs (user_id, actor_type, action, entity_type)
            VALUES (?, 'user', 'record.created', 'medical_record')
            """,
            (doctor_user_id,),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "DELETE FROM doctor_patient_assignments WHERE assignment_id = ?",
                (assignment_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "DELETE FROM medical_records WHERE medical_record_id = ?",
                (record_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "UPDATE medical_record_versions SET record_content_snapshot = 'rewritten' "
                "WHERE medical_record_id = ?",
                (record_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "DELETE FROM audit_logs WHERE audit_log_id = ?",
                (audit_cursor.lastrowid,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("DELETE FROM patients WHERE patient_id = ?", (patient_id,))

        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM doctor_patient_assignments WHERE assignment_id = ?",
                (assignment_id,),
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM medical_record_versions WHERE medical_record_id = ?",
                (record_id,),
            ).fetchone()[0],
            1,
        )

    def test_appointment_overlap_is_rejected_and_cancelled_slots_are_reusable(self) -> None:
        department_id = self.insert_department()
        doctor_user_id = self.insert_user("doctor-schedule", "Doctor")
        reception_id = self.insert_user("reception-schedule", "Receptionist")
        doctor_id = self.insert_doctor(doctor_user_id, department_id)
        patient_id = self.insert_patient("SCHEDULE-001")
        patient_two_id = self.insert_patient("SCHEDULE-002")

        def add_appointment(patient: int, status: str) -> None:
            self.connection.execute(
                """
                INSERT INTO appointments (
                    patient_id, doctor_id, scheduled_start, scheduled_end,
                    status, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    patient,
                    doctor_id,
                    "2026-03-01T10:00:00Z",
                    "2026-03-01T10:30:00Z",
                    status,
                    reception_id,
                ),
            )

        add_appointment(patient_id, "scheduled")
        with self.assertRaises(sqlite3.IntegrityError):
            add_appointment(patient_two_id, "scheduled")
        add_appointment(patient_two_id, "cancelled")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO appointments (
                    patient_id, doctor_id, scheduled_start, scheduled_end,
                    status, created_by_user_id
                ) VALUES (?, ?, 'not-a-timestamp', '2026-03-01T11:00:00Z',
                    'scheduled', ?)
                """,
                (patient_two_id, doctor_id, reception_id),
            )


if __name__ == "__main__":
    unittest.main()
