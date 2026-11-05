"""Read-only relationship queries used by service-layer authorization."""

from repositories.base_repository import BaseRepository


class AuthorizationRepository(BaseRepository):
    """Resolve doctor-care relationships without exposing clinical contents."""

    def doctor_id_for_user(self, user_id: int) -> int | None:
        row = self._fetchone(
            "SELECT doctor_id FROM doctors WHERE user_id = ?",
            (user_id,),
        )
        return int(row["doctor_id"]) if row is not None else None

    def doctor_is_active(self, doctor_id: int) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM doctors WHERE doctor_id = ? AND is_active = 1",
            (doctor_id,),
        )
        return row is not None

    def patient_exists(self, patient_id: int) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM patients WHERE patient_id = ?",
            (patient_id,),
        )
        return row is not None

    def has_active_patient_assignment(
        self,
        doctor_id: int,
        patient_id: int,
    ) -> bool:
        row = self._fetchone(
            """
            SELECT 1
            FROM doctor_patient_assignments
            WHERE doctor_id = ? AND patient_id = ? AND ended_at IS NULL
            LIMIT 1
            """,
            (doctor_id, patient_id),
        )
        return row is not None

    def emergency_case_exists(self, emergency_case_id: int) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM emergency_cases WHERE emergency_case_id = ?",
            (emergency_case_id,),
        )
        return row is not None

    def has_patient_care_relationship(
        self,
        doctor_id: int,
        patient_id: int,
        *,
        write: bool,
    ) -> bool:
        active_assignment = self._fetchone(
            """
            SELECT 1
            FROM doctor_patient_assignments
            WHERE doctor_id = ? AND patient_id = ? AND ended_at IS NULL
            LIMIT 1
            """,
            (doctor_id, patient_id),
        )
        if active_assignment is not None:
            return True
        if write:
            return False

        historical_record = self._fetchone(
            """
            SELECT 1
            FROM medical_records
            WHERE doctor_id = ? AND patient_id = ?
            LIMIT 1
            """,
            (doctor_id, patient_id),
        )
        if historical_record is not None:
            return True
        emergency_assignment = self._fetchone(
            """
            SELECT 1
            FROM emergency_cases AS emergency_case
            JOIN emergency_doctor_assignments AS assignment
                ON assignment.emergency_case_id =
                    emergency_case.emergency_case_id
            WHERE emergency_case.patient_id = ?
                AND (
                    assignment.previous_doctor_id = ?
                    OR assignment.new_doctor_id = ?
                )
            LIMIT 1
            """,
            (patient_id, doctor_id, doctor_id),
        )
        return emergency_assignment is not None

    def has_emergency_case_relationship(
        self,
        doctor_id: int,
        emergency_case_id: int,
        *,
        write: bool,
    ) -> bool:
        current_assignment = self._fetchone(
            """
            SELECT 1
            FROM emergency_cases AS emergency_case
            JOIN doctors AS doctor
                ON doctor.doctor_id = emergency_case.assigned_doctor_id
            WHERE emergency_case.emergency_case_id = ?
                AND doctor.doctor_id = ?
                AND doctor.is_active = 1
            """,
            (emergency_case_id, doctor_id),
        )
        if current_assignment is not None:
            return True
        if write:
            return False

        historical_assignment = self._fetchone(
            """
            SELECT 1
            FROM emergency_doctor_assignments
            WHERE emergency_case_id = ?
                AND (
                    previous_doctor_id = ?
                    OR new_doctor_id = ?
                )
            LIMIT 1
            """,
            (emergency_case_id, doctor_id, doctor_id),
        )
        return historical_assignment is not None

    def medical_record_scope(
        self,
        medical_record_id: int,
    ) -> tuple[int, int] | None:
        row = self._fetchone(
            """
            SELECT patient_id, doctor_id
            FROM medical_records
            WHERE medical_record_id = ?
            """,
            (medical_record_id,),
        )
        if row is None:
            return None
        return int(row["patient_id"]), int(row["doctor_id"])

    def appointment_scope(
        self,
        appointment_id: int,
    ) -> tuple[int, bool] | None:
        row = self._fetchone(
            """
            SELECT doctor.user_id, doctor.is_active
            FROM appointments AS appointment
            JOIN doctors AS doctor ON doctor.doctor_id = appointment.doctor_id
            WHERE appointment.appointment_id = ?
            """,
            (appointment_id,),
        )
        if row is None:
            return None
        return int(row["user_id"]), bool(row["is_active"])
