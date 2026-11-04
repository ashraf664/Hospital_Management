"""SQLite repository for appointment scheduling."""

import sqlite3

from models import Appointment
from repositories.base_repository import BaseRepository, SQLiteParameter
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page


_APPOINTMENT_COLUMNS = (
    "appointment_id, patient_id, doctor_id, scheduled_start, scheduled_end, "
    "status, reason, cancellation_reason, created_by_user_id, created_at, "
    "updated_at"
)


class AppointmentRepository(BaseRepository):
    """Persist appointments without managing authorization or transactions."""

    def create(self, appointment: Appointment) -> Appointment:
        """Insert an appointment and return the saved database values."""
        cursor = self._execute(
            """
            INSERT INTO appointments (
                patient_id, doctor_id, scheduled_start, scheduled_end, status,
                reason, cancellation_reason, created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                appointment.patient_id,
                appointment.doctor_id,
                appointment.scheduled_start,
                appointment.scheduled_end,
                appointment.status,
                appointment.reason,
                appointment.cancellation_reason,
                appointment.created_by_user_id,
            ),
        )
        created = self.find_by_id(int(cursor.lastrowid))
        if created is None:
            raise PersistenceIntegrityError(
                "Inserted appointment could not be read back from SQLite."
            )
        return created

    def find_by_id(self, appointment_id: int) -> Appointment | None:
        """Find one appointment by primary key."""
        row = self._fetchone(
            f"""
            SELECT {_APPOINTMENT_COLUMNS}
            FROM appointments
            WHERE appointment_id = ?
            """,
            (appointment_id,),
        )
        return self._appointment_from_row(row) if row is not None else None

    def reschedule(
        self,
        appointment_id: int,
        scheduled_start: str,
        scheduled_end: str,
    ) -> Appointment | None:
        """Change only appointment start and end times."""
        cursor = self._execute(
            """
            UPDATE appointments
            SET scheduled_start = ?,
                scheduled_end = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE appointment_id = ?
            """,
            (scheduled_start, scheduled_end, appointment_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(appointment_id)

    def update_status(
        self,
        appointment_id: int,
        status: str,
    ) -> Appointment | None:
        """Persist a status string without defining a repository status policy."""
        cursor = self._execute(
            """
            UPDATE appointments
            SET status = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE appointment_id = ?
            """,
            (status, appointment_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(appointment_id)

    def cancel(
        self,
        appointment_id: int,
        cancellation_reason: str | None = None,
    ) -> Appointment | None:
        """Mark an appointment cancelled and preserve its history."""
        cursor = self._execute(
            """
            UPDATE appointments
            SET status = 'cancelled',
                cancellation_reason = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE appointment_id = ?
            """,
            (cancellation_reason, appointment_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(appointment_id)

    def search(
        self,
        patient_id: int | None = None,
        doctor_id: int | None = None,
        start_from: str | None = None,
        start_to: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Appointment]:
        """Search appointments by identity, status, and overlapping time range."""
        Page[Appointment](limit=limit, offset=offset)
        if (
            start_from is not None
            and start_to is not None
            and start_from >= start_to
        ):
            raise ValueError("start_from must be earlier than start_to.")

        clauses: tuple[str, ...] = ()
        parameters: tuple[SQLiteParameter, ...] = ()
        if patient_id is not None:
            clauses += ("patient_id = ?",)
            parameters += (patient_id,)
        if doctor_id is not None:
            clauses += ("doctor_id = ?",)
            parameters += (doctor_id,)
        if start_from is not None and start_to is not None:
            clauses += ("scheduled_start < ? AND scheduled_end > ?",)
            parameters += (start_to, start_from)
        elif start_from is not None:
            clauses += ("scheduled_end > ?",)
            parameters += (start_from,)
        elif start_to is not None:
            clauses += ("scheduled_start < ?",)
            parameters += (start_to,)
        if status is not None:
            clauses += ("status = ?",)
            parameters += (status,)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        count_row = self._fetchone(
            f"SELECT COUNT(*) AS total_count FROM appointments{where_sql}",
            parameters,
        )
        total_count = int(count_row["total_count"]) if count_row is not None else 0
        rows = self._fetchall(
            f"""
            SELECT {_APPOINTMENT_COLUMNS}
            FROM appointments{where_sql}
            ORDER BY scheduled_start ASC, appointment_id ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        )
        items = Page[Appointment](limit=limit, offset=offset).items
        for row in rows:
            items.append(self._appointment_from_row(row))
        return Page(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _appointment_from_row(row: sqlite3.Row) -> Appointment:
        return Appointment(
            appointment_id=int(row["appointment_id"]),
            patient_id=int(row["patient_id"]),
            doctor_id=int(row["doctor_id"]),
            scheduled_start=str(row["scheduled_start"]),
            scheduled_end=str(row["scheduled_end"]),
            status=str(row["status"]),
            reason=(
                str(row["reason"])
                if row["reason"] is not None
                else None
            ),
            cancellation_reason=(
                str(row["cancellation_reason"])
                if row["cancellation_reason"] is not None
                else None
            ),
            created_by_user_id=int(row["created_by_user_id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
