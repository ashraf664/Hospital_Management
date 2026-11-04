"""SQLite-backed tests for EmergencyCaseRepository."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from database.transaction_manager import TransactionManager
from models import (
    AuditActorType,
    AuditLog,
    Department,
    Doctor,
    EmergencyCase,
    Patient,
    User,
    UserRole,
)
from repositories import (
    AuditLogRepository,
    DepartmentRepository,
    DoctorRepository,
    EmergencyCaseRepository,
    PatientRepository,
    PersistenceConflictError,
    PersistenceConstraintError,
    UserRepository,
)


class EmergencyCaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "emergency.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.user_repository = UserRepository(self.connection)
        self.department_repository = DepartmentRepository(self.connection)
        self.doctor_repository = DoctorRepository(self.connection)
        self.patient_repository = PatientRepository(self.connection)
        self.case_repository = EmergencyCaseRepository(self.connection)
        self.audit_log_repository = AuditLogRepository(self.connection)
        self.receptionist_id = self.create_user(
            "synthetic-receptionist",
            UserRole.RECEPTIONIST,
        )
        self.doctor_id = self.create_doctor("synthetic-emergency-doctor")
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.connection.close)

    def create_user(self, username: str, role: UserRole) -> int:
        user = self.user_repository.create(
            User(
                username=username,
                password_hash=f"synthetic-hash-{username}",
                role=role,
            )
        )
        return user.user_id

    def create_doctor(self, username: str) -> int:
        department = self.department_repository.create(
            Department(name=f"Department for {username}")
        )
        doctor_user_id = self.create_user(username, UserRole.DOCTOR)
        doctor = self.doctor_repository.create(
            Doctor(
                user_id=doctor_user_id,
                department_id=department.department_id,
                full_name=f"Synthetic {username}",
                specialty="Synthetic Specialty",
            )
        )
        return doctor.doctor_id

    def create_patient(self, patient_number: str) -> int:
        patient = self.patient_repository.create(
            Patient(
                patient_number=patient_number,
                full_name="Synthetic Emergency Patient",
                date_of_birth="1980-01-02",
            )
        )
        return patient.patient_id

    def create_case(
        self,
        case_number: str,
        *,
        patient_id: int | None = None,
        assigned_doctor_id: int | None = None,
        intake_user_id: int | None = None,
        triage_category: str | None = None,
        status: str = "Open",
        arrival_at: str = "2030-01-02T10:00:00Z",
        closed_at: str | None = None,
        intake_notes: str = "",
    ) -> EmergencyCase:
        return self.case_repository.create(
            EmergencyCase(
                case_number=case_number,
                patient_id=patient_id,
                assigned_doctor_id=assigned_doctor_id,
                intake_user_id=(
                    self.receptionist_id
                    if intake_user_id is None
                    else intake_user_id
                ),
                triage_category=triage_category,
                status=status,
                arrival_at=arrival_at,
                closed_at=closed_at,
                intake_notes=intake_notes,
            )
        )

    def test_create_reads_saved_case_with_nullable_values_and_timestamps(self) -> None:
        created = self.create_case("ER-SYNTH-001")

        self.assertIsInstance(created.emergency_case_id, int)
        self.assertEqual(created.case_number, "ER-SYNTH-001")
        self.assertIsNone(created.patient_id)
        self.assertIsNone(created.assigned_doctor_id)
        self.assertEqual(created.intake_user_id, self.receptionist_id)
        self.assertIsNone(created.triage_category)
        self.assertEqual(created.status, "Open")
        self.assertEqual(created.arrival_at, "2030-01-02T10:00:00Z")
        self.assertIsNone(created.closed_at)
        self.assertEqual(created.intake_notes, "")
        self.assertIsNotNone(created.created_at)
        self.assertIsNotNone(created.updated_at)
        self.assertRegex(created.created_at, r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertRegex(created.updated_at, r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertEqual(
            self.case_repository.find_by_id(created.emergency_case_id),
            created,
        )

    def test_create_can_link_existing_patient_and_currently_assigned_doctor(self) -> None:
        patient_id = self.create_patient("SYNTH-EMERGENCY-001")

        created = self.create_case(
            "ER-SYNTH-002",
            patient_id=patient_id,
            assigned_doctor_id=self.doctor_id,
            triage_category="Synthetic category",
            intake_notes="Synthetic intake notes",
        )

        self.assertEqual(created.patient_id, patient_id)
        self.assertEqual(created.assigned_doctor_id, self.doctor_id)
        self.assertEqual(created.triage_category, "Synthetic category")
        self.assertEqual(created.intake_notes, "Synthetic intake notes")

    def test_find_by_id_and_case_number_return_none_when_missing(self) -> None:
        created = self.create_case("ER-SYNTH-FIND")

        self.assertEqual(
            self.case_repository.find_by_id(created.emergency_case_id),
            created,
        )
        self.assertEqual(
            self.case_repository.find_by_case_number("ER-SYNTH-FIND"),
            created,
        )
        self.assertIsNone(self.case_repository.find_by_id(9999))
        self.assertIsNone(self.case_repository.find_by_case_number("ER-MISSING"))

    def test_find_for_doctor_returns_only_currently_assigned_cases(self) -> None:
        assigned = self.create_case(
            "ER-SYNTH-ASSIGNED",
            assigned_doctor_id=self.doctor_id,
        )
        unassigned = self.create_case("ER-SYNTH-UNASSIGNED")

        self.assertEqual(
            self.case_repository.find_for_doctor(
                assigned.emergency_case_id,
                self.doctor_id,
            ),
            assigned,
        )
        self.assertIsNone(
            self.case_repository.find_for_doctor(
                unassigned.emergency_case_id,
                self.doctor_id,
            )
        )
        self.assertIsNone(
            self.case_repository.find_for_doctor(
                assigned.emergency_case_id,
                9999,
            )
        )
        self.assertIsNone(self.case_repository.find_for_doctor(9999, self.doctor_id))

    def test_link_patient_updates_case_and_missing_case_returns_none(self) -> None:
        created = self.create_case("ER-SYNTH-LINK")
        patient_id = self.create_patient("SYNTH-ER-LINK")
        event_at = "2030-01-02T11:00:00Z"
        with TransactionManager(self.connection).transaction():
            audit_log = self.audit_log_repository.create(
                AuditLog(
                    actor_type=AuditActorType.USER,
                    action="patient_linked",
                    entity_type="emergency_case",
                    user_id=self.receptionist_id,
                    entity_id=str(created.emergency_case_id),
                    occurred_at=event_at,
                )
            )
            linked = self.case_repository.link_patient(
                created.emergency_case_id,
                patient_id,
                actor_user_id=self.receptionist_id,
                audit_log_id=int(audit_log.audit_log_id),
                change_reason="Synthetic patient identification",
                event_at=event_at,
            )

        self.assertIsNotNone(linked)
        self.assertEqual(linked.patient_id, patient_id)
        self.assertEqual(linked.case_number, created.case_number)
        self.assertEqual(linked.intake_user_id, created.intake_user_id)
        history = self.connection.execute(
            """
            SELECT event_type, previous_patient_id_snapshot,
                   patient_id_snapshot, change_reason, actor_user_id,
                   audit_log_id, event_at
            FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (created.emergency_case_id,),
        ).fetchone()
        self.assertEqual(history["event_type"], "patient_linked")
        self.assertIsNone(history["previous_patient_id_snapshot"])
        self.assertEqual(history["patient_id_snapshot"], patient_id)
        self.assertEqual(history["change_reason"], "Synthetic patient identification")
        self.assertEqual(history["actor_user_id"], self.receptionist_id)
        self.assertEqual(history["audit_log_id"], audit_log.audit_log_id)
        self.assertEqual(history["event_at"], event_at)
        self.assertIsNone(
            self.case_repository.link_patient(
                9999,
                patient_id,
                actor_user_id=self.receptionist_id,
                audit_log_id=int(audit_log.audit_log_id),
                change_reason="Synthetic missing case",
                event_at=event_at,
            )
        )

    def test_link_patient_foreign_key_failure_preserves_original_cause(self) -> None:
        created = self.create_case("ER-SYNTH-BAD-LINK")
        event_at = "2030-01-02T11:00:00Z"
        with self.assertRaises(PersistenceConstraintError) as raised:
            with TransactionManager(self.connection).transaction():
                audit_log = self.audit_log_repository.create(
                    AuditLog(
                        actor_type=AuditActorType.USER,
                        action="patient_linked",
                        entity_type="emergency_case",
                        user_id=self.receptionist_id,
                        entity_id=str(created.emergency_case_id),
                        occurred_at=event_at,
                    )
                )
                self.case_repository.link_patient(
                    created.emergency_case_id,
                    9999,
                    actor_user_id=self.receptionist_id,
                    audit_log_id=int(audit_log.audit_log_id),
                    change_reason="Synthetic invalid patient",
                    event_at=event_at,
                )

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)

    def test_search_filters_by_case_patient_doctor_date_status_and_triage(self) -> None:
        patient_id = self.create_patient("SYNTH-ER-SEARCH")
        matching = self.create_case(
            "ER-SYNTH-SEARCH-1",
            patient_id=patient_id,
            assigned_doctor_id=self.doctor_id,
            triage_category="Synthetic triage",
            status="In Treatment",
            arrival_at="2030-01-02T10:00:00Z",
        )
        self.create_case(
            "ER-SYNTH-SEARCH-2",
            patient_id=patient_id,
            assigned_doctor_id=self.doctor_id,
            triage_category="Other triage",
            status="Open",
            arrival_at="2030-01-03T10:00:00Z",
        )

        self.assertEqual(
            self.case_repository.search(
                case_number="ER-SYNTH-SEARCH-1"
            ).total_count,
            1,
        )
        self.assertEqual(
            self.case_repository.search(patient_id=patient_id).total_count,
            2,
        )
        self.assertEqual(
            self.case_repository.search(
                assigned_doctor_id=self.doctor_id
            ).total_count,
            2,
        )
        self.assertEqual(
            self.case_repository.search(arrival_date="2030-01-02").total_count,
            1,
        )
        self.assertEqual(
            self.case_repository.search(status="Open").total_count,
            1,
        )
        self.assertEqual(
            self.case_repository.search(
                triage_category="Synthetic triage"
            ).total_count,
            1,
        )
        combined = self.case_repository.search(
            case_number="ER-SYNTH-SEARCH-1",
            patient_id=patient_id,
            assigned_doctor_id=self.doctor_id,
            arrival_date="2030-01-02",
            status="In Treatment",
            triage_category="Synthetic triage",
        )
        self.assertEqual(combined.total_count, 1)
        self.assertEqual(combined.items.get(0), matching)

    def test_search_paginates_with_total_count_and_stable_ordering(self) -> None:
        cases = (
            self.create_case(
                "ER-SYNTH-PAGE-1",
                arrival_at="2030-01-02T10:00:00Z",
            ),
            self.create_case(
                "ER-SYNTH-PAGE-2",
                arrival_at="2030-01-03T10:00:00Z",
            ),
            self.create_case(
                "ER-SYNTH-PAGE-3",
                arrival_at="2030-01-03T10:00:00Z",
            ),
        )

        first_page = self.case_repository.search(limit=2)
        second_page = self.case_repository.search(limit=2, offset=2)
        empty_page = self.case_repository.search(limit=2, offset=10)
        maximum_page = self.case_repository.search(limit=200)

        self.assertEqual(first_page.total_count, 3)
        self.assertEqual(first_page.limit, 2)
        self.assertEqual(first_page.offset, 0)
        self.assertEqual(
            [case.emergency_case_id for case in first_page.items],
            [cases[1].emergency_case_id, cases[2].emergency_case_id],
        )
        self.assertEqual(
            [case.emergency_case_id for case in second_page.items],
            [cases[0].emergency_case_id],
        )
        self.assertEqual(second_page.total_count, 3)
        self.assertEqual(empty_page.total_count, 3)
        self.assertEqual(len(empty_page.items), 0)
        self.assertEqual(maximum_page.limit, 200)

        for kwargs in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.case_repository.search(**kwargs)

    def test_unique_and_check_errors_are_translated_with_original_cause(self) -> None:
        self.create_case("ER-SYNTH-DUPLICATE")
        with self.assertRaises(PersistenceConflictError) as duplicate:
            self.create_case("ER-SYNTH-DUPLICATE")
        self.assertIsInstance(duplicate.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(duplicate.exception.original_cause, duplicate.exception.__cause__)

        with self.assertRaises(PersistenceConstraintError) as blank_number:
            self.create_case("   ")
        self.assertIsInstance(blank_number.exception.__cause__, sqlite3.IntegrityError)

        with self.assertRaises(PersistenceConstraintError) as invalid_arrival:
            self.create_case(
                "ER-SYNTH-BAD-TIME",
                arrival_at="not-a-timestamp",
            )
        self.assertIsInstance(invalid_arrival.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(
            invalid_arrival.exception.original_cause,
            invalid_arrival.exception.__cause__,
        )

    def test_create_rejects_missing_foreign_keys(self) -> None:
        for values in (
            {"intake_user_id": 9999},
            {"patient_id": 9999},
            {"assigned_doctor_id": 9999},
        ):
            with self.subTest(values=values), self.assertRaises(
                PersistenceConstraintError
            ) as raised:
                self.create_case(
                    f"ER-SYNTH-FK-{len(values)}-{next(iter(values))}",
                    **values,
                )
            self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
            self.assertIs(raised.exception.original_cause, raised.exception.__cause__)

    def test_repository_uses_shared_connection_and_external_rollback(self) -> None:
        statements: list[str] = []
        self.connection.set_trace_callback(statements.append)
        self.connection.execute("BEGIN")

        created = self.create_case("ER-SYNTH-ROLLBACK")

        self.assertIs(self.case_repository.connection, self.connection)
        self.assertTrue(self.connection.in_transaction)
        self.assertFalse(
            any(
                statement.strip().upper() in {"COMMIT", "ROLLBACK"}
                for statement in statements[1:]
            )
        )
        self.connection.set_trace_callback(None)
        self.connection.rollback()
        self.assertIsNone(
            self.case_repository.find_by_id(created.emergency_case_id)
        )

    def test_repository_does_not_expose_delete_or_clinical_mutation_operations(self) -> None:
        for forbidden_operation in (
            "delete",
            "update_status",
            "update_triage",
            "update_outcome",
            "close_case",
            "assign_doctor",
        ):
            self.assertFalse(hasattr(self.case_repository, forbidden_operation))


if __name__ == "__main__":
    unittest.main()
