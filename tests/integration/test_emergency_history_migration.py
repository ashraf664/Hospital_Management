"""Integration tests for the append-only emergency history migration."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from database.transaction_manager import TransactionManager


_HISTORY_TABLES = (
    "emergency_doctor_assignments",
    "emergency_triage_history",
    "emergency_outcome_versions",
    "emergency_status_history",
    "emergency_intake_history",
    "emergency_closure_versions",
)


class EmergencyHistoryMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "emergency-history.db"
        self.empty_migrations = self.root / "empty-migrations"
        self.empty_migrations.mkdir()
        self._create_version_two_database(self.database_path, self.empty_migrations)
        self.assertEqual(DatabaseInitializer(self.database_path).initialize(), 7)
        self.addCleanup(self.temporary_directory.cleanup)
        self.connection = ConnectionManager(self.database_path).connect()
        self.addCleanup(self.connection.close)

        self.user_ids = {
            row["username"]: int(row["user_id"])
            for row in self.connection.execute(
                "SELECT user_id, username FROM users"
            )
        }
        self.doctor_ids = {
            row["full_name"]: int(row["doctor_id"])
            for row in self.connection.execute(
                "SELECT doctor_id, full_name FROM doctors"
            )
        }

    @staticmethod
    def _create_version_two_database(
        database_path: Path,
        empty_migrations: Path,
    ) -> None:
        self_initializer = DatabaseInitializer(
            database_path,
            migrations_dir=empty_migrations,
        )
        if self_initializer.initialize() != 2:
            raise AssertionError("Expected the initial schema to be version 2.")

        with ConnectionManager(database_path).connection() as connection:
            connection.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('synthetic-admin', 'test-hash', 'Admin')
                """
            )
            receptionist_cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('synthetic-receptionist', 'test-hash', 'Receptionist')
                """
            )
            doctor_user_cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('synthetic-doctor', 'test-hash', 'Doctor')
                """
            )
            second_doctor_user_cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('synthetic-doctor-two', 'test-hash', 'Doctor')
                """
            )
            department_cursor = connection.execute(
                "INSERT INTO departments (name) VALUES ('Synthetic Department')"
            )
            patient_cursor = connection.execute(
                """
                INSERT INTO patients (patient_number, full_name, date_of_birth)
                VALUES ('SYNTH-ER-1', 'Synthetic Patient', '1980-01-02')
                """
            )
            doctor_cursor = connection.execute(
                """
                INSERT INTO doctors (user_id, department_id, full_name, specialty)
                VALUES (?, ?, 'Synthetic Doctor', 'General')
                """,
                (doctor_user_cursor.lastrowid, department_cursor.lastrowid),
            )
            connection.execute(
                """
                INSERT INTO doctors (user_id, department_id, full_name, specialty)
                VALUES (?, ?, 'Synthetic Doctor Two', 'General')
                """,
                (
                    second_doctor_user_cursor.lastrowid,
                    department_cursor.lastrowid,
                ),
            )
            connection.execute(
                """
                INSERT INTO emergency_cases (
                    case_number, patient_id, assigned_doctor_id, intake_user_id,
                    triage_category, status, arrival_at, closed_at, intake_notes,
                    created_at, updated_at
                )
                VALUES (
                    'ER-SYNTH-001', ?, ?, ?, 'Legacy triage value', 'In Treatment',
                    '2026-01-01T10:00:00Z', NULL,
                    'Synthetic intake note', '2026-01-01T10:00:00Z',
                    '2026-01-01T10:00:00Z'
                )
                """,
                (
                    patient_cursor.lastrowid,
                    doctor_cursor.lastrowid,
                    receptionist_cursor.lastrowid,
                ),
            )
            connection.execute(
                """
                INSERT INTO emergency_cases (
                    case_number, intake_user_id, status, arrival_at,
                    closed_at, created_at, updated_at
                )
                VALUES (
                    'ER-SYNTH-002', ?, 'Closed', '2026-02-01T09:00:00Z',
                    '2026-02-01T10:00:00Z',
                    '2026-02-01T09:00:00Z', '2026-02-01T09:00:00Z'
                )
                """,
                (receptionist_cursor.lastrowid,),
            )

    def _insert_audit_log(self, username: str = "synthetic-doctor") -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO audit_logs (
                user_id, actor_type, action, entity_type, entity_id, details
            )
            VALUES (?, 'user', 'emergency update', 'emergency_case', '1', '')
            """,
            (self.user_ids[username],),
        )
        return int(cursor.lastrowid)

    def _insert_doctor_intake_update(
        self,
        username: str,
        version_no: int,
        previous_notes: str,
        updated_notes: str,
        event_type: str = "intake_updated",
    ) -> None:
        audit_log_id = self._insert_audit_log(username)
        self.connection.execute(
            """
            INSERT INTO emergency_intake_history (
                emergency_case_id, version_no, previous_case_number_snapshot,
                case_number_snapshot, previous_patient_id_snapshot,
                patient_id_snapshot, previous_intake_user_id_snapshot,
                intake_user_id_snapshot, previous_arrival_at_snapshot,
                arrival_at_snapshot, intake_notes_snapshot,
                previous_intake_notes_snapshot, event_type, change_reason,
                record_origin, event_at, actor_user_id, audit_log_id
            )
            VALUES (
                1, ?, 'ER-SYNTH-001', 'ER-SYNTH-001', 1, 1, ?, ?,
                '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z', ?, ?,
                ?, 'Synthetic doctor correction',
                'application_event', '2026-03-01T11:00:00Z', ?, ?
            )
            """,
            (
                version_no,
                self.user_ids["synthetic-receptionist"],
                self.user_ids["synthetic-receptionist"],
                updated_notes,
                previous_notes,
                event_type,
                self.user_ids[username],
                audit_log_id,
            ),
        )

    def test_only_active_current_doctor_can_update_intake_notes(self) -> None:
        self._insert_doctor_intake_update(
            "synthetic-doctor",
            2,
            "Synthetic intake note",
            "Synthetic doctor correction",
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT intake_notes FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "Synthetic doctor correction",
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_doctor_intake_update(
                "synthetic-doctor-two",
                3,
                "Synthetic doctor correction",
                "Rejected non-assigned correction",
            )

        self.connection.execute(
            "UPDATE doctors SET is_active = 0 WHERE doctor_id = ?",
            (self.doctor_ids["Synthetic Doctor"],),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_doctor_intake_update(
                "synthetic-doctor",
                3,
                "Synthetic doctor correction",
                "Rejected inactive-profile correction",
            )
        self.connection.execute(
            "UPDATE doctors SET is_active = 1 WHERE doctor_id = ?",
            (self.doctor_ids["Synthetic Doctor"],),
        )

        self.connection.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (self.user_ids["synthetic-doctor"],),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_doctor_intake_update(
                "synthetic-doctor",
                3,
                "Synthetic doctor correction",
                "Rejected inactive-account correction",
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT intake_notes FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "Synthetic doctor correction",
        )

    def test_closed_case_rejects_direct_intake_update_atomically(self) -> None:
        self._close_case()
        history_count = self.connection.execute(
            """
            SELECT COUNT(*) FROM emergency_intake_history
            WHERE emergency_case_id = 1
            """
        ).fetchone()[0]
        audit_count = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]
        for username, event_type in (
            ("synthetic-doctor", "intake_updated"),
            ("synthetic-admin", "patient_linked"),
        ):
            with self.subTest(username=username, event_type=event_type):
                with self.assertRaises(sqlite3.IntegrityError):
                    with TransactionManager(self.connection).transaction():
                        self._insert_doctor_intake_update(
                            username,
                            2,
                            "Synthetic intake note",
                            "Rejected closed-case update",
                            event_type,
                        )
                self.assertEqual(
                    self.connection.execute(
                        "SELECT intake_notes FROM emergency_cases "
                        "WHERE emergency_case_id = 1"
                    ).fetchone()[0],
                    "Synthetic intake note",
                )
                self.assertEqual(
                    self.connection.execute(
                        """
                        SELECT COUNT(*) FROM emergency_intake_history
                        WHERE emergency_case_id = 1
                        """
                    ).fetchone()[0],
                    history_count,
                )
                self.assertEqual(
                    self.connection.execute(
                        "SELECT COUNT(*) FROM audit_logs"
                    ).fetchone()[0],
                    audit_count,
                )

    def _close_case(
        self,
        *,
        case_id: int = 1,
        doctor_username: str = "synthetic-doctor",
        sequence_no: int = 1,
    ) -> int:
        audit_log_id = self._insert_audit_log(doctor_username)
        event_at = f"2026-03-01T10:{sequence_no:02d}:00Z"
        self.connection.execute(
            """
            INSERT INTO emergency_closure_versions (
                emergency_case_id, closure_cycle, version_no, closure_type,
                closed_at_snapshot, closed_by_user_id, closure_summary,
                record_origin, event_at, actor_user_id, audit_log_id
            )
            VALUES (?, 1, 1, 'closed', ?, ?, 'Synthetic closure summary',
                    'application_event', ?, ?, ?)
            """,
            (
                case_id,
                event_at,
                self.user_ids[doctor_username],
                event_at,
                self.user_ids[doctor_username],
                audit_log_id,
            ),
        )
        self.connection.execute(
            """
            INSERT INTO emergency_status_history (
                emergency_case_id, sequence_no, previous_status, new_status,
                transition_type, record_origin, event_at, actor_user_id,
                audit_log_id
            )
            VALUES (?, 2, 'In Treatment', 'Closed', 'status_changed',
                    'application_event', ?, ?, ?)
            """,
            (
                case_id,
                event_at,
                self.user_ids[doctor_username],
                audit_log_id,
            ),
        )
        return audit_log_id

    def _reopen_case(self, case_id: int = 1) -> int:
        audit_log_id = self._insert_audit_log("synthetic-admin")
        status_sequence = int(
            self.connection.execute(
                """
                SELECT MAX(sequence_no) + 1
                FROM emergency_status_history
                WHERE emergency_case_id = ?
                """,
                (case_id,),
            ).fetchone()[0]
        )
        self.connection.execute(
            """
            INSERT INTO emergency_status_history (
                emergency_case_id, sequence_no, previous_status, new_status,
                transition_type, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (?, ?, 'Closed', 'Open', 'reopened',
                    'Synthetic reopen reason', 'application_event',
                    '2026-03-01T12:00:00Z', ?, ?)
            """,
            (
                case_id,
                status_sequence,
                self.user_ids["synthetic-admin"],
                audit_log_id,
            ),
        )
        return audit_log_id

    def test_migration_preserves_current_data_and_marks_only_baselines(self) -> None:
        case_rows = self.connection.execute(
            """
            SELECT case_number, patient_id, assigned_doctor_id, intake_user_id,
                   triage_category, status, arrival_at, closed_at, intake_notes
            FROM emergency_cases
            ORDER BY emergency_case_id
            """
        ).fetchall()
        self.assertEqual(len(case_rows), 2)

        for table_name in _HISTORY_TABLES:
            expected_baselines = {
                "emergency_doctor_assignments": 2,
                "emergency_triage_history": 2,
                "emergency_outcome_versions": 0,
                "emergency_status_history": 2,
                "emergency_intake_history": 2,
                "emergency_closure_versions": 1,
            }
            self.assertEqual(
                self.connection.execute(
                    f"SELECT COUNT(*) FROM {table_name} "
                    "WHERE record_origin = 'migration_baseline'"
                ).fetchone()[0],
                expected_baselines[table_name],
            )
            self.assertEqual(
                self.connection.execute(
                    f"SELECT COUNT(*) FROM {table_name} "
                    "WHERE record_origin = 'application_event'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                self.connection.execute(
                    f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE record_origin = 'migration_baseline'
                      AND (
                          event_at IS NOT NULL
                          OR actor_user_id IS NOT NULL
                          OR audit_log_id IS NOT NULL
                      )
                    """
                ).fetchone()[0],
                0,
            )

        legacy_assignment = self.connection.execute(
            """
            SELECT previous_doctor_id, new_doctor_id, change_reason
            FROM emergency_doctor_assignments
            WHERE emergency_case_id = 1
            """
        ).fetchone()
        self.assertIsNone(legacy_assignment["previous_doctor_id"])
        self.assertEqual(
            legacy_assignment["new_doctor_id"],
            self.doctor_ids["Synthetic Doctor"],
        )
        self.assertIsNone(legacy_assignment["change_reason"])
        self.assertEqual(
            self.connection.execute(
                """
                SELECT new_triage_category FROM emergency_triage_history
                WHERE emergency_case_id = 1
                """
            ).fetchone()[0],
            "Legacy triage value",
        )
        self.assertIsNone(
            self.connection.execute(
                "SELECT 1 FROM emergency_outcome_versions LIMIT 1"
            ).fetchone()
        )
        closure = self.connection.execute(
            """
            SELECT closure_summary, closed_by_user_id
            FROM emergency_closure_versions
            """
        ).fetchone()
        self.assertIsNone(closure["closure_summary"])
        self.assertIsNone(closure["closed_by_user_id"])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            0,
        )
        self.assertEqual(
            [tuple(row) for row in self.connection.execute(
                """
                SELECT case_number, patient_id, assigned_doctor_id, intake_user_id,
                       triage_category, status, arrival_at, closed_at, intake_notes
                FROM emergency_cases
                ORDER BY emergency_case_id
                """
            ).fetchall()],
            [tuple(row) for row in case_rows],
        )

    def test_migration_0007_preserves_existing_version_six_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = root / "version-six.db"
            empty_migrations = root / "empty-migrations"
            version_six_migrations = root / "version-six-migrations"
            empty_migrations.mkdir()
            version_six_migrations.mkdir()
            self._create_version_two_database(database_path, empty_migrations)

            source_migrations = (
                Path(__file__).resolve().parents[2] / "database" / "migrations"
            )
            for version in range(3, 7):
                source_path = next(
                    source_migrations.glob(f"{version:04d}_*.sql")
                )
                (version_six_migrations / source_path.name).write_text(
                    source_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )

            self.assertEqual(
                DatabaseInitializer(
                    database_path,
                    migrations_dir=version_six_migrations,
                ).initialize(),
                6,
            )
            with ConnectionManager(database_path).connection() as connection:
                history_before = {
                    table_name: [
                        tuple(row)
                        for row in connection.execute(
                            f"SELECT * FROM {table_name} ORDER BY rowid"
                        )
                    ]
                    for table_name in _HISTORY_TABLES
                }

            self.assertEqual(DatabaseInitializer(database_path).initialize(), 7)
            with ConnectionManager(database_path).connection() as connection:
                history_after = {
                    table_name: [
                        tuple(row)
                        for row in connection.execute(
                            f"SELECT * FROM {table_name} ORDER BY rowid"
                        )
                    ]
                    for table_name in _HISTORY_TABLES
                }
            self.assertEqual(history_after, history_before)

    def test_triage_and_outcome_values_and_other_explanation_are_constrained(
        self,
    ) -> None:
        accepted_triage_audit_id = self._insert_audit_log()
        self.connection.execute(
            """
            INSERT INTO emergency_triage_history (
                emergency_case_id, sequence_no, previous_triage_category,
                new_triage_category, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (1, 2, 'Legacy triage value', 'RED', 'Synthetic triage reason',
                    'application_event', '2026-03-01T10:00:00Z', ?, ?)
            """,
            (
                self.user_ids["synthetic-doctor"],
                accepted_triage_audit_id,
            ),
        )

        audit_log_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_triage_history (
                    emergency_case_id, sequence_no, previous_triage_category,
                    new_triage_category, change_reason, record_origin, event_at,
                    actor_user_id, audit_log_id
                )
                VALUES (1, 3, 'RED', 'PURPLE', 'Reason',
                        'application_event', '2026-03-01T10:00:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-doctor"], audit_log_id),
            )

        first_audit_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_outcome_versions (
                    emergency_case_id, version_no, outcome_code,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (1, 1, 'Other', 'application_event',
                        '2026-03-01T10:00:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-doctor"], first_audit_id),
            )

        accepted_outcomes = (
            "Discharged",
            "Admitted",
            "Transferred",
            "Referred",
            "Deceased",
            "Other",
        )
        previous_outcome_version_id = None
        for version_no, outcome_code in enumerate(accepted_outcomes, start=1):
            audit_id = self._insert_audit_log()
            explanation = (
                "Synthetic explanation" if outcome_code == "Other" else None
            )
            cursor = self.connection.execute(
                """
                INSERT INTO emergency_outcome_versions (
                    emergency_case_id, version_no, outcome_code,
                    outcome_explanation, supersedes_version_id, record_origin,
                    event_at, actor_user_id, audit_log_id
                )
                VALUES (1, ?, ?, ?, ?, 'application_event',
                        '2026-03-01T10:00:00Z', ?, ?)
                """,
                (
                    version_no,
                    outcome_code,
                    explanation,
                    previous_outcome_version_id,
                    self.user_ids["synthetic-doctor"],
                    audit_id,
                ),
            )
            previous_outcome_version_id = int(cursor.lastrowid)

        third_audit_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_outcome_versions (
                    emergency_case_id, version_no, outcome_code,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (1, 7, 'Unknown', 'application_event',
                        '2026-03-01T10:01:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-doctor"], third_audit_id),
            )

    def test_assignment_reopen_intake_and_closure_requirements_are_constrained(
        self,
    ) -> None:
        audit_log_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_doctor_assignments (
                    emergency_case_id, sequence_no, previous_doctor_id,
                    new_doctor_id, change_reason, record_origin, event_at,
                    actor_user_id, audit_log_id
                )
                VALUES (1, 2, ?, ?, '', 'application_event',
                        '2026-03-01T10:00:00Z', ?, ?)
                """,
                (
                    self.doctor_ids["Synthetic Doctor"],
                    self.doctor_ids["Synthetic Doctor Two"],
                    self.user_ids["synthetic-admin"],
                    audit_log_id,
                ),
            )

        reopen_audit_id = self._insert_audit_log("synthetic-admin")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_status_history (
                    emergency_case_id, sequence_no, previous_status, new_status,
                    transition_type, record_origin, event_at, actor_user_id,
                    audit_log_id
                )
                VALUES (1, 2, 'Closed', 'Open', 'reopened',
                        'application_event', '2026-03-01T10:00:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-admin"], reopen_audit_id),
            )

        intake_audit_id = self._insert_audit_log("synthetic-receptionist")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_intake_history (
                    emergency_case_id, version_no, case_number_snapshot,
                    patient_id_snapshot, intake_user_id_snapshot,
                    arrival_at_snapshot, intake_notes_snapshot, event_type,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (1, 2, 'ER-SYNTH-001', 1, ?, '2026-01-01T10:00:00Z',
                        'Synthetic change', 'intake_updated',
                        'application_event', '2026-03-01T10:00:00Z', ?, ?)
                """,
                (
                    self.user_ids["synthetic-receptionist"],
                    self.user_ids["synthetic-receptionist"],
                    intake_audit_id,
                ),
            )

        closure_audit_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_closure_versions (
                    emergency_case_id, closure_cycle, version_no, closure_type,
                    closed_at_snapshot, closed_by_user_id, record_origin,
                    event_at, actor_user_id, audit_log_id
                )
                VALUES (2, 1, 1, 'closed', '2026-03-01T10:00:00Z', ?,
                        'application_event', '2026-03-01T10:00:00Z', ?, ?)
                """,
                (
                    self.user_ids["synthetic-doctor"],
                    self.user_ids["synthetic-doctor"],
                    closure_audit_id,
                ),
            )

    def test_foreign_keys_and_history_are_append_only(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_intake_history (
                    emergency_case_id, version_no, case_number_snapshot,
                    intake_user_id_snapshot, arrival_at_snapshot,
                    intake_notes_snapshot, event_type, record_origin
                )
                VALUES (9999, 1, 'ER-ORPHAN', ?, '2026-03-01T10:00:00Z',
                        '', 'migration_baseline', 'migration_baseline')
                """,
                (self.user_ids["synthetic-receptionist"],),
            )

        for table_name, primary_key in (
            ("emergency_doctor_assignments", "assignment_event_id"),
            ("emergency_triage_history", "triage_history_id"),
            ("emergency_status_history", "status_history_id"),
            ("emergency_intake_history", "intake_history_id"),
            ("emergency_closure_versions", "closure_version_id"),
        ):
            row_id = self.connection.execute(
                f"SELECT {primary_key} FROM {table_name} LIMIT 1"
            ).fetchone()[0]
            with self.subTest(table=table_name, operation="update"):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(
                        f"UPDATE {table_name} SET {primary_key} = {primary_key} "
                        f"WHERE {primary_key} = ?",
                        (row_id,),
                    )
            with self.subTest(table=table_name, operation="delete"):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(
                        f"DELETE FROM {table_name} WHERE {primary_key} = ?",
                        (row_id,),
                    )

        outcome_audit_id = self._insert_audit_log()
        self.connection.execute(
            """
            INSERT INTO emergency_outcome_versions (
                emergency_case_id, version_no, outcome_code, record_origin,
                event_at, actor_user_id, audit_log_id
            )
            VALUES (1, 1, 'Discharged', 'application_event',
                    '2026-03-01T10:00:00Z', ?, ?)
            """,
            (self.user_ids["synthetic-doctor"], outcome_audit_id),
        )
        outcome_id = self.connection.execute(
            "SELECT outcome_version_id FROM emergency_outcome_versions"
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_outcome_versions
                SET outcome_code = 'Admitted'
                WHERE outcome_version_id = ?
                """,
                (outcome_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "DELETE FROM emergency_outcome_versions WHERE outcome_version_id = ?",
                (outcome_id,),
            )

    def test_reassignment_and_audit_roll_back_together_on_failure(self) -> None:
        audit_count = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]
        history_count = self.connection.execute(
            "SELECT COUNT(*) FROM emergency_doctor_assignments"
        ).fetchone()[0]
        transaction_manager = TransactionManager(self.connection)

        with self.assertRaises(sqlite3.IntegrityError):
            with transaction_manager.transaction("IMMEDIATE"):
                audit_log_id = self._insert_audit_log("synthetic-admin")
                self.connection.execute(
                    """
                    INSERT INTO emergency_doctor_assignments (
                        emergency_case_id, sequence_no, previous_doctor_id,
                        new_doctor_id, change_reason, record_origin, event_at,
                        actor_user_id, audit_log_id
                    )
                    VALUES (1, 2, ?, ?, 'Synthetic reassignment reason',
                            'application_event', '2026-03-01T10:00:00Z', ?, ?)
                    """,
                    (
                        self.doctor_ids["Synthetic Doctor"],
                        self.doctor_ids["Synthetic Doctor Two"],
                        self.user_ids["synthetic-admin"],
                        audit_log_id,
                    ),
                )
                triage_audit_id = self._insert_audit_log("synthetic-doctor")
                self.connection.execute(
                    """
                    INSERT INTO emergency_triage_history (
                        emergency_case_id, sequence_no, new_triage_category,
                        change_reason, record_origin, event_at, actor_user_id,
                        audit_log_id
                    )
                    VALUES (1, 2, 'PURPLE', 'Synthetic invalid update',
                            'application_event', '2026-03-01T10:00:00Z', ?, ?)
                    """,
                    (self.user_ids["synthetic-doctor"], triage_audit_id),
                )

        self.assertEqual(
            self.connection.execute(
                """
                SELECT assigned_doctor_id FROM emergency_cases
                WHERE emergency_case_id = 1
                """
            ).fetchone()[0],
            self.doctor_ids["Synthetic Doctor"],
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM emergency_doctor_assignments"
            ).fetchone()[0],
            history_count,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            audit_count,
        )

    def test_assignment_event_changes_doctor_without_a_gap(self) -> None:
        audit_log_id = self._insert_audit_log("synthetic-admin")
        self.connection.execute(
            """
            INSERT INTO emergency_doctor_assignments (
                emergency_case_id, sequence_no, previous_doctor_id,
                new_doctor_id, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (1, 2, ?, ?, 'Synthetic reassignment reason',
                    'application_event', '2026-03-01T10:00:00Z', ?, ?)
            """,
            (
                self.doctor_ids["Synthetic Doctor"],
                self.doctor_ids["Synthetic Doctor Two"],
                self.user_ids["synthetic-admin"],
                audit_log_id,
            ),
        )
        self.assertEqual(
            self.connection.execute(
                """
                SELECT assigned_doctor_id FROM emergency_cases
                WHERE emergency_case_id = 1
                """
            ).fetchone()[0],
            self.doctor_ids["Synthetic Doctor Two"],
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET assigned_doctor_id = ?
                WHERE emergency_case_id = 1
                """,
                (self.doctor_ids["Synthetic Doctor"],),
            )

    def test_assignment_cannot_be_changed_directly_or_by_a_stale_event(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET assigned_doctor_id = ?
                WHERE emergency_case_id = 1
                """,
                (self.doctor_ids["Synthetic Doctor Two"],),
            )

        self.assertEqual(
            self.connection.execute(
                """
                SELECT assigned_doctor_id FROM emergency_cases
                WHERE emergency_case_id = 1
                """
            ).fetchone()[0],
            self.doctor_ids["Synthetic Doctor"],
        )

        first_audit_id = self._insert_audit_log("synthetic-admin")
        self.connection.execute(
            """
            INSERT INTO emergency_doctor_assignments (
                emergency_case_id, sequence_no, previous_doctor_id,
                new_doctor_id, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (1, 2, ?, ?, 'Synthetic reassignment', 'application_event',
                    '2026-03-01T10:00:00Z', ?, ?)
            """,
            (
                self.doctor_ids["Synthetic Doctor"],
                self.doctor_ids["Synthetic Doctor Two"],
                self.user_ids["synthetic-admin"],
                first_audit_id,
            ),
        )
        second_audit_id = self._insert_audit_log("synthetic-receptionist")
        self.connection.execute(
            """
            INSERT INTO emergency_doctor_assignments (
                emergency_case_id, sequence_no, previous_doctor_id,
                new_doctor_id, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (1, 3, ?, ?, 'Synthetic return assignment',
                    'application_event', '2026-03-01T10:01:00Z', ?, ?)
            """,
            (
                self.doctor_ids["Synthetic Doctor Two"],
                self.doctor_ids["Synthetic Doctor"],
                self.user_ids["synthetic-receptionist"],
                second_audit_id,
            ),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET assigned_doctor_id = ?
                WHERE emergency_case_id = 1
                """,
                (self.doctor_ids["Synthetic Doctor Two"],),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET assigned_doctor_id = NULL
                WHERE emergency_case_id = 1
                """
            )

    def test_status_transitions_are_role_and_state_guarded(self) -> None:
        doctor_id = self.user_ids["synthetic-doctor"]
        audit_log_id = self._insert_audit_log()
        self.connection.execute(
            """
            INSERT INTO emergency_status_history (
                emergency_case_id, sequence_no, previous_status, new_status,
                transition_type, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (1, 2, 'In Treatment', 'Open', 'status_changed',
                    'Synthetic doctor reason', 'application_event',
                    '2026-03-01T10:00:00Z', ?, ?)
            """,
            (doctor_id, audit_log_id),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "Open",
        )
        second_audit_id = self._insert_audit_log()
        self.connection.execute(
            """
            INSERT INTO emergency_status_history (
                emergency_case_id, sequence_no, previous_status, new_status,
                transition_type, record_origin, event_at, actor_user_id,
                audit_log_id
            )
            VALUES (1, 3, 'Open', 'In Treatment', 'status_changed',
                    'application_event', '2026-03-01T10:01:00Z', ?, ?)
            """,
            (doctor_id, second_audit_id),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "In Treatment",
        )

        no_reason_audit_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_status_history (
                    emergency_case_id, sequence_no, previous_status, new_status,
                    transition_type, record_origin, event_at, actor_user_id,
                    audit_log_id
                )
                VALUES (1, 4, 'In Treatment', 'Open', 'status_changed',
                        'application_event', '2026-03-01T10:02:00Z', ?, ?)
                """,
                (doctor_id, no_reason_audit_id),
            )

        receptionist_audit_id = self._insert_audit_log("synthetic-receptionist")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_status_history (
                    emergency_case_id, sequence_no, previous_status, new_status,
                    transition_type, record_origin, event_at, actor_user_id,
                    audit_log_id
                )
                VALUES (1, 4, 'In Treatment', 'Open', 'status_changed',
                        'application_event', '2026-03-01T10:02:00Z', ?, ?)
                """,
                (
                    self.user_ids["synthetic-receptionist"],
                    receptionist_audit_id,
                ),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET status = 'Closed'
                WHERE emergency_case_id = 1
                """
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT status FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "In Treatment",
        )

    def test_outcome_requires_open_case_current_doctor_and_next_version(
        self,
    ) -> None:
        self._close_case()
        closed_audit_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_outcome_versions (
                    emergency_case_id, version_no, outcome_code,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (1, 1, 'Discharged', 'application_event',
                        '2026-03-01T11:00:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-doctor"], closed_audit_id),
            )
        self._reopen_case()

        outcome_audit_id = self._insert_audit_log()
        outcome_cursor = self.connection.execute(
            """
            INSERT INTO emergency_outcome_versions (
                emergency_case_id, version_no, outcome_code, record_origin,
                event_at, actor_user_id, audit_log_id
            )
            VALUES (1, 1, 'Discharged', 'application_event',
                    '2026-03-01T12:01:00Z', ?, ?)
            """,
            (
                self.user_ids["synthetic-doctor"],
                outcome_audit_id,
            ),
        )
        previous_outcome_version_id = int(outcome_cursor.lastrowid)

        self.connection.execute(
            "UPDATE doctors SET is_active = 0 WHERE doctor_id = ?",
            (self.doctor_ids["Synthetic Doctor"],),
        )
        inactive_audit_id = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_outcome_versions (
                    emergency_case_id, version_no, outcome_code,
                    supersedes_version_id, record_origin, event_at,
                    actor_user_id, audit_log_id
                )
                VALUES (1, 2, 'Discharged', ?, 'application_event',
                        '2026-03-01T12:01:00Z', ?, ?)
                """,
                (
                    previous_outcome_version_id,
                    self.user_ids["synthetic-doctor"],
                    inactive_audit_id,
                ),
            )

    def test_previous_doctor_cannot_amend_outcome_or_closure(self) -> None:
        reassignment_audit_id = self._insert_audit_log("synthetic-admin")
        self.connection.execute(
            """
            INSERT INTO emergency_doctor_assignments (
                emergency_case_id, sequence_no, previous_doctor_id,
                new_doctor_id, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (1, 2, ?, ?, 'Synthetic reassignment', 'application_event',
                    '2026-03-01T10:00:00Z', ?, ?)
            """,
            (
                self.doctor_ids["Synthetic Doctor"],
                self.doctor_ids["Synthetic Doctor Two"],
                self.user_ids["synthetic-admin"],
                reassignment_audit_id,
            ),
        )
        outcome_audit_id = self._insert_audit_log("synthetic-doctor")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_outcome_versions (
                    emergency_case_id, version_no, outcome_code,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (1, 1, 'Discharged', 'application_event',
                        '2026-03-01T10:01:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-doctor"], outcome_audit_id),
            )

        closure_audit_id = self._insert_audit_log("synthetic-doctor")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_closure_versions (
                    emergency_case_id, closure_cycle, version_no, closure_type,
                    closed_at_snapshot, closed_by_user_id, closure_summary,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (1, 1, 1, 'closed', '2026-03-01T10:02:00Z', ?,
                        'Synthetic closure', 'application_event',
                        '2026-03-01T10:02:00Z', ?, ?)
                """,
                (
                    self.user_ids["synthetic-doctor"],
                    self.user_ids["synthetic-doctor"],
                    closure_audit_id,
                ),
            )

    def test_closure_and_correction_require_valid_state_and_doctor(self) -> None:
        self._close_case()
        original_closure_version_id = int(
            self.connection.execute(
                """
                SELECT closure_version_id
                FROM emergency_closure_versions
                WHERE emergency_case_id = 1
                """
            ).fetchone()[0]
        )
        current_case = self.connection.execute(
            """
            SELECT status, closed_at FROM emergency_cases
            WHERE emergency_case_id = 1
            """
        ).fetchone()
        self.assertEqual(current_case["status"], "Closed")
        self.assertEqual(current_case["closed_at"], "2026-03-01T10:01:00Z")

        closed_correction_audit = self._insert_audit_log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_closure_versions (
                    emergency_case_id, closure_cycle, version_no, closure_type,
                    closed_at_snapshot, closed_by_user_id, closure_summary,
                    supersedes_version_id, correction_reason, record_origin,
                    event_at, actor_user_id, audit_log_id
                )
                VALUES (
                    1, 1, 2, 'corrected', '2026-03-01T10:01:00Z', ?,
                    'Corrected synthetic summary', ?, 'Correction reason',
                    'application_event', '2026-03-01T10:01:00Z', ?, ?
                )
                """,
                (
                    self.user_ids["synthetic-doctor"],
                    original_closure_version_id,
                    self.user_ids["synthetic-doctor"],
                    closed_correction_audit,
                ),
            )

        self._reopen_case()
        correction_audit = self._insert_audit_log()
        self.connection.execute(
            """
            INSERT INTO emergency_closure_versions (
                emergency_case_id, closure_cycle, version_no, closure_type,
                closed_at_snapshot, closed_by_user_id, closure_summary,
                supersedes_version_id, correction_reason, record_origin,
                event_at, actor_user_id, audit_log_id
            )
            VALUES (
                1, 1, 2, 'corrected', '2026-03-01T10:01:00Z', ?,
                'Corrected synthetic summary', ?, 'Correction reason',
                'application_event', '2026-03-01T10:01:00Z', ?, ?
            )
            """,
            (
                self.user_ids["synthetic-doctor"],
                original_closure_version_id,
                self.user_ids["synthetic-doctor"],
                correction_audit,
            ),
        )
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM emergency_closure_versions
                WHERE emergency_case_id = 1
            """
            ).fetchone()[0],
            2,
        )
        self.assertIsNone(
            self.connection.execute(
                """
                SELECT closed_at FROM emergency_cases WHERE emergency_case_id = 1
                """
            ).fetchone()[0]
        )

    def test_intake_history_records_before_and_after_and_blocks_identity_edits(
        self,
    ) -> None:
        audit_log_id = self._insert_audit_log("synthetic-receptionist")
        self.connection.execute(
            """
            INSERT INTO emergency_intake_history (
                emergency_case_id, version_no, previous_case_number_snapshot,
                case_number_snapshot, previous_patient_id_snapshot,
                patient_id_snapshot, previous_intake_user_id_snapshot,
                intake_user_id_snapshot, previous_arrival_at_snapshot,
                arrival_at_snapshot, intake_notes_snapshot,
                previous_intake_notes_snapshot, event_type, change_reason,
                record_origin, event_at, actor_user_id, audit_log_id
            )
            VALUES (
                1, 2, 'ER-SYNTH-001', 'ER-SYNTH-001', 1, 1, ?, ?,
                '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z',
                'Updated synthetic intake', 'Synthetic intake note',
                'intake_updated', 'Synthetic correction reason',
                'application_event', '2026-03-01T10:00:00Z', ?, ?
            )
            """,
            (
                self.user_ids["synthetic-receptionist"],
                self.user_ids["synthetic-receptionist"],
                self.user_ids["synthetic-receptionist"],
                audit_log_id,
            ),
        )
        snapshot = self.connection.execute(
            """
            SELECT previous_intake_notes_snapshot, intake_notes_snapshot
            FROM emergency_intake_history
            WHERE emergency_case_id = 1 AND version_no = 2
            """
        ).fetchone()
        self.assertEqual(
            tuple(snapshot),
            ("Synthetic intake note", "Updated synthetic intake"),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT intake_notes FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "Updated synthetic intake",
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET case_number = 'ER-CHANGED'
                WHERE emergency_case_id = 1
                """
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE emergency_cases SET arrival_at = '2026-01-01T10:02:00Z'
                WHERE emergency_case_id = 1
                """
            )

        self.connection.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (self.user_ids["synthetic-receptionist"],),
        )
        inactive_audit_id = self._insert_audit_log("synthetic-admin")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO emergency_intake_history (
                    emergency_case_id, version_no, previous_case_number_snapshot,
                    case_number_snapshot, previous_patient_id_snapshot,
                    patient_id_snapshot, previous_intake_user_id_snapshot,
                    intake_user_id_snapshot, previous_arrival_at_snapshot,
                    arrival_at_snapshot, intake_notes_snapshot,
                    previous_intake_notes_snapshot, event_type, change_reason,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (
                    1, 3, 'ER-SYNTH-001', 'ER-SYNTH-001', 1, 1, ?, ?,
                    '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z',
                    'Another note', 'Updated synthetic intake',
                    'intake_updated', 'Reason', 'application_event',
                    '2026-03-01T10:01:00Z', ?, ?
                )
                """,
                (
                    self.user_ids["synthetic-receptionist"],
                    self.user_ids["synthetic-receptionist"],
                    self.user_ids["synthetic-receptionist"],
                    inactive_audit_id,
                ),
            )

        admin_audit_id = self._insert_audit_log("synthetic-admin")
        self.connection.execute(
            """
            INSERT INTO emergency_intake_history (
                emergency_case_id, version_no, previous_case_number_snapshot,
                case_number_snapshot, previous_patient_id_snapshot,
                patient_id_snapshot, previous_intake_user_id_snapshot,
                intake_user_id_snapshot, previous_arrival_at_snapshot,
                arrival_at_snapshot, intake_notes_snapshot,
                previous_intake_notes_snapshot, event_type, change_reason,
                record_origin, event_at, actor_user_id, audit_log_id
            )
            VALUES (
                1, 3, 'ER-SYNTH-001', 'ER-SYNTH-001', 1, 1, ?, ?,
                '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z',
                'Admin updated synthetic intake', 'Updated synthetic intake',
                'intake_updated', 'Synthetic admin correction',
                'application_event', '2026-03-01T10:01:00Z', ?, ?
            )
            """,
            (
                self.user_ids["synthetic-receptionist"],
                self.user_ids["synthetic-receptionist"],
                self.user_ids["synthetic-admin"],
                admin_audit_id,
            ),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT intake_notes FROM emergency_cases WHERE emergency_case_id = 1"
            ).fetchone()[0],
            "Admin updated synthetic intake",
        )

    def test_unassigned_closed_case_reopens_only_with_active_doctor_atomically(
        self,
    ) -> None:
        initial_audit_count = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]
        transaction_manager = TransactionManager(self.connection)
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction_manager.transaction("IMMEDIATE"):
                reopen_audit_id = self._insert_audit_log("synthetic-admin")
                self.connection.execute(
                    """
                    INSERT INTO emergency_status_history (
                        emergency_case_id, sequence_no, previous_status,
                        new_status, transition_type, change_reason,
                        record_origin, event_at, actor_user_id, audit_log_id
                    )
                    VALUES (2, 2, 'Closed', 'Open', 'reopened',
                            'Synthetic reopen reason', 'application_event',
                            '2026-03-01T10:00:00Z', ?, ?)
                    """,
                    (
                        self.user_ids["synthetic-admin"],
                        reopen_audit_id,
                    ),
                )
        self.assertIsNone(
            self.connection.execute(
                """
                SELECT assigned_doctor_id FROM emergency_cases
                WHERE emergency_case_id = 2
                """
            ).fetchone()[0]
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            initial_audit_count,
        )

        assignment_count = self.connection.execute(
            "SELECT COUNT(*) FROM emergency_doctor_assignments"
        ).fetchone()[0]
        status_count = self.connection.execute(
            "SELECT COUNT(*) FROM emergency_status_history"
        ).fetchone()[0]
        audit_count = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction_manager.transaction("IMMEDIATE"):
                assignment_audit_id = self._insert_audit_log("synthetic-admin")
                self.connection.execute(
                    """
                    INSERT INTO emergency_doctor_assignments (
                        emergency_case_id, sequence_no, previous_doctor_id,
                        new_doctor_id, change_reason, record_origin, event_at,
                        actor_user_id, audit_log_id
                    )
                    VALUES (2, 2, NULL, ?, 'Synthetic initial assignment',
                            'application_event',
                            '2026-03-01T10:01:00Z', ?, ?)
                    """,
                    (
                        self.doctor_ids["Synthetic Doctor"],
                        self.user_ids["synthetic-admin"],
                        assignment_audit_id,
                    ),
                )
                status_audit_id = self._insert_audit_log("synthetic-admin")
                self.connection.execute(
                    """
                    INSERT INTO emergency_status_history (
                        emergency_case_id, sequence_no, previous_status,
                        new_status, transition_type, change_reason,
                        record_origin, event_at, actor_user_id, audit_log_id
                    )
                    VALUES (2, 2, 'Closed', 'Open', 'reopened',
                            'Synthetic reopen reason', 'application_event',
                            '2026-03-01T10:01:00Z', ?, ?)
                    """,
                    (self.user_ids["synthetic-admin"], status_audit_id),
                )
                self.connection.execute(
                    """
                    UPDATE emergency_cases
                    SET status = 'Open', closed_at = NULL
                    WHERE emergency_case_id = 2
                    """
                )
                invalid_status_audit_id = self._insert_audit_log(
                    "synthetic-admin"
                )
                self.connection.execute(
                    """
                    INSERT INTO emergency_status_history (
                        emergency_case_id, sequence_no, previous_status,
                        new_status, transition_type, change_reason,
                        record_origin, event_at, actor_user_id, audit_log_id
                    )
                    VALUES (2, 3, 'Open', '', 'status_changed',
                            'Synthetic invalid status', 'application_event',
                            '2026-03-01T10:02:00Z', ?, ?)
                    """,
                    (
                        self.user_ids["synthetic-admin"],
                        invalid_status_audit_id,
                    ),
                )

        reopened_case = self.connection.execute(
            """
            SELECT assigned_doctor_id, status, closed_at
            FROM emergency_cases WHERE emergency_case_id = 2
            """
        ).fetchone()
        self.assertIsNone(reopened_case["assigned_doctor_id"])
        self.assertEqual(reopened_case["status"], "Closed")
        self.assertIsNotNone(reopened_case["closed_at"])
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM emergency_doctor_assignments"
            ).fetchone()[0],
            assignment_count,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM emergency_status_history"
            ).fetchone()[0],
            status_count,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            audit_count,
        )

        with transaction_manager.transaction("IMMEDIATE"):
            assignment_audit_id = self._insert_audit_log("synthetic-admin")
            self.connection.execute(
                """
                INSERT INTO emergency_doctor_assignments (
                    emergency_case_id, sequence_no, previous_doctor_id,
                    new_doctor_id, change_reason, record_origin, event_at,
                    actor_user_id, audit_log_id
                )
                VALUES (2, 2, NULL, ?, 'Synthetic initial assignment',
                        'application_event',
                        '2026-03-01T10:03:00Z', ?, ?)
                """,
                (
                    self.doctor_ids["Synthetic Doctor"],
                    self.user_ids["synthetic-admin"],
                    assignment_audit_id,
                ),
            )
            status_audit_id = self._insert_audit_log("synthetic-admin")
            self.connection.execute(
                """
                INSERT INTO emergency_status_history (
                    emergency_case_id, sequence_no, previous_status, new_status,
                    transition_type, change_reason, record_origin, event_at,
                    actor_user_id, audit_log_id
                )
                VALUES (2, 2, 'Closed', 'Open', 'reopened',
                        'Synthetic reopen reason', 'application_event',
                        '2026-03-01T10:03:00Z', ?, ?)
                """,
                (self.user_ids["synthetic-admin"], status_audit_id),
            )
            self.connection.execute(
                """
                UPDATE emergency_cases
                SET status = 'Open', closed_at = NULL
                WHERE emergency_case_id = 2
                """
            )
        reopened_case = self.connection.execute(
            """
            SELECT assigned_doctor_id, status, closed_at
            FROM emergency_cases WHERE emergency_case_id = 2
            """
        ).fetchone()
        self.assertEqual(
            reopened_case["assigned_doctor_id"],
            self.doctor_ids["Synthetic Doctor"],
        )
        self.assertEqual(reopened_case["status"], "Open")
        self.assertIsNone(reopened_case["closed_at"])

    def test_failed_emergency_history_migration_rolls_back_completely(self) -> None:
        database_path = self.root / "migration-rollback.db"
        empty_migrations = self.root / "rollback-empty-migrations"
        empty_migrations.mkdir()
        self._create_version_two_database(database_path, empty_migrations)
        migration_directory = self.root / "rollback-migrations"
        migration_directory.mkdir()
        source_migration = (
            Path(__file__).resolve().parents[2]
            / "database"
            / "migrations"
            / "0003_add_emergency_history.sql"
        )
        migration_content = source_migration.read_text(encoding="utf-8")
        (migration_directory / source_migration.name).write_text(
            migration_content + "\nTHIS IS NOT VALID SQL;\n",
            encoding="utf-8",
        )

        with self.assertRaises(sqlite3.OperationalError):
            DatabaseInitializer(
                database_path,
                migrations_dir=migration_directory,
            ).initialize()

        with ConnectionManager(database_path).connection() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM emergency_cases"
                ).fetchone()[0],
                2,
            )
            table_names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue(table_names.isdisjoint(_HISTORY_TABLES))
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
