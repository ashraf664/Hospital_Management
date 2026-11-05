"""Integration-style service tests for emergency intake workflows."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import Department, Doctor, Patient, User, UserRole
from repositories import (
    DepartmentRepository,
    DoctorRepository,
    EmergencyCaseRepository,
    PatientRepository,
    PersistenceConstraintError,
    UserRepository,
)
from services import (
    AuthorizationService,
    EmergencyCaseService,
    SessionRegistry,
)


class EmergencyIntakeWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "intake.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.users = UserRepository(self.connection)
        self.departments = DepartmentRepository(self.connection)
        self.doctors = DoctorRepository(self.connection)
        self.patients = PatientRepository(self.connection)
        self.cases = EmergencyCaseRepository(self.connection)
        self.owner_id = self.create_user("synthetic-intake-owner", UserRole.ADMIN)
        self.connection.execute(
            "INSERT INTO owner_accounts (singleton_id, user_id) VALUES (1, ?)",
            (self.owner_id,),
        )
        self.admin_id = self.create_user("synthetic-intake-admin", UserRole.ADMIN)
        self.receptionist_id = self.create_user(
            "synthetic-intake-receptionist",
            UserRole.RECEPTIONIST,
        )
        self.doctor_user_id = self.create_user(
            "synthetic-intake-doctor",
            UserRole.DOCTOR,
        )
        department = self.departments.create(
            Department(name="Synthetic Emergency Department")
        )
        self.doctor = self.doctors.create(
            Doctor(
                user_id=self.doctor_user_id,
                department_id=int(department.department_id),
                full_name="Synthetic Emergency Doctor",
                specialty="Emergency Medicine",
            )
        )
        self.patient = self.patients.create(
            Patient(
                patient_number="SYNTH-ER-001",
                full_name="Synthetic Intake Patient",
                date_of_birth="1985-04-03",
            )
        )
        self.sessions = SessionRegistry()
        self.admin_session = self.sessions.issue(self.admin_id)
        self.owner_session = self.sessions.issue(self.owner_id)
        self.receptionist_session = self.sessions.issue(self.receptionist_id)
        self.doctor_session = self.sessions.issue(self.doctor_user_id)
        self.authorization = AuthorizationService(self.connection, self.sessions)
        self.service = EmergencyCaseService(self.connection, self.authorization)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def create_user(
        self,
        username: str,
        role: UserRole,
        *,
        is_active: bool = True,
    ) -> int:
        created = self.users.create(
            User(
                username=username,
                password_hash=f"synthetic-hash-{username}",
                role=role,
                is_active=is_active,
            )
        )
        return int(created.user_id)

    def audit_count(self) -> int:
        return int(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        )

    def close_assigned_case(self, emergency_case_id: int) -> None:
        treatment_time = datetime.now(timezone.utc)
        treatment_at = treatment_time.isoformat(timespec="milliseconds").replace(
            "+00:00",
            "Z",
        )
        closed_at = (treatment_time + timedelta(seconds=1)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        with self.service.transaction_manager.transaction():
            treatment_audit = self.service._create_audit(
                self.doctor_user_id,
                "emergency_status_changed",
                emergency_case_id,
                treatment_at,
            )
            self.connection.execute(
                """
                INSERT INTO emergency_status_history (
                    emergency_case_id, sequence_no, previous_status, new_status,
                    transition_type, record_origin, event_at, actor_user_id,
                    audit_log_id
                )
                VALUES (?, 2, 'Open', 'In Treatment', 'status_changed',
                        'application_event', ?, ?, ?)
                """,
                (
                    emergency_case_id,
                    treatment_at,
                    self.doctor_user_id,
                    treatment_audit.audit_log_id,
                ),
            )
            closure_audit = self.service._create_audit(
                self.doctor_user_id,
                "emergency_case_closed",
                emergency_case_id,
                closed_at,
            )
            self.connection.execute(
                """
                INSERT INTO emergency_closure_versions (
                    emergency_case_id, closure_cycle, version_no, closure_type,
                    closed_at_snapshot, closed_by_user_id, closure_summary,
                    record_origin, event_at, actor_user_id, audit_log_id
                )
                VALUES (?, 1, 1, 'closed', ?, ?, 'Synthetic closure',
                        'application_event', ?, ?, ?)
                """,
                (
                    emergency_case_id,
                    closed_at,
                    self.doctor_user_id,
                    closed_at,
                    self.doctor_user_id,
                    closure_audit.audit_log_id,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO emergency_status_history (
                    emergency_case_id, sequence_no, previous_status, new_status,
                    transition_type, record_origin, event_at, actor_user_id,
                    audit_log_id
                )
                VALUES (?, 3, 'In Treatment', 'Closed', 'status_changed',
                        'application_event', ?, ?, ?)
                """,
                (
                    emergency_case_id,
                    closed_at,
                    self.doctor_user_id,
                    closure_audit.audit_log_id,
                ),
            )

    def test_create_case_records_status_intake_and_audit_without_exposing_notes(self) -> None:
        before = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'emergency_case_created'"
        ).fetchone()[0]
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic restricted intake notes",
        )

        self.assertRegex(case.case_number, r"^ER-\d{8}-[0-9A-F]{16}$")
        datetime.fromisoformat(case.arrival_at.replace("Z", "+00:00"))
        self.assertEqual(case.status, "Open")
        self.assertIsNone(case.patient_id)
        self.assertIsNone(case.assigned_doctor_id)
        self.assertFalse(hasattr(case, "intake_notes"))
        self.assertFalse(hasattr(case, "triage_category"))
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action = 'emergency_case_created'"
            ).fetchone()[0],
            before + 1,
        )

        intake = self.connection.execute(
            """
            SELECT event_type, record_origin, actor_user_id, audit_log_id,
                   intake_notes_snapshot, event_at
            FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (case.emergency_case_id,),
        ).fetchone()
        status = self.connection.execute(
            """
            SELECT transition_type, new_status, actor_user_id, audit_log_id
            FROM emergency_status_history
            WHERE emergency_case_id = ?
            """,
            (case.emergency_case_id,),
        ).fetchone()
        self.assertEqual(intake["event_type"], "case_created")
        self.assertEqual(intake["record_origin"], "application_event")
        self.assertEqual(intake["actor_user_id"], self.receptionist_id)
        self.assertEqual(intake["intake_notes_snapshot"], "Synthetic restricted intake notes")
        self.assertEqual(status["transition_type"], "case_created")
        self.assertEqual(status["new_status"], "Open")
        self.assertEqual(status["audit_log_id"], intake["audit_log_id"])
        audit_details = self.connection.execute(
            "SELECT details FROM audit_logs WHERE audit_log_id = ?",
            (intake["audit_log_id"],),
        ).fetchone()["details"]
        self.assertNotIn("Synthetic restricted intake notes", audit_details)

    def test_case_number_generation_retries_a_collision(self) -> None:
        with patch(
            "services.emergency_case_service.secrets.token_hex",
            side_effect=["A" * 16, "A" * 16, "B" * 16],
        ):
            first = self.service.create_case(self.receptionist_session)
            second = self.service.create_case(self.receptionist_session)
        self.assertNotEqual(first.case_number, second.case_number)

    def test_create_with_patient_and_active_doctor_is_one_atomic_workflow(self) -> None:
        case = self.service.create_case(
            self.admin_session,
            patient_id=int(self.patient.patient_id),
            assigned_doctor_id=int(self.doctor.doctor_id),
            intake_notes="Synthetic initial intake",
            assignment_reason="Synthetic initial assignment",
        )
        stored = self.cases.find_by_id(case.emergency_case_id)
        assignment = self.connection.execute(
            """
            SELECT previous_doctor_id, new_doctor_id, change_reason,
                   actor_user_id, audit_log_id, event_at
            FROM emergency_doctor_assignments
            WHERE emergency_case_id = ?
            """,
            (case.emergency_case_id,),
        ).fetchone()
        self.assertEqual(stored.patient_id, self.patient.patient_id)
        self.assertEqual(stored.assigned_doctor_id, self.doctor.doctor_id)
        self.assertIsNone(assignment["previous_doctor_id"])
        self.assertEqual(assignment["new_doctor_id"], self.doctor.doctor_id)
        self.assertEqual(assignment["change_reason"], "Synthetic initial assignment")
        self.assertEqual(assignment["actor_user_id"], self.admin_id)

    def test_owner_can_create_emergency_case_under_owner_policy(self) -> None:
        owner = self.users.find_by_id(self.owner_id)
        self.assertEqual(owner.role, UserRole.OWNER)
        case = self.service.create_case(self.owner_session)
        audit = self.connection.execute(
            """
            SELECT user_id, action FROM audit_logs
            WHERE action = 'emergency_case_created'
              AND entity_id = ?
            """,
            (str(case.emergency_case_id),),
        ).fetchone()
        self.assertEqual(audit["user_id"], self.owner_id)
        self.assertEqual(audit["action"], "emergency_case_created")

    def test_link_patient_then_reassign_doctor_keeps_each_history_event(self) -> None:
        case = self.service.create_case(self.receptionist_session)
        linked = self.service.link_patient(
            case.emergency_case_id,
            int(self.patient.patient_id),
            self.receptionist_session,
            "Synthetic identity confirmation",
        )
        self.assertEqual(linked.patient_id, self.patient.patient_id)

        first = self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic first assignment",
        )
        second_user_id = self.create_user(
            "synthetic-second-doctor",
            UserRole.DOCTOR,
        )
        second_doctor = self.doctors.create(
            Doctor(
                user_id=second_user_id,
                department_id=int(self.doctor.department_id),
                full_name="Synthetic Second Doctor",
                specialty="Emergency Medicine",
            )
        )
        reassigned = self.service.assign_doctor(
            case.emergency_case_id,
            int(second_doctor.doctor_id),
            self.admin_session,
            "Synthetic shift handoff",
        )
        self.assertEqual(first.assigned_doctor_id, self.doctor.doctor_id)
        self.assertEqual(reassigned.assigned_doctor_id, second_doctor.doctor_id)

        rows = self.connection.execute(
            """
            SELECT sequence_no, previous_doctor_id, new_doctor_id, change_reason
            FROM emergency_doctor_assignments
            WHERE emergency_case_id = ?
            ORDER BY sequence_no
            """,
            (case.emergency_case_id,),
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["sequence_no"], 2)
        self.assertEqual(rows[1]["previous_doctor_id"], self.doctor.doctor_id)
        self.assertEqual(rows[1]["new_doctor_id"], second_doctor.doctor_id)
        self.assertEqual(rows[1]["change_reason"], "Synthetic shift handoff")

    def test_inactive_doctor_or_doctor_actor_is_rejected(self) -> None:
        case = self.service.create_case(self.receptionist_session)
        self.connection.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (self.doctor_user_id,),
        )
        with self.assertRaises(ValueError):
            self.service.assign_doctor(
                case.emergency_case_id,
                int(self.doctor.doctor_id),
                self.receptionist_session,
                "Synthetic inactive doctor rejection",
            )
        self.connection.execute(
            "UPDATE users SET is_active = 1 WHERE user_id = ?",
            (self.doctor_user_id,),
        )
        self.connection.execute(
            "UPDATE doctors SET is_active = 0 WHERE doctor_id = ?",
            (self.doctor.doctor_id,),
        )
        with self.assertRaises(ValueError):
            self.service.assign_doctor(
                case.emergency_case_id,
                int(self.doctor.doctor_id),
                self.receptionist_session,
                "Synthetic inactive directory rejection",
            )
        self.connection.execute(
            "UPDATE doctors SET is_active = 1 WHERE doctor_id = ?",
            (self.doctor.doctor_id,),
        )
        case_creation_audits = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'emergency_case_created'"
        ).fetchone()[0]
        with self.assertRaises(PermissionError):
            self.service.create_case(self.doctor_session)
        with self.assertRaises(PermissionError):
            self.service.assign_doctor(
                case.emergency_case_id,
                int(self.doctor.doctor_id),
                self.doctor_session,
                "Synthetic unauthorized assignment",
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action = 'emergency_case_created'"
            ).fetchone()[0],
            case_creation_audits,
        )
        self.assertIsNone(
            self.cases.find_by_id(case.emergency_case_id).assigned_doctor_id
        )

    def test_intake_note_update_is_versioned_and_never_returned(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic prior note",
        )
        updated = self.service.update_intake_notes(
            case.emergency_case_id,
            "Synthetic corrected note",
            self.admin_session,
            "Synthetic correction reason",
        )
        self.assertFalse(hasattr(updated, "intake_notes"))
        histories = self.connection.execute(
            """
            SELECT event_type, previous_intake_notes_snapshot,
                   intake_notes_snapshot, change_reason
            FROM emergency_intake_history
            WHERE emergency_case_id = ?
            ORDER BY version_no
            """,
            (case.emergency_case_id,),
        ).fetchall()
        self.assertEqual(len(histories), 2)
        self.assertEqual(histories[1]["event_type"], "intake_updated")
        self.assertEqual(histories[1]["previous_intake_notes_snapshot"], "Synthetic prior note")
        self.assertEqual(histories[1]["intake_notes_snapshot"], "Synthetic corrected note")
        self.assertEqual(histories[1]["change_reason"], "Synthetic correction reason")

    def test_closed_case_rejects_intake_updates_without_audit_or_history(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic original note",
        )
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic current assignment",
        )
        self.close_assigned_case(case.emergency_case_id)
        history_count = self.connection.execute(
            """
            SELECT COUNT(*) FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (case.emergency_case_id,),
        ).fetchone()[0]
        audit_count = self.audit_count()

        for session_token, role in (
            (self.owner_session, UserRole.OWNER),
            (self.admin_session, UserRole.ADMIN),
            (self.receptionist_session, UserRole.RECEPTIONIST),
            (self.doctor_session, UserRole.DOCTOR),
        ):
            with self.subTest(session_role=role):
                with self.assertRaisesRegex(ValueError, "case is closed"):
                    self.service.update_intake_notes(
                        case.emergency_case_id,
                        "Synthetic forbidden closed-case note",
                        session_token,
                        "Synthetic closed-case correction",
                    )

        self.assertEqual(self.audit_count(), audit_count)
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM emergency_intake_history
                WHERE emergency_case_id = ?
                """,
                (case.emergency_case_id,),
            ).fetchone()[0],
            history_count,
        )
        self.assertEqual(
            self.cases.find_by_id(case.emergency_case_id).intake_notes,
            "Synthetic original note",
        )

    def test_assigned_active_doctor_updates_notes_with_snapshots_actor_and_audit(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic original doctor-facing note",
        )
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic assignment",
        )

        updated = self.service.update_intake_notes(
            case.emergency_case_id,
            "Synthetic revised doctor-facing note",
            self.doctor_session,
            "Synthetic doctor correction",
        )

        self.assertFalse(hasattr(updated, "intake_notes"))
        history = self.connection.execute(
            """
            SELECT previous_intake_notes_snapshot, intake_notes_snapshot,
                   change_reason, actor_user_id, audit_log_id, event_at
            FROM emergency_intake_history
            WHERE emergency_case_id = ? AND event_type = 'intake_updated'
            """,
            (case.emergency_case_id,),
        ).fetchone()
        self.assertEqual(
            history["previous_intake_notes_snapshot"],
            "Synthetic original doctor-facing note",
        )
        self.assertEqual(
            history["intake_notes_snapshot"],
            "Synthetic revised doctor-facing note",
        )
        self.assertEqual(history["change_reason"], "Synthetic doctor correction")
        self.assertEqual(history["actor_user_id"], self.doctor_user_id)
        self.assertTrue(history["event_at"])
        audit = self.connection.execute(
            """
            SELECT user_id, action, occurred_at, details
            FROM audit_logs WHERE audit_log_id = ?
            """,
            (history["audit_log_id"],),
        ).fetchone()
        self.assertEqual(audit["user_id"], self.doctor_user_id)
        self.assertEqual(audit["action"], "emergency_intake_updated")
        self.assertEqual(audit["occurred_at"], history["event_at"])
        self.assertNotIn("Synthetic revised doctor-facing note", audit["details"])

    def test_non_assigned_doctor_cannot_update_intake_notes(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic protected note",
        )
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic current assignment",
        )
        other_user_id = self.create_user(
            "synthetic-other-emergency-doctor",
            UserRole.DOCTOR,
        )
        other_doctor = self.doctors.create(
            Doctor(
                user_id=other_user_id,
                department_id=int(self.doctor.department_id),
                full_name="Synthetic Other Emergency Doctor",
                specialty="Emergency Medicine",
            )
        )
        other_session = self.sessions.issue(other_user_id)
        audit_count = self.audit_count()

        with self.assertRaises(PermissionError):
            self.service.update_intake_notes(
                case.emergency_case_id,
                "Synthetic unauthorized edit",
                other_session,
                "Synthetic unauthorized reason",
            )

        saved = self.cases.find_by_id(case.emergency_case_id)
        self.assertEqual(saved.intake_notes, "Synthetic protected note")
        self.assertEqual(self.audit_count(), audit_count)
        self.assertIsNotNone(other_doctor.doctor_id)

    def test_inactive_doctor_account_or_profile_cannot_update_intake_notes(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic protected note",
        )
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic current assignment",
        )
        audit_count = self.audit_count()

        self.connection.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (self.doctor_user_id,),
        )
        with self.assertRaises(PermissionError):
            self.service.update_intake_notes(
                case.emergency_case_id,
                "Synthetic edit by inactive account",
                self.doctor_session,
                "Synthetic inactive account reason",
            )
        self.connection.execute(
            "UPDATE users SET is_active = 1 WHERE user_id = ?",
            (self.doctor_user_id,),
        )

        self.connection.execute(
            "UPDATE doctors SET is_active = 0 WHERE doctor_id = ?",
            (self.doctor.doctor_id,),
        )
        with self.assertRaises(PermissionError):
            self.service.update_intake_notes(
                case.emergency_case_id,
                "Synthetic edit by inactive profile",
                self.doctor_session,
                "Synthetic inactive profile reason",
            )

        self.assertEqual(self.audit_count(), audit_count)
        self.assertEqual(
            self.cases.find_by_id(case.emergency_case_id).intake_notes,
            "Synthetic protected note",
        )

    def test_doctor_cannot_link_patient_or_assign_or_reassign_doctor(self) -> None:
        case = self.service.create_case(self.receptionist_session)
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic current assignment",
        )
        other_user_id = self.create_user(
            "synthetic-reassignment-target",
            UserRole.DOCTOR,
        )
        other_doctor = self.doctors.create(
            Doctor(
                user_id=other_user_id,
                department_id=int(self.doctor.department_id),
                full_name="Synthetic Reassignment Target",
                specialty="Emergency Medicine",
            )
        )
        audit_count = self.audit_count()

        with self.assertRaises(PermissionError):
            self.service.link_patient(
                case.emergency_case_id,
                int(self.patient.patient_id),
                self.doctor_session,
                "Synthetic unauthorized patient link",
            )
        for doctor_id in (int(self.doctor.doctor_id), int(other_doctor.doctor_id)):
            with self.subTest(doctor_id=doctor_id):
                with self.assertRaises(PermissionError):
                    self.service.assign_doctor(
                        case.emergency_case_id,
                        doctor_id,
                        self.doctor_session,
                        "Synthetic unauthorized doctor change",
                    )

        saved = self.cases.find_by_id(case.emergency_case_id)
        self.assertIsNone(saved.patient_id)
        self.assertEqual(saved.assigned_doctor_id, self.doctor.doctor_id)
        self.assertEqual(self.audit_count(), audit_count)

    def test_empty_or_whitespace_intake_note_reasons_are_rejected(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic unchanged note",
        )
        audit_count = self.audit_count()
        for reason in ("", "   \t"):
            with self.subTest(reason=reason):
                with self.assertRaises(ValueError):
                    self.service.update_intake_notes(
                        case.emergency_case_id,
                        "Synthetic rejected note",
                        self.doctor_session,
                        reason,
                    )
        self.assertEqual(self.audit_count(), audit_count)
        self.assertEqual(
            self.cases.find_by_id(case.emergency_case_id).intake_notes,
            "Synthetic unchanged note",
        )

    def test_intake_history_failure_rolls_back_doctor_audit_and_note(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic original note",
        )
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic current assignment",
        )
        history_count = self.connection.execute(
            """
            SELECT COUNT(*) FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (case.emergency_case_id,),
        ).fetchone()[0]
        audit_count = self.audit_count()
        self.connection.execute(
            """
            CREATE TEMP TRIGGER reject_test_doctor_intake_history
            BEFORE INSERT ON emergency_intake_history
            WHEN NEW.event_type = 'intake_updated'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic doctor intake history failure');
            END
            """
        )

        with self.assertRaises(PersistenceConstraintError) as raised:
            self.service.update_intake_notes(
                case.emergency_case_id,
                "Synthetic uncommitted note",
                self.doctor_session,
                "Synthetic history rollback",
            )

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertEqual(self.audit_count(), audit_count)
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM emergency_intake_history
                WHERE emergency_case_id = ?
                """,
                (case.emergency_case_id,),
            ).fetchone()[0],
            history_count,
        )
        self.assertEqual(
            self.cases.find_by_id(case.emergency_case_id).intake_notes,
            "Synthetic original note",
        )

    def test_intake_audit_failure_rolls_back_doctor_history_and_note(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic original note",
        )
        self.service.assign_doctor(
            case.emergency_case_id,
            int(self.doctor.doctor_id),
            self.receptionist_session,
            "Synthetic current assignment",
        )
        history_count = self.connection.execute(
            """
            SELECT COUNT(*) FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (case.emergency_case_id,),
        ).fetchone()[0]
        audit_count = self.audit_count()
        self.connection.execute(
            """
            CREATE TEMP TRIGGER reject_test_doctor_intake_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'emergency_intake_updated'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic doctor intake audit failure');
            END
            """
        )

        with self.assertRaises(PersistenceConstraintError) as raised:
            self.service.update_intake_notes(
                case.emergency_case_id,
                "Synthetic uncommitted note",
                self.doctor_session,
                "Synthetic audit rollback",
            )

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertEqual(self.audit_count(), audit_count)
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM emergency_intake_history
                WHERE emergency_case_id = ?
                """,
                (case.emergency_case_id,),
            ).fetchone()[0],
            history_count,
        )
        self.assertEqual(
            self.cases.find_by_id(case.emergency_case_id).intake_notes,
            "Synthetic original note",
        )

    def test_admin_receptionist_and_owner_retain_note_update_permission(self) -> None:
        case = self.service.create_case(self.receptionist_session)
        for session, actor_id, value in (
            (self.admin_session, self.admin_id, "Synthetic Admin note"),
            (
                self.receptionist_session,
                self.receptionist_id,
                "Synthetic Receptionist note",
            ),
            (self.owner_session, self.owner_id, "Synthetic Owner note"),
        ):
            with self.subTest(actor_id=actor_id):
                self.service.update_intake_notes(
                    case.emergency_case_id,
                    value,
                    session,
                    "Synthetic permitted correction",
                )
                history = self.connection.execute(
                    """
                    SELECT actor_user_id FROM emergency_intake_history
                    WHERE emergency_case_id = ? AND event_type = 'intake_updated'
                    ORDER BY version_no DESC LIMIT 1
                    """,
                    (case.emergency_case_id,),
                ).fetchone()
                self.assertEqual(history["actor_user_id"], actor_id)

    def test_failed_creation_and_assignment_roll_back_case_and_audit(self) -> None:
        before = self.audit_count()
        self.connection.execute(
            """
            CREATE TEMP TRIGGER reject_test_status_history
            BEFORE INSERT ON emergency_status_history
            BEGIN
                SELECT RAISE(ABORT, 'synthetic status history failure');
            END
            """
        )
        with self.assertRaises(PersistenceConstraintError) as raised:
            self.service.create_case(self.receptionist_session)
        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertEqual(self.audit_count(), before)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM emergency_cases"
            ).fetchone()[0],
            0,
        )
        self.connection.execute("DROP TRIGGER reject_test_status_history")

        case = self.service.create_case(self.receptionist_session)
        before_assignment_audits = self.audit_count()
        self.connection.execute(
            """
            CREATE TEMP TRIGGER reject_test_assignment_history
            BEFORE INSERT ON emergency_doctor_assignments
            BEGIN
                SELECT RAISE(ABORT, 'synthetic assignment history failure');
            END
            """
        )
        with self.assertRaises(PersistenceConstraintError):
            self.service.assign_doctor(
                case.emergency_case_id,
                int(self.doctor.doctor_id),
                self.receptionist_session,
                "Synthetic rollback assignment",
            )
        self.assertEqual(self.audit_count(), before_assignment_audits)
        self.assertIsNone(
            self.cases.find_by_id(case.emergency_case_id).assigned_doctor_id
        )
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*) FROM emergency_doctor_assignments
                WHERE emergency_case_id = ?
                """,
                (case.emergency_case_id,),
            ).fetchone()[0],
            0,
        )

    def test_search_and_reopened_database_retain_case_without_notes_in_view(self) -> None:
        case = self.service.create_case(
            self.receptionist_session,
            intake_notes="Synthetic private note",
        )
        page = self.service.search_cases(
            self.receptionist_session,
            case_number=case.case_number,
            limit=10,
        )
        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items.get(0).case_number, case.case_number)
        self.connection.close()

        reopened = ConnectionManager(self.database_path).connect()
        try:
            saved = EmergencyCaseRepository(reopened).find_by_id(
                case.emergency_case_id
            )
            self.assertEqual(saved.case_number, case.case_number)
            self.assertEqual(saved.intake_notes, "Synthetic private note")
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
