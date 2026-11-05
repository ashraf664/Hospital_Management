"""SQLite-backed tests for AppointmentRepository."""

from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import Appointment, Department, Doctor, Patient, User, UserRole
from repositories import (
    AppointmentRepository,
    DepartmentRepository,
    DoctorRepository,
    PatientRepository,
    PersistenceConstraintError,
    UserRepository,
)


class AppointmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "appointments.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.user_repository = UserRepository(self.connection)
        self.department_repository = DepartmentRepository(self.connection)
        self.doctor_repository = DoctorRepository(self.connection)
        self.patient_repository = PatientRepository(self.connection)
        self.appointment_repository = AppointmentRepository(self.connection)
        self.creator_user_id = self.create_user("test-reception", UserRole.RECEPTIONIST)
        self.doctor_id = self.create_doctor("appointment-doctor")
        self.patient_id = self.create_patient("SYNTH-APPOINTMENT-001")
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
                full_name="Synthetic Appointment Patient",
                date_of_birth="1980-01-02",
            )
        )
        return patient.patient_id

    def create_appointment(
        self,
        *,
        patient_id: int | None = None,
        doctor_id: int | None = None,
        scheduled_start: str = "2030-01-02T10:00:00Z",
        scheduled_end: str = "2030-01-02T10:30:00Z",
        status: str = "scheduled",
        reason: str | None = None,
        cancellation_reason: str | None = None,
        created_by_user_id: int | None = None,
    ) -> Appointment:
        return self.appointment_repository.create(
            Appointment(
                patient_id=self.patient_id if patient_id is None else patient_id,
                doctor_id=self.doctor_id if doctor_id is None else doctor_id,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                status=status,
                reason=reason,
                cancellation_reason=cancellation_reason,
                created_by_user_id=(
                    self.creator_user_id
                    if created_by_user_id is None
                    else created_by_user_id
                ),
            )
        )

    def test_create_reads_saved_appointment_optional_values_and_timestamps(self) -> None:
        created = self.create_appointment()

        self.assertIsInstance(created.appointment_id, int)
        self.assertEqual(created.patient_id, self.patient_id)
        self.assertEqual(created.doctor_id, self.doctor_id)
        self.assertEqual(created.scheduled_start, "2030-01-02T10:00:00Z")
        self.assertEqual(created.scheduled_end, "2030-01-02T10:30:00Z")
        self.assertEqual(created.status, "scheduled")
        self.assertIsNone(created.reason)
        self.assertIsNone(created.cancellation_reason)
        self.assertEqual(created.created_by_user_id, self.creator_user_id)
        self.assertIsNotNone(created.created_at)
        self.assertIsNotNone(created.updated_at)
        self.assertRegex(created.created_at, r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertRegex(created.updated_at, r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertEqual(
            self.appointment_repository.find_by_id(created.appointment_id),
            created,
        )

    def test_find_by_id_returns_none_for_missing_appointment(self) -> None:
        self.assertIsNone(self.appointment_repository.find_by_id(9999))

    def test_reschedule_changes_only_times_and_updates_timestamp(self) -> None:
        created = self.create_appointment(
            reason="Synthetic visit reason",
            cancellation_reason="No cancellation",
        )
        time.sleep(0.02)

        updated = self.appointment_repository.reschedule(
            created.appointment_id,
            "2030-01-02T11:00:00Z",
            "2030-01-02T11:45:00Z",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.scheduled_start, "2030-01-02T11:00:00Z")
        self.assertEqual(updated.scheduled_end, "2030-01-02T11:45:00Z")
        self.assertEqual(updated.patient_id, created.patient_id)
        self.assertEqual(updated.doctor_id, created.doctor_id)
        self.assertEqual(updated.reason, created.reason)
        self.assertEqual(updated.cancellation_reason, created.cancellation_reason)
        self.assertEqual(updated.created_by_user_id, created.created_by_user_id)
        self.assertEqual(updated.created_at, created.created_at)
        self.assertGreater(updated.updated_at, created.updated_at)
        self.assertIsNone(
            self.appointment_repository.reschedule(
                9999,
                "2030-01-02T12:00:00Z",
                "2030-01-02T12:30:00Z",
            )
        )

    def test_update_status_persists_text_and_returns_none_for_missing_id(self) -> None:
        created = self.create_appointment()

        updated = self.appointment_repository.update_status(
            created.appointment_id,
            "Completed",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "Completed")
        self.assertIsNone(self.appointment_repository.update_status(9999, "Any"))

    def test_cancel_retains_appointment_and_accepts_optional_reason(self) -> None:
        created = self.create_appointment()

        cancelled = self.appointment_repository.cancel(created.appointment_id)

        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.status, "Cancelled")
        self.assertIsNone(cancelled.cancellation_reason)
        self.assertEqual(cancelled.appointment_id, created.appointment_id)
        self.assertIsNone(self.appointment_repository.cancel(9999))
        with_reason = self.appointment_repository.cancel(
            created.appointment_id,
            "Synthetic cancellation reason",
        )
        self.assertEqual(
            with_reason.cancellation_reason,
            "Synthetic cancellation reason",
        )
        self.assertEqual(
            self.appointment_repository.find_by_id(created.appointment_id),
            with_reason,
        )

    def test_search_filters_individually_and_combines_filters(self) -> None:
        second_patient_id = self.create_patient("SYNTH-APPOINTMENT-002")
        second_doctor_id = self.create_doctor("appointment-doctor-two")
        matching = self.create_appointment(
            scheduled_start="2030-01-02T10:00:00Z",
            scheduled_end="2030-01-02T10:30:00Z",
            status="scheduled",
        )
        self.create_appointment(
            patient_id=second_patient_id,
            scheduled_start="2030-01-02T11:00:00Z",
            scheduled_end="2030-01-02T11:30:00Z",
            status="confirmed",
        )
        self.create_appointment(
            doctor_id=second_doctor_id,
            scheduled_start="2030-01-02T12:00:00Z",
            scheduled_end="2030-01-02T12:30:00Z",
            status="scheduled",
        )

        self.assertEqual(
            self.appointment_repository.search(patient_id=self.patient_id).total_count,
            2,
        )
        self.assertEqual(
            self.appointment_repository.search(doctor_id=second_doctor_id).total_count,
            1,
        )
        self.assertEqual(
            self.appointment_repository.search(status="confirmed").total_count,
            1,
        )
        combined = self.appointment_repository.search(
            patient_id=self.patient_id,
            doctor_id=self.doctor_id,
            status="scheduled",
        )
        self.assertEqual(combined.total_count, 1)
        self.assertEqual(combined.items.get(0), matching)

    def test_search_time_range_with_both_bounds_finds_overlapping_appointments(self) -> None:
        overlaps = self.create_appointment(
            scheduled_start="2030-01-02T09:30:00Z",
            scheduled_end="2030-01-02T10:15:00Z",
        )
        self.create_appointment(
            scheduled_start="2030-01-02T10:30:00Z",
            scheduled_end="2030-01-02T11:00:00Z",
        )

        result = self.appointment_repository.search(
            start_from="2030-01-02T10:00:00Z",
            start_to="2030-01-02T10:30:00Z",
        )

        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.items.get(0), overlaps)

    def test_search_time_range_accepts_either_single_bound(self) -> None:
        first = self.create_appointment(
            scheduled_start="2030-01-02T09:00:00Z",
            scheduled_end="2030-01-02T10:00:00Z",
        )
        second = self.create_appointment(
            scheduled_start="2030-01-02T11:00:00Z",
            scheduled_end="2030-01-02T12:00:00Z",
        )

        after = self.appointment_repository.search(
            start_from="2030-01-02T10:30:00Z"
        )
        before = self.appointment_repository.search(
            start_to="2030-01-02T11:30:00Z"
        )

        self.assertEqual(after.total_count, 1)
        self.assertEqual(after.items.get(0), second)
        self.assertEqual(before.total_count, 2)
        self.assertEqual(
            [item.appointment_id for item in before.items],
            [first.appointment_id, second.appointment_id],
        )

    def test_search_rejects_empty_or_reversed_time_ranges(self) -> None:
        with self.assertRaises(ValueError):
            self.appointment_repository.search(
                start_from="2030-01-02T10:00:00Z",
                start_to="2030-01-02T10:00:00Z",
            )
        with self.assertRaises(ValueError):
            self.appointment_repository.search(
                start_from="2030-01-02T11:00:00Z",
                start_to="2030-01-02T10:00:00Z",
            )

    def test_search_paginates_with_total_count_and_stable_ordering(self) -> None:
        appointments = (
            self.create_appointment(
                scheduled_start="2030-01-02T10:00:00Z",
                scheduled_end="2030-01-02T10:30:00Z",
            ),
            self.create_appointment(
                doctor_id=self.create_doctor("appointment-page-doctor-two"),
                scheduled_start="2030-01-02T11:00:00Z",
                scheduled_end="2030-01-02T11:30:00Z",
            ),
            self.create_appointment(
                scheduled_start="2030-01-02T11:00:00Z",
                scheduled_end="2030-01-02T11:45:00Z",
            ),
        )
        first_page = self.appointment_repository.search(limit=2)
        second_page = self.appointment_repository.search(limit=2, offset=2)
        empty_page = self.appointment_repository.search(limit=2, offset=10)

        self.assertEqual(first_page.total_count, 3)
        self.assertEqual(first_page.limit, 2)
        self.assertEqual(first_page.offset, 0)
        self.assertEqual(
            [item.appointment_id for item in first_page.items],
            [appointments[0].appointment_id, appointments[1].appointment_id],
        )
        self.assertEqual(
            [item.appointment_id for item in second_page.items],
            [appointments[2].appointment_id],
        )
        self.assertEqual(second_page.total_count, 3)
        self.assertEqual(empty_page.total_count, 3)
        self.assertEqual(len(empty_page.items), 0)
        for kwargs in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.appointment_repository.search(**kwargs)

    def test_search_applies_filters_to_count_and_results(self) -> None:
        self.create_appointment(status="scheduled")
        self.create_appointment(
            scheduled_start="2030-01-02T11:00:00Z",
            scheduled_end="2030-01-02T11:30:00Z",
            status="completed",
        )

        result = self.appointment_repository.search(
            patient_id=self.patient_id,
            doctor_id=self.doctor_id,
            start_from="2030-01-02T09:00:00Z",
            start_to="2030-01-02T10:30:00Z",
            status="scheduled",
            limit=1,
        )

        self.assertEqual(result.total_count, 1)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items.get(0).status, "scheduled")

    def test_invalid_times_and_foreign_keys_raise_persistence_constraints(self) -> None:
        with self.assertRaises(PersistenceConstraintError) as invalid_timestamp:
            self.create_appointment(
                scheduled_start="not-a-timestamp",
                scheduled_end="2030-01-02T10:30:00Z",
            )
        self.assertIsInstance(
            invalid_timestamp.exception.__cause__,
            sqlite3.IntegrityError,
        )
        self.assertIs(
            invalid_timestamp.exception.original_cause,
            invalid_timestamp.exception.__cause__,
        )

        with self.assertRaises(PersistenceConstraintError) as invalid_duration:
            self.create_appointment(
                scheduled_start="2030-01-02T10:30:00Z",
                scheduled_end="2030-01-02T10:30:00Z",
            )
        self.assertIsInstance(
            invalid_duration.exception.__cause__,
            sqlite3.IntegrityError,
        )

        for values in (
            {"patient_id": 9999},
            {"doctor_id": 9999},
            {"created_by_user_id": 9999},
        ):
            with self.subTest(values=values), self.assertRaises(
                PersistenceConstraintError
            ) as foreign_key:
                self.create_appointment(**values)
            self.assertIsInstance(foreign_key.exception.__cause__, sqlite3.IntegrityError)

        with self.assertRaises(PersistenceConstraintError) as blank_status:
            self.create_appointment(status="   ")
        self.assertIsInstance(blank_status.exception.__cause__, sqlite3.IntegrityError)

    def test_doctor_overlap_trigger_rejects_conflict_and_preserves_cause(self) -> None:
        self.create_appointment()

        with self.assertRaises(PersistenceConstraintError) as conflict:
            self.create_appointment(
                patient_id=self.create_patient("SYNTH-OVERLAP-002"),
                scheduled_start="2030-01-02T10:15:00Z",
                scheduled_end="2030-01-02T10:45:00Z",
            )

        self.assertIsInstance(conflict.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(conflict.exception.original_cause, conflict.exception.__cause__)

    def test_back_to_back_appointments_are_allowed(self) -> None:
        first = self.create_appointment()
        second = self.create_appointment(
            patient_id=self.create_patient("SYNTH-BACK-TO-BACK"),
            scheduled_start=first.scheduled_end,
            scheduled_end="2030-01-02T11:00:00Z",
        )

        self.assertNotEqual(first.appointment_id, second.appointment_id)

    def test_cancelled_appointment_releases_doctor_time_slot(self) -> None:
        cancelled = self.create_appointment()
        self.appointment_repository.cancel(cancelled.appointment_id)

        replacement = self.create_appointment(
            patient_id=self.create_patient("SYNTH-REPLACEMENT"),
            scheduled_start=cancelled.scheduled_start,
            scheduled_end=cancelled.scheduled_end,
        )

        self.assertNotEqual(cancelled.appointment_id, replacement.appointment_id)

    def test_overlapping_patient_appointments_with_different_doctors_are_allowed(self) -> None:
        first = self.create_appointment()
        second_doctor_id = self.create_doctor("appointment-other-doctor")

        second = self.create_appointment(
            doctor_id=second_doctor_id,
            scheduled_start=first.scheduled_start,
            scheduled_end=first.scheduled_end,
        )

        self.assertEqual(second.patient_id, first.patient_id)
        self.assertNotEqual(second.doctor_id, first.doctor_id)

    def test_repository_leaves_transaction_control_to_caller(self) -> None:
        statements: list[str] = []
        self.connection.set_trace_callback(statements.append)
        self.connection.execute("BEGIN")

        created = self.create_appointment()

        self.assertIs(self.appointment_repository.connection, self.connection)
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
            self.appointment_repository.find_by_id(created.appointment_id)
        )


if __name__ == "__main__":
    unittest.main()
