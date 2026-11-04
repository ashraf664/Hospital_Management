"""SQLite-backed tests for DoctorRepository."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import Department, Doctor, User, UserRole
from repositories import (
    DepartmentRepository,
    DoctorRepository,
    PersistenceConflictError,
    PersistenceConstraintError,
    UserRepository,
)


class DoctorRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "doctors.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.user_repository = UserRepository(self.connection)
        self.department_repository = DepartmentRepository(self.connection)
        self.doctor_repository = DoctorRepository(self.connection)
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.connection.close)

    def create_user(
        self,
        username: str,
        role: UserRole = UserRole.DOCTOR,
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

    def create_department(self, name: str) -> int:
        department = self.department_repository.create(Department(name=name))
        return department.department_id

    def create_doctor(
        self,
        username: str,
        department_id: int | None = None,
        *,
        full_name: str = "Synthetic Doctor",
        specialty: str = "General Medicine",
        phone: str | None = "555-0100",
        is_active: bool = True,
        role: UserRole = UserRole.DOCTOR,
        user_is_active: bool = True,
    ) -> Doctor:
        if department_id is None:
            department_id = self.create_department(f"Department for {username}")
        return self.doctor_repository.create(
            Doctor(
                user_id=self.create_user(
                    username,
                    role,
                    is_active=user_is_active,
                ),
                department_id=department_id,
                full_name=full_name,
                specialty=specialty,
                phone=phone,
                is_active=is_active,
            )
        )

    def test_create_returns_saved_doctor_with_nullable_phone_and_boolean(self) -> None:
        department_id = self.create_department("Synthetic Cardiology")
        user_id = self.create_user("doctor-create", is_active=False)

        created = self.doctor_repository.create(
            Doctor(
                user_id=user_id,
                department_id=department_id,
                full_name="Synthetic Cardiologist",
                specialty="Cardiology",
                phone=None,
                is_active=False,
            )
        )

        self.assertIsInstance(created, Doctor)
        self.assertIsInstance(created.doctor_id, int)
        self.assertEqual(created.user_id, user_id)
        self.assertEqual(created.department_id, department_id)
        self.assertEqual(created.full_name, "Synthetic Cardiologist")
        self.assertEqual(created.specialty, "Cardiology")
        self.assertIsNone(created.phone)
        self.assertIs(created.is_active, False)
        self.assertEqual(self.doctor_repository.find_by_id(created.doctor_id), created)

    def test_find_by_id_and_user_id_return_none_for_missing_doctors(self) -> None:
        created = self.create_doctor("doctor-find")

        self.assertEqual(
            self.doctor_repository.find_by_id(created.doctor_id),
            created,
        )
        self.assertEqual(
            self.doctor_repository.find_by_user_id(created.user_id),
            created,
        )
        self.assertIsNone(self.doctor_repository.find_by_id(9999))
        self.assertIsNone(self.doctor_repository.find_by_user_id(9999))

    def test_update_details_changes_only_directory_fields(self) -> None:
        created = self.create_doctor("doctor-update")
        other_department_id = self.create_department("Synthetic Neurology")

        updated = self.doctor_repository.update_details(
            created.doctor_id,
            other_department_id,
            "Updated Synthetic Doctor",
            "Neurology",
            None,
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.doctor_id, created.doctor_id)
        self.assertEqual(updated.user_id, created.user_id)
        self.assertEqual(updated.department_id, other_department_id)
        self.assertEqual(updated.full_name, "Updated Synthetic Doctor")
        self.assertEqual(updated.specialty, "Neurology")
        self.assertIsNone(updated.phone)
        self.assertIs(updated.is_active, True)
        self.assertIsNone(
            self.doctor_repository.update_details(
                9999,
                other_department_id,
                "Missing Doctor",
                "Neurology",
                None,
            )
        )

    def test_deactivate_preserves_user_account_and_does_not_delete_doctor(self) -> None:
        created = self.create_doctor(
            "doctor-deactivate",
            user_is_active=True,
        )

        deactivated = self.doctor_repository.deactivate(created.doctor_id)

        self.assertIsNotNone(deactivated)
        self.assertIs(deactivated.is_active, False)
        self.assertIs(self.user_repository.find_by_id(created.user_id).is_active, True)
        self.assertIsNone(self.doctor_repository.deactivate(9999))
        self.assertFalse(hasattr(self.doctor_repository, "delete"))
        stored = self.connection.execute(
            "SELECT doctor_id, is_active FROM doctors WHERE doctor_id = ?",
            (created.doctor_id,),
        ).fetchone()
        self.assertEqual(stored["doctor_id"], created.doctor_id)
        self.assertEqual(stored["is_active"], 0)

    def test_search_supports_partial_name_and_specialty_matching(self) -> None:
        self.create_doctor(
            "doctor-search-one",
            full_name="Alexandra Synthetic",
            specialty="Cardiothoracic Surgery",
        )
        self.create_doctor(
            "doctor-search-two",
            full_name="Jordan Synthetic",
            specialty="Neurology",
        )

        by_name = self.doctor_repository.search(full_name="andra Syn")
        by_specialty = self.doctor_repository.search(specialty="thoracic Sur")

        self.assertEqual(by_name.total_count, 1)
        self.assertEqual(by_name.items.get(0).full_name, "Alexandra Synthetic")
        self.assertEqual(by_specialty.total_count, 1)
        self.assertEqual(
            by_specialty.items.get(0).specialty,
            "Cardiothoracic Surgery",
        )

    def test_search_combines_department_and_active_filters(self) -> None:
        department_id = self.create_department("Synthetic Search Department")
        matching = self.create_doctor(
            "doctor-filter-match",
            department_id,
            full_name="Casey Synthetic",
            specialty="Family Medicine",
        )
        self.create_doctor(
            "doctor-filter-inactive",
            department_id,
            full_name="Casey Inactive",
            specialty="Family Medicine",
            is_active=False,
        )
        self.create_doctor(
            "doctor-filter-other-department",
            full_name="Casey Other",
            specialty="Family Medicine",
        )

        result = self.doctor_repository.search(
            department_id=department_id,
            full_name="Casey",
            specialty="Family",
            is_active=True,
        )

        self.assertEqual(result.total_count, 1)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items.get(0), matching)

    def test_search_paginates_stably_and_counts_before_pagination(self) -> None:
        doctors = (
            self.create_doctor("doctor-page-one", full_name="Same Name"),
            self.create_doctor("doctor-page-two", full_name="Same Name"),
            self.create_doctor("doctor-page-three", full_name="Same Name"),
        )

        first_page = self.doctor_repository.search(full_name="Same", limit=2)
        second_page = self.doctor_repository.search(
            full_name="Same",
            limit=2,
            offset=2,
        )
        beyond_page = self.doctor_repository.search(
            full_name="Same",
            limit=2,
            offset=5,
        )
        default_page = self.doctor_repository.search()
        maximum_page = self.doctor_repository.search(limit=200)

        self.assertEqual(first_page.total_count, 3)
        self.assertEqual(first_page.limit, 2)
        self.assertEqual(first_page.offset, 0)
        self.assertEqual(
            [doctor.doctor_id for doctor in first_page.items],
            [doctors[0].doctor_id, doctors[1].doctor_id],
        )
        self.assertEqual(
            [doctor.doctor_id for doctor in second_page.items],
            [doctors[2].doctor_id],
        )
        self.assertEqual(second_page.total_count, 3)
        self.assertEqual(len(beyond_page.items), 0)
        self.assertEqual(beyond_page.total_count, 3)
        self.assertEqual(default_page.limit, 50)
        self.assertEqual(maximum_page.limit, 200)

        for kwargs in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.doctor_repository.search(**kwargs)

    def test_missing_user_and_department_and_non_doctor_role_are_constraints(self) -> None:
        department_id = self.create_department("Synthetic Valid Department")
        missing_user = self.doctor_repository.create

        with self.assertRaises(PersistenceConstraintError):
            missing_user(
                Doctor(
                    user_id=9999,
                    department_id=department_id,
                    full_name="Missing User Doctor",
                    specialty="Synthetic Specialty",
                )
            )

        non_doctor_user_id = self.create_user(
            "receptionist-profile",
            UserRole.RECEPTIONIST,
        )
        with self.assertRaises(PersistenceConstraintError):
            self.doctor_repository.create(
                Doctor(
                    user_id=non_doctor_user_id,
                    department_id=department_id,
                    full_name="Wrong Role Doctor",
                    specialty="Synthetic Specialty",
                )
            )

        doctor_user_id = self.create_user("missing-department-doctor")
        with self.assertRaises(PersistenceConstraintError):
            self.doctor_repository.create(
                Doctor(
                    user_id=doctor_user_id,
                    department_id=9999,
                    full_name="Missing Department Doctor",
                    specialty="Synthetic Specialty",
                )
            )

    def test_duplicate_user_and_empty_required_fields_keep_sqlite_causes(self) -> None:
        created = self.create_doctor("doctor-unique")
        with self.assertRaises(PersistenceConflictError) as duplicate:
            self.doctor_repository.create(
                Doctor(
                    user_id=created.user_id,
                    department_id=created.department_id,
                    full_name="Duplicate Synthetic Doctor",
                    specialty="Synthetic Specialty",
                )
            )
        self.assertIsInstance(duplicate.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(
            duplicate.exception.original_cause,
            duplicate.exception.__cause__,
        )

        for field_values in (
            {"full_name": "   ", "specialty": "Synthetic Specialty"},
            {"full_name": "Synthetic Doctor", "specialty": "   "},
        ):
            with self.subTest(field_values=field_values):
                user_id = self.create_user(
                    f"doctor-check-{len(field_values)}-{field_values['full_name']!r}"
                )
                with self.assertRaises(PersistenceConstraintError) as rejected:
                    self.doctor_repository.create(
                        Doctor(
                            user_id=user_id,
                            department_id=created.department_id,
                            **field_values,
                        )
                    )
                self.assertIsInstance(
                    rejected.exception.__cause__,
                    sqlite3.IntegrityError,
                )
                self.assertIs(
                    rejected.exception.original_cause,
                    rejected.exception.__cause__,
                )

    def test_repository_leaves_transaction_control_to_caller(self) -> None:
        department_id = self.create_department("Synthetic Transaction Department")
        user_id = self.create_user("doctor-transaction")
        statements: list[str] = []
        self.connection.set_trace_callback(statements.append)
        self.connection.execute("BEGIN")

        created = self.doctor_repository.create(
            Doctor(
                user_id=user_id,
                department_id=department_id,
                full_name="Transactional Synthetic Doctor",
                specialty="Synthetic Specialty",
            )
        )

        repository_statements = tuple(statements[1:])
        self.assertIs(self.doctor_repository.connection, self.connection)
        self.assertTrue(self.connection.in_transaction)
        self.assertFalse(
            any(
                statement.strip().upper() in {"COMMIT", "ROLLBACK"}
                for statement in repository_statements
            )
        )
        self.connection.set_trace_callback(None)
        self.connection.rollback()
        self.assertIsNone(self.doctor_repository.find_by_id(created.doctor_id))


if __name__ == "__main__":
    unittest.main()
