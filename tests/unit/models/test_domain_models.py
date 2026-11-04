"""Unit tests for domain model fields, defaults, and enum values."""

from dataclasses import FrozenInstanceError, fields
from typing import get_type_hints
import unittest

from models import (
    Appointment,
    AuditActorType,
    AuditLog,
    Department,
    Doctor,
    DoctorPatientAssignment,
    EmergencyCase,
    MedicalRecord,
    MedicalRecordVersion,
    Patient,
    User,
    UserRole,
)


class DomainModelTests(unittest.TestCase):
    def test_model_fields_match_database_entity_columns(self) -> None:
        expected_fields = {
            User: {
                "user_id", "username", "password_hash", "role", "is_active",
                "created_at", "updated_at",
            },
            Patient: {
                "patient_id", "patient_number", "full_name", "date_of_birth",
                "sex", "phone", "address", "emergency_contact", "is_active",
                "created_at", "updated_at",
            },
            Doctor: {
                "doctor_id", "user_id", "department_id", "full_name",
                "specialty", "phone", "is_active",
            },
            Department: {
                "department_id", "name", "description", "is_active",
                "created_at", "updated_at",
            },
            DoctorPatientAssignment: {
                "assignment_id", "doctor_id", "patient_id", "assigned_by_user_id",
                "assigned_at", "ended_by_user_id", "ended_at", "end_reason",
            },
            Appointment: {
                "appointment_id", "patient_id", "doctor_id", "scheduled_start",
                "scheduled_end", "status", "reason", "cancellation_reason",
                "created_by_user_id", "created_at", "updated_at",
            },
            EmergencyCase: {
                "emergency_case_id", "case_number", "patient_id",
                "assigned_doctor_id", "intake_user_id", "triage_category",
                "status", "arrival_at", "closed_at", "intake_notes", "created_at",
                "updated_at",
            },
            MedicalRecord: {
                "medical_record_id", "patient_id", "doctor_id", "appointment_id",
                "record_type", "record_content", "created_at", "updated_at",
                "is_amended",
            },
            MedicalRecordVersion: {
                "version_id", "medical_record_id", "patient_id_snapshot",
                "doctor_id_snapshot", "appointment_id_snapshot",
                "record_type_snapshot", "record_content_snapshot",
                "created_at_snapshot", "updated_at_snapshot",
                "is_amended_snapshot", "modified_by_user_id", "modified_at",
            },
            AuditLog: {
                "audit_log_id", "user_id", "actor_type", "action", "entity_type",
                "entity_id", "occurred_at", "details",
            },
        }

        for model, column_names in expected_fields.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    {field.name for field in fields(model)},
                    column_names,
                )

    def test_user_model_fields_types_and_defaults(self) -> None:
        user = User(
            username="doctor",
            password_hash="test-hash",
            role=UserRole.DOCTOR,
        )

        self.assertIsNone(user.user_id)
        self.assertIs(user.role, UserRole.DOCTOR)
        self.assertTrue(user.is_active)
        self.assertIsNone(user.created_at)
        self.assertIsNone(user.updated_at)
        self.assertEqual(get_type_hints(User)["password_hash"], str)
        self.assertFalse(hasattr(user, "password"))

    def test_patient_model_fields_optional_values_and_defaults(self) -> None:
        patient = Patient(
            patient_number="TEST-001",
            full_name="Synthetic Patient",
            date_of_birth="1980-01-02",
        )

        self.assertIsNone(patient.patient_id)
        self.assertIsNone(patient.sex)
        self.assertIsNone(patient.phone)
        self.assertIsNone(patient.address)
        self.assertIsNone(patient.emergency_contact)
        self.assertTrue(patient.is_active)
        self.assertIsNone(patient.created_at)
        self.assertIsNone(patient.updated_at)
        self.assertIsInstance(patient.date_of_birth, str)

    def test_doctor_model_required_foreign_keys_and_optional_phone(self) -> None:
        doctor = Doctor(
            user_id=1,
            department_id=2,
            full_name="Synthetic Doctor",
            specialty="Unspecified",
        )

        self.assertIsNone(doctor.doctor_id)
        self.assertIsNone(doctor.phone)
        self.assertTrue(doctor.is_active)
        self.assertEqual(doctor.user_id, 1)
        self.assertEqual(doctor.department_id, 2)

    def test_department_model_defaults(self) -> None:
        department = Department(name="General")

        self.assertIsNone(department.department_id)
        self.assertEqual(department.description, "")
        self.assertTrue(department.is_active)
        self.assertIsNone(department.created_at)
        self.assertIsNone(department.updated_at)

    def test_assignment_model_optional_end_fields(self) -> None:
        assignment = DoctorPatientAssignment(
            doctor_id=1,
            patient_id=2,
            assigned_by_user_id=3,
        )

        self.assertIsNone(assignment.assignment_id)
        self.assertIsNone(assignment.assigned_at)
        self.assertIsNone(assignment.ended_by_user_id)
        self.assertIsNone(assignment.ended_at)
        self.assertIsNone(assignment.end_reason)

    def test_appointment_model_optional_fields_and_timestamp_types(self) -> None:
        appointment = Appointment(
            patient_id=1,
            doctor_id=2,
            scheduled_start="2026-01-02T09:00:00Z",
            scheduled_end="2026-01-02T09:30:00Z",
            status="Pending",
            created_by_user_id=3,
        )

        self.assertIsNone(appointment.appointment_id)
        self.assertIsNone(appointment.reason)
        self.assertIsNone(appointment.cancellation_reason)
        self.assertIsNone(appointment.created_at)
        self.assertIsNone(appointment.updated_at)
        self.assertIsInstance(appointment.scheduled_start, str)
        self.assertIsInstance(appointment.scheduled_end, str)

    def test_emergency_case_allows_unknown_patient_and_unassigned_doctor(self) -> None:
        case = EmergencyCase(
            case_number="ER-TEST-001",
            intake_user_id=1,
            status="Open",
            arrival_at="2026-01-02T09:00:00Z",
        )

        self.assertIsNone(case.emergency_case_id)
        self.assertIsNone(case.patient_id)
        self.assertIsNone(case.assigned_doctor_id)
        self.assertIsNone(case.triage_category)
        self.assertIsNone(case.closed_at)
        self.assertEqual(case.intake_notes, "")
        self.assertIsNone(case.created_at)
        self.assertIsNone(case.updated_at)

    def test_medical_record_model_optional_appointment_and_amendment_default(self) -> None:
        record = MedicalRecord(
            patient_id=1,
            doctor_id=2,
            record_type="consultation",
            record_content="Synthetic note",
        )

        self.assertIsNone(record.medical_record_id)
        self.assertIsNone(record.appointment_id)
        self.assertIsNone(record.created_at)
        self.assertIsNone(record.updated_at)
        self.assertFalse(record.is_amended)

    def test_medical_record_version_preserves_full_prior_fields(self) -> None:
        version = MedicalRecordVersion(
            medical_record_id=1,
            patient_id_snapshot=2,
            doctor_id_snapshot=3,
            appointment_id_snapshot=None,
            record_type_snapshot="consultation",
            record_content_snapshot="Original synthetic note",
            created_at_snapshot="2026-01-02T09:00:00Z",
            updated_at_snapshot="2026-01-02T09:00:00Z",
            is_amended_snapshot=False,
            modified_by_user_id=4,
            modified_at="2026-01-03T10:00:00Z",
        )

        self.assertIsNone(version.version_id)
        self.assertIsNone(version.appointment_id_snapshot)
        self.assertFalse(version.is_amended_snapshot)
        self.assertEqual(version.modified_by_user_id, 4)
        self.assertEqual(len(fields(version)), 12)

    def test_medical_record_version_fields_cannot_be_modified(self) -> None:
        version = MedicalRecordVersion(
            medical_record_id=1,
            patient_id_snapshot=2,
            doctor_id_snapshot=3,
            appointment_id_snapshot=None,
            record_type_snapshot="consultation",
            record_content_snapshot="Original synthetic note",
            created_at_snapshot="2026-01-02T09:00:00Z",
            updated_at_snapshot="2026-01-02T09:00:00Z",
            is_amended_snapshot=False,
            modified_by_user_id=4,
            modified_at="2026-01-03T10:00:00Z",
        )

        with self.assertRaises(FrozenInstanceError):
            version.record_content_snapshot = "Changed synthetic note"

    def test_audit_log_model_optional_actor_and_database_defaults(self) -> None:
        event = AuditLog(
            actor_type=AuditActorType.FIRST_ADMIN_SETUP,
            action="account.created",
            entity_type="user",
            entity_id="1",
        )

        self.assertIsNone(event.audit_log_id)
        self.assertIsNone(event.user_id)
        self.assertIsNone(event.occurred_at)
        self.assertEqual(event.details, "")

    def test_enums_match_only_schema_defined_role_and_actor_values(self) -> None:
        self.assertEqual(
            {role.value for role in UserRole},
            {"Admin", "Doctor", "Receptionist"},
        )
        self.assertEqual(
            {actor.value for actor in AuditActorType},
            {"user", "anonymous", "first_admin_setup"},
        )

    def test_unsettled_status_values_remain_strings(self) -> None:
        appointment_status = get_type_hints(Appointment)["status"]
        emergency_status = get_type_hints(EmergencyCase)["status"]
        triage_category = get_type_hints(EmergencyCase)["triage_category"]

        self.assertIs(appointment_status, str)
        self.assertIs(emergency_status, str)
        self.assertEqual(str(triage_category), "str | None")


if __name__ == "__main__":
    unittest.main()
