"""SQLite repository for emergency case intake and lookup."""

import sqlite3

from models import EmergencyCase
from repositories.base_repository import BaseRepository, SQLiteParameter
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page


_EMERGENCY_CASE_COLUMNS = (
    "emergency_case_id, case_number, patient_id, assigned_doctor_id, "
    "intake_user_id, triage_category, status, arrival_at, closed_at, "
    "intake_notes, created_at, updated_at"
)


class EmergencyCaseRepository(BaseRepository):
    """Persist emergency cases without managing authorization or transactions."""

    def create(self, case: EmergencyCase) -> EmergencyCase:
        """Insert an emergency case and return its saved database values."""
        cursor = self._execute(
            """
            INSERT INTO emergency_cases (
                case_number, patient_id, assigned_doctor_id, intake_user_id,
                triage_category, status, arrival_at, closed_at, intake_notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.case_number,
                case.patient_id,
                case.assigned_doctor_id,
                case.intake_user_id,
                case.triage_category,
                case.status,
                case.arrival_at,
                case.closed_at,
                case.intake_notes,
            ),
        )
        created = self.find_by_id(int(cursor.lastrowid))
        if created is None:
            raise PersistenceIntegrityError(
                "Inserted emergency case could not be read back from SQLite."
            )
        return created

    def find_by_id(self, emergency_case_id: int) -> EmergencyCase | None:
        """Find an emergency case by primary key."""
        row = self._fetchone(
            f"""
            SELECT {_EMERGENCY_CASE_COLUMNS}
            FROM emergency_cases
            WHERE emergency_case_id = ?
            """,
            (emergency_case_id,),
        )
        return self._case_from_row(row) if row is not None else None

    def find_by_case_number(self, case_number: str) -> EmergencyCase | None:
        """Find an emergency case by its exact unique case number."""
        row = self._fetchone(
            f"""
            SELECT {_EMERGENCY_CASE_COLUMNS}
            FROM emergency_cases
            WHERE case_number = ?
            """,
            (case_number,),
        )
        return self._case_from_row(row) if row is not None else None

    def find_for_doctor(
        self,
        emergency_case_id: int,
        doctor_id: int,
    ) -> EmergencyCase | None:
        """Find a case assigned to the specified current doctor."""
        row = self._fetchone(
            f"""
            SELECT {_EMERGENCY_CASE_COLUMNS}
            FROM emergency_cases
            WHERE emergency_case_id = ?
              AND assigned_doctor_id = ?
            """,
            (emergency_case_id, doctor_id),
        )
        return self._case_from_row(row) if row is not None else None

    def link_patient(
        self,
        emergency_case_id: int,
        patient_id: int,
        *,
        actor_user_id: int,
        audit_log_id: int,
        change_reason: str,
        event_at: str,
    ) -> EmergencyCase | None:
        """Record a patient link; the database trigger updates the case."""
        case = self.find_by_id(emergency_case_id)
        if case is None:
            return None

        version_row = self._fetchone(
            """
            SELECT COALESCE(MAX(version_no), 0) + 1 AS next_version
            FROM emergency_intake_history
            WHERE emergency_case_id = ?
            """,
            (emergency_case_id,),
        )
        if version_row is None:
            raise PersistenceIntegrityError(
                "Emergency intake history version could not be determined."
            )

        self._execute(
            """
            INSERT INTO emergency_intake_history (
                emergency_case_id, version_no, previous_case_number_snapshot,
                case_number_snapshot, previous_patient_id_snapshot,
                patient_id_snapshot, previous_intake_user_id_snapshot,
                intake_user_id_snapshot, previous_arrival_at_snapshot,
                arrival_at_snapshot, intake_notes_snapshot,
                previous_intake_notes_snapshot, event_type, change_reason,
                record_origin, event_at, actor_user_id, audit_log_id
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                'patient_linked', ?, 'application_event', ?, ?, ?
            )
            """,
            (
                emergency_case_id,
                int(version_row["next_version"]),
                case.case_number,
                case.case_number,
                case.patient_id,
                patient_id,
                case.intake_user_id,
                case.intake_user_id,
                case.arrival_at,
                case.arrival_at,
                case.intake_notes,
                case.intake_notes,
                change_reason,
                event_at,
                actor_user_id,
                audit_log_id,
            ),
        )
        return self.find_by_id(emergency_case_id)

    def search(
        self,
        case_number: str | None = None,
        patient_id: int | None = None,
        assigned_doctor_id: int | None = None,
        arrival_date: str | None = None,
        status: str | None = None,
        triage_category: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[EmergencyCase]:
        """Search emergency cases using exact filters and bounded pagination."""
        Page[EmergencyCase](limit=limit, offset=offset)
        clauses: tuple[str, ...] = ()
        parameters: tuple[SQLiteParameter, ...] = ()
        if case_number is not None:
            clauses += ("case_number = ?",)
            parameters += (case_number,)
        if patient_id is not None:
            clauses += ("patient_id = ?",)
            parameters += (patient_id,)
        if assigned_doctor_id is not None:
            clauses += ("assigned_doctor_id = ?",)
            parameters += (assigned_doctor_id,)
        if arrival_date is not None:
            clauses += ("substr(arrival_at, 1, 10) = ?",)
            parameters += (arrival_date,)
        if status is not None:
            clauses += ("status = ?",)
            parameters += (status,)
        if triage_category is not None:
            clauses += ("triage_category = ?",)
            parameters += (triage_category,)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        count_row = self._fetchone(
            f"SELECT COUNT(*) AS total_count FROM emergency_cases{where_sql}",
            parameters,
        )
        total_count = int(count_row["total_count"]) if count_row is not None else 0
        rows = self._fetchall(
            f"""
            SELECT {_EMERGENCY_CASE_COLUMNS}
            FROM emergency_cases{where_sql}
            ORDER BY arrival_at DESC, emergency_case_id ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        )
        items = Page[EmergencyCase](limit=limit, offset=offset).items
        for row in rows:
            items.append(self._case_from_row(row))
        return Page(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> EmergencyCase:
        return EmergencyCase(
            emergency_case_id=int(row["emergency_case_id"]),
            case_number=str(row["case_number"]),
            patient_id=(
                int(row["patient_id"]) if row["patient_id"] is not None else None
            ),
            assigned_doctor_id=(
                int(row["assigned_doctor_id"])
                if row["assigned_doctor_id"] is not None
                else None
            ),
            intake_user_id=int(row["intake_user_id"]),
            triage_category=(
                str(row["triage_category"])
                if row["triage_category"] is not None
                else None
            ),
            status=str(row["status"]),
            arrival_at=str(row["arrival_at"]),
            closed_at=(
                str(row["closed_at"]) if row["closed_at"] is not None else None
            ),
            intake_notes=str(row["intake_notes"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
