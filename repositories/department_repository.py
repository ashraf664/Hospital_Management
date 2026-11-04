"""SQLite repository for hospital departments."""

import sqlite3

from models import Department
from repositories.base_repository import BaseRepository, SQLiteParameter
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page


_DEPARTMENT_COLUMNS = (
    "department_id, name, description, is_active, created_at, updated_at"
)


class DepartmentRepository(BaseRepository):
    """Persist departments while retaining deactivated historical rows."""

    def create(self, department: Department) -> Department:
        """Insert a department and return its database-generated values."""
        cursor = self._execute(
            """
            INSERT INTO departments (name, description, is_active)
            VALUES (?, ?, ?)
            """,
            (
                department.name,
                department.description,
                int(department.is_active),
            ),
        )
        created = self.find_by_id(int(cursor.lastrowid))
        if created is None:
            raise PersistenceIntegrityError(
                "Inserted department could not be read back from SQLite."
            )
        return created

    def update_details(
        self,
        department_id: int,
        name: str,
        description: str,
    ) -> Department | None:
        """Update a department's name and description only."""
        cursor = self._execute(
            """
            UPDATE departments
            SET name = ?,
                description = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE department_id = ?
            """,
            (name, description, department_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(department_id)

    def deactivate(self, department_id: int) -> Department | None:
        """Deactivate a department without deleting its history."""
        cursor = self._execute(
            """
            UPDATE departments
            SET is_active = 0,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE department_id = ?
            """,
            (department_id,),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(department_id)

    def find_by_id(self, department_id: int) -> Department | None:
        """Find one department, returning None when it does not exist."""
        row = self._fetchone(
            f"""
            SELECT {_DEPARTMENT_COLUMNS}
            FROM departments
            WHERE department_id = ?
            """,
            (department_id,),
        )
        return self._department_from_row(row) if row is not None else None

    def search(
        self,
        name: str | None = None,
        is_active: bool | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Department]:
        """Search departments by exact, schema-collated name and active state."""
        Page[Department](limit=limit, offset=offset)
        clauses: tuple[str, ...] = ()
        parameters: tuple[SQLiteParameter, ...] = ()
        if name is not None:
            clauses += ("name = ?",)
            parameters += (name,)
        if is_active is not None:
            clauses += ("is_active = ?",)
            parameters += (int(is_active),)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        count_row = self._fetchone(
            f"SELECT COUNT(*) AS total_count FROM departments{where_sql}",
            parameters,
        )
        total_count = int(count_row["total_count"]) if count_row is not None else 0
        rows = self._fetchall(
            f"""
            SELECT {_DEPARTMENT_COLUMNS}
            FROM departments{where_sql}
            ORDER BY department_id ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        )
        items = Page[Department](limit=limit, offset=offset).items
        for row in rows:
            items.append(self._department_from_row(row))
        return Page(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _department_from_row(row: sqlite3.Row) -> Department:
        return Department(
            department_id=int(row["department_id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
