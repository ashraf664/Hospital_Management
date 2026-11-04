"""Tests for shared repository types and SQLite handling."""

import sqlite3
import unittest
from dataclasses import fields

from data_structures import DynamicArray
from models.enums import UserRole
from repositories import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    BaseRepository,
    Page,
    PersistenceConflictError,
    PersistenceConstraintError,
    PersistenceError,
    PersistenceUnavailableError,
    UserSummary,
)


class RepositorySharedComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:", isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.repository = BaseRepository(self.connection)
        self.addCleanup(self.connection.close)

    def test_page_defaults_and_dynamic_array_items(self) -> None:
        page: Page[str] = Page()

        self.assertIsInstance(page.items, DynamicArray)
        self.assertEqual(len(page.items), 0)
        self.assertEqual(page.total_count, 0)
        self.assertEqual(page.limit, DEFAULT_PAGE_LIMIT)
        self.assertEqual(page.limit, 50)
        self.assertEqual(page.offset, 0)
        self.assertEqual(MAX_PAGE_LIMIT, 200)

    def test_page_validates_pagination_and_result_bounds(self) -> None:
        with self.assertRaises(ValueError):
            Page(limit=0)
        with self.assertRaises(ValueError):
            Page(limit=MAX_PAGE_LIMIT + 1)
        with self.assertRaises(ValueError):
            Page(offset=-1)
        with self.assertRaises(TypeError):
            Page(limit=True)
        with self.assertRaises(ValueError):
            Page(items=DynamicArray(), total_count=-1)

        items: DynamicArray[str] = DynamicArray()
        items.append("one")
        items.append("two")
        with self.assertRaises(ValueError):
            Page(items=items, total_count=1, limit=1, offset=0)
        with self.assertRaises(ValueError):
            Page(items=items, total_count=0, limit=1, offset=0)

    def test_user_summary_has_no_password_hash(self) -> None:
        summary = UserSummary(
            user_id=7,
            username="doctor",
            role=UserRole.DOCTOR,
            is_active=True,
        )

        self.assertEqual(
            {field.name for field in fields(UserSummary)},
            {"user_id", "username", "role", "is_active"},
        )
        self.assertFalse(hasattr(summary, "password_hash"))
        self.assertIs(summary.role, UserRole.DOCTOR)
        self.assertIs(summary.is_active, True)

    def test_base_repository_uses_shared_connection_and_does_not_commit(self) -> None:
        self.assertIs(self.repository.connection, self.connection)

        self.connection.execute("BEGIN")
        self.repository._execute("CREATE TABLE sample (value TEXT NOT NULL)")
        self.repository._execute(
            "INSERT INTO sample (value) VALUES (?)",
            ("synthetic",),
        )

        self.assertTrue(self.connection.in_transaction)
        self.connection.rollback()
        table = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "sample"),
        ).fetchone()
        self.assertIsNone(table)

    def test_base_repository_uses_parameterized_queries(self) -> None:
        row = self.repository._fetchone(
            "SELECT ? AS value",
            ("value with ' quotes",),
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "value with ' quotes")

    def test_unique_violation_maps_to_conflict_and_preserves_cause(self) -> None:
        self.connection.execute(
            "CREATE TABLE unique_values (value TEXT NOT NULL UNIQUE)"
        )
        self.repository._execute(
            "INSERT INTO unique_values (value) VALUES (?)",
            ("same",),
        )

        with self.assertRaises(PersistenceConflictError) as raised:
            self.repository._execute(
                "INSERT INTO unique_values (value) VALUES (?)",
                ("same",),
            )

        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)

    def test_foreign_key_violation_maps_to_constraint_and_preserves_cause(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        self.connection.execute(
            "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
        )

        with self.assertRaises(PersistenceConstraintError) as raised:
            self.repository._execute(
                "INSERT INTO child (parent_id) VALUES (?)",
                (42,),
            )

        self.assertNotIsInstance(raised.exception, PersistenceConflictError)
        self.assertIsInstance(raised.exception.__cause__, sqlite3.IntegrityError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)

    def test_sqlite_readonly_error_maps_to_unavailable(self) -> None:
        self.connection.execute("PRAGMA query_only = ON")

        with self.assertRaises(PersistenceUnavailableError) as raised:
            self.repository._execute("CREATE TABLE read_only (id INTEGER)")

        self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)

    def test_general_sqlite_error_maps_to_base_persistence_error(self) -> None:
        with self.assertRaises(PersistenceError) as raised:
            self.repository._execute("SELECT missing_column FROM missing_table")

        self.assertNotIsInstance(raised.exception, PersistenceConstraintError)
        self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)
        self.assertIs(raised.exception.original_cause, raised.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
