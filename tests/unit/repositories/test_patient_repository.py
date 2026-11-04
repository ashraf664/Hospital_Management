"""SQLite-backed tests for PatientRepository."""

from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import Department, Doctor, Patient, User, UserRole
from repositories import (
    DepartmentRepository,
    DoctorRepository,
    PatientRepository,
    PersistenceConflictError,
    PersistenceConstraintError,
    UserRepository,
)


class PatientRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "patients.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.user_repository = UserRepository(self.connection)
        self.department_repository = DepartmentRepository(self.connection)
        self.doctor_repository = DoctorRepository(self.connection)
        self.patient_repository = PatientRepository(self.connection)
        self.actor_user_id = self.create_user("test-admin", UserRole.ADMIN)
        self.doctor_id = self.create_doctor("test-doctor")
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
        user_id = self.create_user(username, UserRole.DOCTOR)
        doctor = self.doctor_repository.create(
            Doctor(
                user_id=user_id,
                department_id=department.department_id,
                full_name=f"Synthetic {username}",
                specialty="Synthetic Specialty",
            )
        )
        return doctor.doctor_id

    def create_patient(
        self,
        patient_number: str,
        *,
        full_name: str = "Synthetic Patient",
        date_of_birth: str = "1980-01-02",
        sex: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        emergency_contact: str | None = None,
        is_active: bool = True,
    ) -> Patient:
        return self.patient_repository.create(
            Patient(
                patient_number=patient_number,
                full_name=full_name,
                date_of_birth=date_of_birth,
                sex=sex,
                phone=phone,
                address=address,
                emergency_contact=emergency_contact,
                is_active=is_active,
            )
        )

    def create_assignment(self, doctor_id: int, patient_id: int) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO doctor_patient_assignments
                (doctor_id, patient_id, assigned_by_user_id)
            VALUES (?, ?, ?)
            """,
            (doctor_id, patient_id, self.actor_user_id),
        )
        return int(cursor.lastrowid)

    def test_create_reads_saved_patient_and_preserves_nulls_and_timestamps(self) -> None:
        created = self.create_patient("SYNTH-001")

        self.assertIsInstance(created.patient_id, int)
        self.assertEqual(created.patient_number, "SYNTH-001")
        self.assertEqual(created.full_name, "Synthetic Patient")
        self.assertEqual(created.date_of_birth, "1980-01-02")
        self.assertIsNone(created.sex)
        self.assertIsNone(created.phone)
        self.assertIsNone(created.address)
        self.assertIsNone(created.emergency_contact)
        self.assertIs(created.is_active, True)
        self.assertIsNotNone(created.created_at)
        self.assertIsNotNone(created.updated_at)
        self.assertRegex(created.created_at, r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertRegex(created.updated_at, r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertEqual(
            self.patient_repository.find_by_id(created.patient_id),
            created,
        )

    def test_update_changes_demographics_but_preserves_identity_and_creation_time(self) -> None:
        created = self.create_patient(
            "SYNTH-UPDATE",
            full_name="Before Update",
            sex="test value",
            phone="555-0101",
            address="Synthetic address",
            emergency_contact="Synthetic contact",
        )
        time.sleep(0.02)

        updated = self.patient_repository.update_demographics(
            created.patient_id,
            "After Update",
            "1990-12-31",
            None,
            None,
            "Updated synthetic address",
            None,
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.patient_id, created.patient_id)
        self.assertEqual(updated.patient_number, "SYNTH-UPDATE")
        self.assertEqual(updated.created_at, created.created_at)
        self.assertEqual(updated.full_name, "After Update")
        self.assertEqual(updated.date_of_birth, "1990-12-31")
        self.assertIsNone(updated.sex)
        self.assertIsNone(updated.phone)
        self.assertEqual(updated.address, "Updated synthetic address")
        self.assertIsNone(updated.emergency_contact)
        self.assertGreater(updated.updated_at, created.updated_at)
        self.assertIsNone(
            self.patient_repository.update_demographics(
                9999,
                "Missing",
                "1990-12-31",
                None,
                None,
                None,
                None,
            )
        )

    def test_deactivate_marks_patient_inactive_without_deleting_it(self) -> None:
        created = self.create_patient("SYNTH-DEACTIVATE")

        deactivated = self.patient_repository.deactivate(created.patient_id)

        self.assertIsNotNone(deactivated)
        self.assertIs(deactivated.is_active, False)
        self.assertEqual(deactivated.patient_number, created.patient_number)
        self.assertGreaterEqual(deactivated.updated_at, created.updated_at)
        self.assertIsNone(self.patient_repository.deactivate(9999))
        self.assertFalse(hasattr(self.patient_repository, "delete"))
        stored = self.connection.execute(
            "SELECT patient_id, is_active FROM patients WHERE patient_id = ?",
            (created.patient_id,),
        ).fetchone()
        self.assertEqual(stored["patient_id"], created.patient_id)
        self.assertEqual(stored["is_active"], 0)

    def test_find_methods_use_exact_patient_number_and_return_none_when_missing(self) -> None:
        patient = self.create_patient("SYNTH-FIND-001")
        self.create_patient("SYNTH-FIND-010")

        self.assertEqual(
            self.patient_repository.find_by_number("SYNTH-FIND-001"),
            patient,
        )
        self.assertIsNone(self.patient_repository.find_by_number("FIND-001"))
        self.assertIsNone(self.patient_repository.find_by_id(9999))

    def test_search_supports_partial_name_and_phone_matching(self) -> None:
        self.create_patient(
            "SYNTH-PARTIAL-001",
            full_name="Alexandra Synthetic",
            phone="555-123-4567",
        )
        self.create_patient(
            "SYNTH-PARTIAL-002",
            full_name="Jordan Synthetic",
            phone="555-987-0000",
        )

        by_name = self.patient_repository.search(full_name="andra Syn")
        by_phone = self.patient_repository.search(phone="123-45")

        self.assertEqual(by_name.total_count, 1)
        self.assertEqual(by_name.items.get(0).full_name, "Alexandra Synthetic")
        self.assertEqual(by_phone.total_count, 1)
        self.assertEqual(by_phone.items.get(0).patient_number, "SYNTH-PARTIAL-001")

    def test_search_treats_like_wildcard_characters_as_literals(self) -> None:
        matching = self.create_patient(
            "SYNTH-LITERAL-001",
            full_name="Patient 100%_ Real",
            phone="555-100%_22",
        )
        self.create_patient(
            "SYNTH-LITERAL-002",
            full_name="Patient 100XX Real",
            phone="555-100XX22",
        )

        by_name = self.patient_repository.search(full_name="100%_")
        by_phone = self.patient_repository.search(phone="100%_")

        self.assertEqual(by_name.total_count, 1)
        self.assertEqual(by_name.items.get(0).patient_id, matching.patient_id)
        self.assertEqual(by_phone.total_count, 1)
        self.assertEqual(by_phone.items.get(0).patient_id, matching.patient_id)

    def test_search_combines_filters_and_applies_them_to_total_count(self) -> None:
        matching = self.create_patient(
            "SYNTH-FILTER-001",
            full_name="Morgan Synthetic",
            phone="555-111-1000",
            is_active=True,
        )
        self.create_patient(
            "SYNTH-FILTER-002",
            full_name="Morgan Inactive",
            phone="555-111-2000",
            is_active=False,
        )
        self.create_patient(
            "SYNTH-FILTER-003",
            full_name="Taylor Synthetic",
            phone="555-111-3000",
            is_active=True,
        )

        result = self.patient_repository.search(
            patient_number="SYNTH-FILTER-001",
            full_name="Morgan",
            phone="111",
            is_active=True,
        )

        self.assertEqual(result.total_count, 1)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items.get(0), matching)

    def test_search_paginates_in_stable_patient_id_order(self) -> None:
        patients = (
            self.create_patient("SYNTH-PAGE-001", full_name="Same Name"),
            self.create_patient("SYNTH-PAGE-002", full_name="Same Name"),
            self.create_patient("SYNTH-PAGE-003", full_name="Same Name"),
        )

        first_page = self.patient_repository.search(full_name="Same", limit=2)
        second_page = self.patient_repository.search(
            full_name="Same",
            limit=2,
            offset=2,
        )
        empty_page = self.patient_repository.search(
            full_name="Same",
            limit=2,
            offset=10,
        )

        self.assertEqual(first_page.total_count, 3)
        self.assertEqual(first_page.offset, 0)
        self.assertEqual(
            [patient.patient_id for patient in first_page.items],
            [patients[0].patient_id, patients[1].patient_id],
        )
        self.assertEqual(
            [patient.patient_id for patient in second_page.items],
            [patients[2].patient_id],
        )
        self.assertEqual(second_page.total_count, 3)
        self.assertEqual(len(empty_page.items), 0)
        self.assertEqual(empty_page.total_count, 3)

        for kwargs in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.patient_repository.search(**kwargs)

    def test_create_translates_unique_and_check_violations_with_original_cause(self) -> None:
        self.create_patient("SYNTH-UNIQUE")
        with self.assertRaises(PersistenceConflictError) as duplicate:
            self.create_patient("SYNTH-UNIQUE")
        self.assertIsInstance(duplicate.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(
            duplicate.exception.original_cause,
            duplicate.exception.__cause__,
        )

        with self.assertRaises(PersistenceConstraintError) as invalid_date:
            self.create_patient(
                "SYNTH-BAD-DATE",
                date_of_birth="1980-13-40",
            )
        self.assertIsInstance(invalid_date.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(
            invalid_date.exception.original_cause,
            invalid_date.exception.__cause__,
        )

        with self.assertRaises(PersistenceConstraintError) as blank_number:
            self.create_patient("   ")
        self.assertIsInstance(blank_number.exception.__cause__, sqlite3.IntegrityError)

    def test_shared_repository_executor_translates_assignment_foreign_key_failure(self) -> None:
        with self.assertRaises(PersistenceConstraintError) as raised:
            self.patient_repository._execute(
                """
                INSERT INTO doctor_patient_assignments
                    (doctor_id, patient_id, assigned_by_user_id)
                VALUES (?, ?, ?)
                """,
                (9999, 9999, self.actor_user_id),
            )

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(
            raised.exception.original_cause,
            raised.exception.__cause__,
        )

    def test_find_for_doctor_requires_an_active_assignment(self) -> None:
        assigned = self.create_patient("SYNTH-ASSIGNED")
        unassigned = self.create_patient("SYNTH-UNASSIGNED")
        self.create_assignment(self.doctor_id, assigned.patient_id)

        self.assertEqual(
            self.patient_repository.find_for_doctor(
                self.doctor_id,
                assigned.patient_id,
            ),
            assigned,
        )
        self.assertIsNone(
            self.patient_repository.find_for_doctor(
                self.doctor_id,
                unassigned.patient_id,
            )
        )
        self.assertIsNone(
            self.patient_repository.find_for_doctor(9999, assigned.patient_id)
        )

    def test_find_for_doctor_denies_patient_after_assignment_is_ended(self) -> None:
        patient = self.create_patient("SYNTH-ENDED")
        assignment_id = self.create_assignment(self.doctor_id, patient.patient_id)
        self.connection.execute(
            """
            UPDATE doctor_patient_assignments
            SET ended_by_user_id = ?,
                ended_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE assignment_id = ?
            """,
            (self.actor_user_id, assignment_id),
        )

        self.assertIsNone(
            self.patient_repository.find_for_doctor(self.doctor_id, patient.patient_id)
        )

    def test_appointment_alone_does_not_grant_doctor_patient_access(self) -> None:
        patient = self.create_patient("SYNTH-APPOINTMENT-ONLY")
        self.connection.execute(
            """
            INSERT INTO appointments (
                patient_id, doctor_id, scheduled_start, scheduled_end, status,
                created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                patient.patient_id,
                self.doctor_id,
                "2030-01-02T10:00:00Z",
                "2030-01-02T10:30:00Z",
                "scheduled",
                self.actor_user_id,
            ),
        )

        self.assertIsNone(
            self.patient_repository.find_for_doctor(self.doctor_id, patient.patient_id)
        )
        page = self.patient_repository.search(doctor_id=self.doctor_id)
        self.assertEqual(page.total_count, 0)
        self.assertEqual(len(page.items), 0)

    def test_search_doctor_scope_filters_items_and_count_and_allows_multiple_doctors(self) -> None:
        patient = self.create_patient("SYNTH-MULTI-DOCTOR")
        other_patient = self.create_patient("SYNTH-OTHER-DOCTOR")
        second_doctor_id = self.create_doctor("second-test-doctor")
        self.create_assignment(self.doctor_id, patient.patient_id)
        self.create_assignment(second_doctor_id, patient.patient_id)
        self.create_assignment(second_doctor_id, other_patient.patient_id)

        first_doctor_page = self.patient_repository.search(doctor_id=self.doctor_id)
        second_doctor_page = self.patient_repository.search(
            doctor_id=second_doctor_id
        )

        self.assertEqual(first_doctor_page.total_count, 1)
        self.assertEqual(len(first_doctor_page.items), 1)
        self.assertEqual(first_doctor_page.items.get(0).patient_id, patient.patient_id)
        self.assertEqual(second_doctor_page.total_count, 2)
        self.assertEqual(
            [item.patient_id for item in second_doctor_page.items],
            [patient.patient_id, other_patient.patient_id],
        )

    def test_repository_leaves_transaction_control_to_caller(self) -> None:
        statements: list[str] = []
        self.connection.set_trace_callback(statements.append)
        self.connection.execute("BEGIN")

        created = self.create_patient("SYNTH-ROLLBACK")

        self.assertIs(self.patient_repository.connection, self.connection)
        self.assertTrue(self.connection.in_transaction)
        self.assertFalse(
            any(
                statement.strip().upper() in {"COMMIT", "ROLLBACK"}
                for statement in statements[1:]
            )
        )
        self.connection.set_trace_callback(None)
        self.connection.rollback()
        self.assertIsNone(self.patient_repository.find_by_id(created.patient_id))


if __name__ == "__main__":
    unittest.main()
