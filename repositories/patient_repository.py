"""SQLite repository for patient demographics."""

import sqlite3

from models import Patient
from repositories.base_repository import BaseRepository, SQLiteParameter
from repositories.exceptions import PersistenceIntegrityError
from repositories.page import DEFAULT_PAGE_LIMIT, Page


_PATIENT_COLUMNS = (
    "patient_id, patient_number, full_name, date_of_birth, sex, phone, "
    "address, emergency_contact, is_active, created_at, updated_at"
)


class PatientRepository(BaseRepository):
    """Persist patient demographics without managing authorization or transactions."""

    def create(self, patient: Patient) -> Patient:
        """Insert a patient and return the database-generated values."""
        cursor = self._execute(
            """
            INSERT INTO patients (
                patient_number, full_name, date_of_birth, sex, phone, address,
                emergency_contact, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient.patient_number,
                patient.full_name,
                patient.date_of_birth,
                patient.sex,
                patient.phone,
                patient.address,
                patient.emergency_contact,
                int(patient.is_active),
            ),
        )
        created = self.find_by_id(int(cursor.lastrowid))
        if created is None:
            raise PersistenceIntegrityError(
                "Inserted patient could not be read back from SQLite."
            )
        return created

    def update_demographics(
        self,
        patient_id: int,
        full_name: str,
        date_of_birth: str,
        sex: str | None,
        phone: str | None,
        address: str | None,
        emergency_contact: str | None,
    ) -> Patient | None:
        """Update demographic fields while retaining patient identity."""
        cursor = self._execute(
            """
            UPDATE patients
            SET full_name = ?,
                date_of_birth = ?,
                sex = ?,
                phone = ?,
                address = ?,
                emergency_contact = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE patient_id = ?
            """,
            (
                full_name,
                date_of_birth,
                sex,
                phone,
                address,
                emergency_contact,
                patient_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(patient_id)

    def deactivate(self, patient_id: int) -> Patient | None:
        """Mark a patient inactive without deleting their history."""
        cursor = self._execute(
            """
            UPDATE patients
            SET is_active = 0,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE patient_id = ?
            """,
            (patient_id,),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(patient_id)

    def find_by_id(self, patient_id: int) -> Patient | None:
        """Find a patient by primary key."""
        row = self._fetchone(
            f"SELECT {_PATIENT_COLUMNS} FROM patients WHERE patient_id = ?",
            (patient_id,),
        )
        return self._patient_from_row(row) if row is not None else None

    def find_by_number(self, patient_number: str) -> Patient | None:
        """Find a patient by exact patient number."""
        row = self._fetchone(
            f"SELECT {_PATIENT_COLUMNS} FROM patients WHERE patient_number = ?",
            (patient_number,),
        )
        return self._patient_from_row(row) if row is not None else None

    def find_for_doctor(self, doctor_id: int, patient_id: int) -> Patient | None:
        """Find a patient only when the doctor has an active care assignment."""
        row = self._fetchone(
            f"""
            SELECT {_PATIENT_COLUMNS}
            FROM patients AS patient
            WHERE patient.patient_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM doctor_patient_assignments AS assignment
                  WHERE assignment.patient_id = patient.patient_id
                    AND assignment.doctor_id = ?
                    AND assignment.ended_at IS NULL
              )
            """,
            (patient_id, doctor_id),
        )
        return self._patient_from_row(row) if row is not None else None

    def search(
        self,
        patient_number: str | None = None,
        full_name: str | None = None,
        phone: str | None = None,
        is_active: bool | None = None,
        doctor_id: int | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> Page[Patient]:
        """Search patients with optional active-care scoping and pagination."""
        Page[Patient](limit=limit, offset=offset)
        clauses: tuple[str, ...] = ()
        parameters: tuple[SQLiteParameter, ...] = ()
        if patient_number is not None:
            clauses += ("patient.patient_number = ?",)
            parameters += (patient_number,)
        if full_name is not None:
            clauses += ("""patient.full_name LIKE ? ESCAPE '\\'""",)
            parameters += (self._like_pattern(full_name),)
        if phone is not None:
            clauses += ("""patient.phone LIKE ? ESCAPE '\\'""",)
            parameters += (self._like_pattern(phone),)
        if is_active is not None:
            clauses += ("patient.is_active = ?",)
            parameters += (int(is_active),)
        if doctor_id is not None:
            clauses += (
                """
                EXISTS (
                    SELECT 1
                    FROM doctor_patient_assignments AS assignment
                    WHERE assignment.patient_id = patient.patient_id
                      AND assignment.doctor_id = ?
                      AND assignment.ended_at IS NULL
                )
                """,
            )
            parameters += (doctor_id,)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        count_row = self._fetchone(
            f"SELECT COUNT(*) AS total_count FROM patients AS patient{where_sql}",
            parameters,
        )
        total_count = int(count_row["total_count"]) if count_row is not None else 0
        rows = self._fetchall(
            f"""
            SELECT {_PATIENT_COLUMNS}
            FROM patients AS patient{where_sql}
            ORDER BY patient.patient_id ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        )
        items = Page[Patient](limit=limit, offset=offset).items
        for row in rows:
            items.append(self._patient_from_row(row))
        return Page(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _like_pattern(value: str) -> str:
        """Build a substring pattern where user-supplied wildcards are literal."""
        escaped_value = (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        return f"%{escaped_value}%"

    @staticmethod
    def _patient_from_row(row: sqlite3.Row) -> Patient:
        return Patient(
            patient_id=int(row["patient_id"]),
            patient_number=str(row["patient_number"]),
            full_name=str(row["full_name"]),
            date_of_birth=str(row["date_of_birth"]),
            sex=str(row["sex"]) if row["sex"] is not None else None,
            phone=str(row["phone"]) if row["phone"] is not None else None,
            address=str(row["address"]) if row["address"] is not None else None,
            emergency_contact=(
                str(row["emergency_contact"])
                if row["emergency_contact"] is not None
                else None
            ),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
