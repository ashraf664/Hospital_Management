"""SQLite-backed tests for authorized emergency-case workflows."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import EmergencyCase, Patient, User, UserRole
from repositories import (
    EmergencyCaseRepository,
    PatientRepository,
    PersistenceConstraintError,
    UserRepository,
)
from services import EmergencyCaseService


class EmergencyCaseServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "emergency.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.user_repository = UserRepository(self.connection)
        self.patient_repository = PatientRepository(self.connection)
        self.case_repository = EmergencyCaseRepository(self.connection)
        self.service = EmergencyCaseService(self.connection)
        self.admin_id = self.create_user("synthetic-admin", UserRole.ADMIN)
        self.receptionist_id = self.create_user(
            "synthetic-receptionist",
            UserRole.RECEPTIONIST,
        )
        self.patient_id = self.create_patient("SYNTH-SERVICE-001")
        self.case = self.create_case()
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.connection.close)

    def create_user(
        self,
        username: str,
        role: UserRole,
        *,
        is_active: bool = True,
    ) -> int:
        user = self.user_repository.create(
            User(
                username=username,
                password_hash=f"synthetic-hash-{username}",
                role=role,
                is_active=is_active,
            )
        )
        return user.user_id

    def create_patient(self, patient_number: str) -> int:
        patient = self.patient_repository.create(
            Patient(
                patient_number=patient_number,
                full_name="Synthetic Emergency Patient",
                date_of_birth="1980-01-02",
            )
        )
        return patient.patient_id

    def create_case(self) -> EmergencyCase:
        return self.case_repository.create(
            EmergencyCase(
                case_number="ER-SYNTH-SERVICE-001",
                intake_user_id=self.receptionist_id,
                status="Open",
                arrival_at="2030-01-02T10:00:00Z",
                intake_notes="Synthetic intake details",
            )
        )

    def audit_count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()
        return int(row[0])

    def test_link_patient_writes_case_history_and_audit_atomically(self) -> None:
        linked = self.service.link_patient(
            self.case.emergency_case_id,
            self.patient_id,
            self.receptionist_id,
            "Patient identity confirmed",
        )

        self.assertIsNotNone(linked)
        self.assertEqual(linked.patient_id, self.patient_id)
        history = self.connection.execute(
            """
            SELECT event_type, version_no, previous_case_number_snapshot,
                   case_number_snapshot, previous_patient_id_snapshot,
                   patient_id_snapshot, previous_intake_user_id_snapshot,
                   intake_user_id_snapshot, previous_arrival_at_snapshot,
                   arrival_at_snapshot, intake_notes_snapshot,
                   previous_intake_notes_snapshot, change_reason,
                   actor_user_id, audit_log_id, event_at
            FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (self.case.emergency_case_id,),
        ).fetchone()
        self.assertEqual(history["event_type"], "patient_linked")
        self.assertEqual(history["version_no"], 1)
        self.assertIsNone(history["previous_patient_id_snapshot"])
        self.assertEqual(history["patient_id_snapshot"], self.patient_id)
        self.assertEqual(history["previous_case_number_snapshot"], self.case.case_number)
        self.assertEqual(history["case_number_snapshot"], self.case.case_number)
        self.assertEqual(
            history["previous_intake_user_id_snapshot"],
            self.receptionist_id,
        )
        self.assertEqual(history["intake_user_id_snapshot"], self.receptionist_id)
        self.assertEqual(
            history["previous_arrival_at_snapshot"],
            self.case.arrival_at,
        )
        self.assertEqual(history["arrival_at_snapshot"], self.case.arrival_at)
        self.assertEqual(history["intake_notes_snapshot"], self.case.intake_notes)
        self.assertEqual(
            history["previous_intake_notes_snapshot"],
            self.case.intake_notes,
        )
        self.assertEqual(history["change_reason"], "Patient identity confirmed")
        self.assertEqual(history["actor_user_id"], self.receptionist_id)

        audit = self.connection.execute(
            """
            SELECT user_id, actor_type, action, entity_type, entity_id, occurred_at
            FROM audit_logs
            WHERE audit_log_id = ?
            """,
            (history["audit_log_id"],),
        ).fetchone()
        self.assertEqual(audit["user_id"], self.receptionist_id)
        self.assertEqual(audit["actor_type"], "user")
        self.assertEqual(audit["action"], "patient_linked")
        self.assertEqual(audit["entity_type"], "emergency_case")
        self.assertEqual(audit["entity_id"], str(self.case.emergency_case_id))
        self.assertEqual(audit["occurred_at"], history["event_at"])

    def test_doctor_and_inactive_actor_are_rejected_without_audit(self) -> None:
        doctor_id = self.create_user("synthetic-doctor", UserRole.DOCTOR)
        inactive_admin_id = self.create_user(
            "synthetic-inactive-admin",
            UserRole.ADMIN,
            is_active=False,
        )
        audit_count = self.audit_count()

        for actor_id in (doctor_id, inactive_admin_id, 9999):
            with self.subTest(actor_id=actor_id):
                with self.assertRaises(PermissionError):
                    self.service.link_patient(
                        self.case.emergency_case_id,
                        self.patient_id,
                        actor_id,
                        "Synthetic link reason",
                    )

        self.assertEqual(self.audit_count(), audit_count)
        self.assertIsNone(
            self.case_repository.find_by_id(self.case.emergency_case_id).patient_id
        )

    def test_missing_case_or_patient_does_not_create_audit(self) -> None:
        audit_count = self.audit_count()

        self.assertIsNone(
            self.service.link_patient(
                9999,
                self.patient_id,
                self.receptionist_id,
                "Synthetic missing case",
            )
        )
        self.assertIsNone(
            self.service.link_patient(
                self.case.emergency_case_id,
                9999,
                self.receptionist_id,
                "Synthetic missing patient",
            )
        )
        self.assertEqual(self.audit_count(), audit_count)

    def test_history_failure_rolls_back_audit_and_case_update(self) -> None:
        self.connection.execute(
            """
            CREATE TEMP TRIGGER reject_test_intake_history
            BEFORE INSERT ON emergency_intake_history
            BEGIN
                SELECT RAISE(ABORT, 'synthetic history insertion failure');
            END
            """
        )
        audit_count = self.audit_count()
        with self.assertRaises(PersistenceConstraintError) as raised:
            self.service.link_patient(
                self.case.emergency_case_id,
                self.patient_id,
                self.admin_id,
                "Synthetic rollback test",
            )

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)
        self.assertEqual(self.audit_count(), audit_count)
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM emergency_intake_history
                WHERE emergency_case_id = ?
                """,
                (self.case.emergency_case_id,),
            ).fetchone()[0],
            0,
        )
        current_case = self.case_repository.find_by_id(
            self.case.emergency_case_id
        )
        self.assertIsNotNone(current_case)
        self.assertIsNone(current_case.patient_id)
