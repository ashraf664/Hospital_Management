"""SQLite repository for the doctor directory."""

import sqlite3

from models import Doctor
from repositories.base_repository import BaseRepository, SQLiteParameter
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page


_DOCTOR_COLUMNS = (
    "doctor_id, user_id, department_id, full_name, specialty, phone, is_active"
)


class DoctorRepository(BaseRepository):
    """Persist doctor directory entries without managing transactions."""

    def create(self, doctor: Doctor) -> Doctor:
        """Insert a doctor and return the saved database values."""
        cursor = self._execute(
            """
            INSERT INTO doctors (
                user_id, department_id, full_name, specialty, phone, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                doctor.user_id,
                doctor.department_id,
                doctor.full_name,
                doctor.specialty,
                doctor.phone,
                int(doctor.is_active),
            ),
        )
        created = self.find_by_id(int(cursor.lastrowid))
        if created is None:
            raise PersistenceIntegrityError(
                "Inserted doctor could not be read back from SQLite."
            )
        return created

    def update_details(
        self,
        doctor_id: int,
        department_id: int,
        full_name: str,
        specialty: str,
        phone: str | None,
    ) -> Doctor | None:
        """Update directory details without changing the linked user."""
        cursor = self._execute(
            """
            UPDATE doctors
            SET department_id = ?,
                full_name = ?,
                specialty = ?,
                phone = ?
            WHERE doctor_id = ?
            """,
            (department_id, full_name, specialty, phone, doctor_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(doctor_id)

    def deactivate(
        self,
        doctor_id: int,
        *,
        linked_user_was_active: bool | None = None,
    ) -> Doctor | None:
        """Deactivate a doctor and retain the linked account's prior state."""
        if linked_user_was_active is not None and type(linked_user_was_active) is not bool:
            raise TypeError("linked_user_was_active must be a boolean or None.")
        cursor = self._execute(
            """
            UPDATE doctors
            SET is_active = 0,
                account_was_active_before_deactivation = ?
            WHERE doctor_id = ? AND is_active = 1
            """,
            (
                (
                    int(linked_user_was_active)
                    if linked_user_was_active is not None
                    else None
                ),
                doctor_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(doctor_id)

    def activate(self, doctor_id: int) -> Doctor | None:
        """Reactivate a retained doctor and clear its consumed state marker."""
        cursor = self._execute(
            """
            UPDATE doctors
            SET is_active = 1,
                account_was_active_before_deactivation = NULL
            WHERE doctor_id = ? AND is_active = 0
            """,
            (doctor_id,),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(doctor_id)

    def linked_user_was_active_before_deactivation(
        self,
        doctor_id: int,
    ) -> bool | None:
        """Return the saved account state, or None for pre-migration history."""
        row = self._fetchone(
            """
            SELECT account_was_active_before_deactivation
            FROM doctors
            WHERE doctor_id = ? AND is_active = 0
            """,
            (doctor_id,),
        )
        if row is None or row["account_was_active_before_deactivation"] is None:
            return None
        return bool(row["account_was_active_before_deactivation"])

    def find_by_id(self, doctor_id: int) -> Doctor | None:
        """Find a doctor by its primary key."""
        row = self._fetchone(
            f"SELECT {_DOCTOR_COLUMNS} FROM doctors WHERE doctor_id = ?",
            (doctor_id,),
        )
        return self._doctor_from_row(row) if row is not None else None

    def find_by_user_id(self, user_id: int) -> Doctor | None:
        """Find a doctor by its linked user account."""
        row = self._fetchone(
            f"SELECT {_DOCTOR_COLUMNS} FROM doctors WHERE user_id = ?",
            (user_id,),
        )
        return self._doctor_from_row(row) if row is not None else None

    def search(
        self,
        department_id: int | None = None,
        full_name: str | None = None,
        specialty: str | None = None,
        is_active: bool | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Doctor]:
        """Search doctors with optional filters and bounded pagination."""
        Page[Doctor](limit=limit, offset=offset)
        clauses: tuple[str, ...] = ()
        parameters: tuple[SQLiteParameter, ...] = ()
        if department_id is not None:
            clauses += ("department_id = ?",)
            parameters += (department_id,)
        if full_name is not None:
            clauses += ("full_name LIKE ?",)
            parameters += (f"%{full_name}%",)
        if specialty is not None:
            clauses += ("specialty LIKE ?",)
            parameters += (f"%{specialty}%",)
        if is_active is not None:
            clauses += ("is_active = ?",)
            parameters += (int(is_active),)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        count_row = self._fetchone(
            f"SELECT COUNT(*) AS total_count FROM doctors{where_sql}",
            parameters,
        )
        total_count = int(count_row["total_count"]) if count_row is not None else 0
        rows = self._fetchall(
            f"""
            SELECT {_DOCTOR_COLUMNS}
            FROM doctors{where_sql}
            ORDER BY doctor_id ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        )
        items = Page[Doctor](limit=limit, offset=offset).items
        for row in rows:
            items.append(self._doctor_from_row(row))
        return Page(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _doctor_from_row(row: sqlite3.Row) -> Doctor:
        return Doctor(
            doctor_id=int(row["doctor_id"]),
            user_id=int(row["user_id"]),
            department_id=int(row["department_id"]),
            full_name=str(row["full_name"]),
            specialty=str(row["specialty"]),
            phone=row["phone"],
            is_active=bool(row["is_active"]),
        )
