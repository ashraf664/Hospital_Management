"""SQLite-backed tests for user and department repositories."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import Department, User, UserRole
from repositories import (
    DepartmentRepository,
    PersistenceConflictError,
    UserRepository,
    UserSummary,
)


class UserAndDepartmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "repositories.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.user_repository = UserRepository(self.connection)
        self.department_repository = DepartmentRepository(self.connection)
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.connection.close)

    def create_user(
        self,
        username: str,
        role: UserRole = UserRole.RECEPTIONIST,
        *,
        is_active: bool = True,
    ) -> UserSummary:
        return self.user_repository.create(
            User(
                username=username,
                password_hash=f"test-hash-{username}",
                role=role,
                is_active=is_active,
            )
        )

    def create_department(self, name: str, *, is_active: bool = True) -> Department:
        return self.department_repository.create(
            Department(name=name, is_active=is_active)
        )

    def test_user_create_find_and_authentication_mapping(self) -> None:
        traced_statements: list[str] = []
        self.connection.set_trace_callback(traced_statements.append)
        created = self.create_user("doctor", UserRole.DOCTOR)
        display_user = self.user_repository.find_by_id(created.user_id)
        self.connection.set_trace_callback(None)

        self.assertIsInstance(created, UserSummary)
        self.assertIsInstance(created.user_id, int)
        self.assertEqual(created.username, "doctor")
        self.assertIs(created.role, UserRole.DOCTOR)
        self.assertIs(created.is_active, True)
        self.assertFalse(hasattr(created, "password_hash"))
        stored_user = self.connection.execute(
            "SELECT username, role, is_active FROM users WHERE user_id = ?",
            (created.user_id,),
        ).fetchone()
        self.assertEqual(stored_user["username"], created.username)
        self.assertEqual(stored_user["role"], created.role.value)
        self.assertEqual(bool(stored_user["is_active"]), created.is_active)

        self.assertIsInstance(display_user, UserSummary)
        self.assertEqual(display_user.username, "doctor")
        self.assertIs(display_user.role, UserRole.DOCTOR)
        self.assertFalse(hasattr(display_user, "password_hash"))
        user_selects = tuple(
            statement
            for statement in traced_statements
            if statement.lstrip().casefold().startswith("select")
        )
        self.assertTrue(user_selects)
        self.assertFalse(any("password_hash" in statement for statement in user_selects))

        authenticated = self.user_repository.find_for_authentication("doctor")
        self.assertIsInstance(authenticated, User)
        self.assertEqual(authenticated.password_hash, "test-hash-doctor")
        self.assertIsNone(self.user_repository.find_for_authentication("missing"))

    def test_user_update_account_preserves_hash_and_missing_returns_none(self) -> None:
        created = self.create_user("staff")

        updated = self.user_repository.update_account(
            created.user_id,
            "staff-updated",
            UserRole.ADMIN,
        )
        self.assertIsInstance(updated, UserSummary)
        self.assertEqual(updated.username, "staff-updated")
        self.assertIs(updated.role, UserRole.ADMIN)
        self.assertEqual(
            self.user_repository.find_for_authentication("staff-updated").password_hash,
            "test-hash-staff",
        )
        self.assertIsNone(
            self.user_repository.update_account(9999, "missing", UserRole.ADMIN)
        )

    def test_user_deactivate_and_missing_records(self) -> None:
        created = self.create_user("deactivate")

        deactivated = self.user_repository.deactivate(created.user_id)
        self.assertIsNotNone(deactivated)
        self.assertFalse(deactivated.is_active)
        self.assertIsNone(self.user_repository.deactivate(9999))
        self.assertIsNone(self.user_repository.find_by_id(9999))
        self.assertIsNone(self.user_repository.find_for_authentication("missing"))

        stored = self.connection.execute(
            "SELECT is_active FROM users WHERE user_id = ?",
            (created.user_id,),
        ).fetchone()
        self.assertEqual(stored["is_active"], 0)
        self.assertFalse(hasattr(self.user_repository, "delete"))

    def test_has_admin_account_includes_inactive_admin(self) -> None:
        self.assertFalse(self.user_repository.has_admin_account())
        self.create_user("inactive-admin", UserRole.ADMIN, is_active=False)
        self.assertTrue(self.user_repository.has_admin_account())

    def test_user_search_paginates_stably_and_omits_password_hash(self) -> None:
        created = (
            self.create_user("page-one", UserRole.ADMIN),
            self.create_user("page-two", UserRole.DOCTOR),
            self.create_user("page-three", UserRole.RECEPTIONIST),
        )
        traced_statements: list[str] = []
        self.connection.set_trace_callback(traced_statements.append)

        first_page = self.user_repository.search(limit=2, offset=0)
        second_page = self.user_repository.search(limit=2, offset=2)
        filtered_page = self.user_repository.search(role=UserRole.DOCTOR)
        maximum_page = self.user_repository.search(limit=200)

        self.connection.set_trace_callback(None)
        self.assertEqual(first_page.total_count, 3)
        self.assertEqual(first_page.limit, 2)
        self.assertEqual(first_page.offset, 0)
        self.assertEqual(
            [item.user_id for item in first_page.items],
            [created[0].user_id, created[1].user_id],
        )
        self.assertEqual(
            [item.user_id for item in second_page.items],
            [created[2].user_id],
        )
        self.assertEqual(second_page.total_count, 3)
        self.assertEqual(filtered_page.total_count, 1)
        self.assertIs(filtered_page.items.get(0).role, UserRole.DOCTOR)
        self.assertEqual(maximum_page.limit, 200)
        self.assertEqual(maximum_page.total_count, 3)
        select_statements = (
            statement.casefold()
            for statement in traced_statements
            if statement.lstrip().casefold().startswith("select")
        )
        self.assertTrue(tuple(select_statements))
        self.assertFalse(
            any("password_hash" in statement for statement in traced_statements)
        )

    def test_user_search_filters_and_rejects_invalid_pagination(self) -> None:
        self.create_user("active")
        self.create_user("inactive", is_active=False)

        result = self.user_repository.search(
            username="inactive",
            is_active=False,
        )
        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.items.get(0).username, "inactive")

        for kwargs in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.user_repository.search(**kwargs)

    def test_user_unique_constraint_is_translated_and_original_is_preserved(self) -> None:
        self.create_user("duplicate-user")

        with self.assertRaises(PersistenceConflictError) as raised:
            self.create_user("duplicate-user")

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)

    def test_department_create_find_update_and_deactivate(self) -> None:
        created = self.create_department("Cardiology")

        self.assertIsInstance(created.department_id, int)
        self.assertEqual(created.name, "Cardiology")
        self.assertEqual(created.description, "")
        self.assertTrue(created.is_active)
        self.assertIsNotNone(created.created_at)
        self.assertIsNotNone(created.updated_at)
        self.assertEqual(
            self.department_repository.find_by_id(created.department_id),
            created,
        )

        updated = self.department_repository.update_details(
            created.department_id,
            "Cardiology Services",
            "Synthetic department description",
        )
        self.assertEqual(updated.name, "Cardiology Services")
        self.assertEqual(updated.description, "Synthetic department description")
        self.assertIsNone(
            self.department_repository.update_details(
                9999,
                "Missing",
                "No department",
            )
        )

        deactivated = self.department_repository.deactivate(created.department_id)
        self.assertIsNotNone(deactivated)
        self.assertFalse(deactivated.is_active)
        self.assertIsNone(self.department_repository.deactivate(9999))
        self.assertIsNone(self.department_repository.find_by_id(9999))
        self.assertFalse(hasattr(self.department_repository, "delete"))

    def test_department_search_paginates_with_stable_primary_key_order(self) -> None:
        departments = (
            self.create_department("Alpha"),
            self.create_department("Beta"),
            self.create_department("Gamma"),
        )

        page = self.department_repository.search(limit=2, offset=1)
        self.assertEqual(page.total_count, 3)
        self.assertEqual(page.limit, 2)
        self.assertEqual(page.offset, 1)
        self.assertEqual(
            [department.department_id for department in page.items],
            [departments[1].department_id, departments[2].department_id],
        )

        filtered = self.department_repository.search(name="Beta")
        self.assertEqual(filtered.total_count, 1)
        self.assertEqual(filtered.items.get(0).name, "Beta")
        self.assertEqual(
            self.department_repository.search(limit=200).total_count,
            3,
        )

        for kwargs in (
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.department_repository.search(**kwargs)

    def test_department_unique_constraint_and_case_sensitive_filter(self) -> None:
        self.create_department("Radiology")

        with self.assertRaises(PersistenceConflictError):
            self.create_department("Radiology")

        self.assertEqual(
            self.department_repository.search(name="radiology").total_count,
            0,
        )

    def test_repositories_do_not_commit_or_rollback_shared_transactions(self) -> None:
        self.connection.execute("BEGIN")
        self.create_user("rolled-back-user")
        self.create_department("Rolled Back")

        self.assertTrue(self.connection.in_transaction)
        self.connection.rollback()

        self.assertIsNone(self.user_repository.find_for_authentication("rolled-back-user"))
        self.assertEqual(
            self.department_repository.search(name="Rolled Back").total_count,
            0,
        )


if __name__ == "__main__":
    unittest.main()
