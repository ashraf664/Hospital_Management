"""Authorization, validation, and persistence tests for directory services."""

from pathlib import Path
import tempfile
import unittest

from models import UserRole
from services import (
    AuthenticationService,
    DepartmentService,
    DoctorService,
    PatientService,
    PersistenceConflictError,
    PersistenceConstraintError,
    UserAdministrationService,
)
from ui.bootstrap import create_service_container


_OWNER_PASSWORD = "Synthetic Directory Owner Password 2026!"
_ADMIN_PASSWORD = "Synthetic Directory Admin Password 2026!"
_DOCTOR_PASSWORD = "Synthetic Directory Doctor Password 2026!"
_SECOND_DOCTOR_PASSWORD = "Synthetic Directory Second Doctor Password 2026!"
_RECEPTION_PASSWORD = "Synthetic Directory Reception Password 2026!"


class DirectoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "directory.db"
        self.container = create_service_container(self.database_path)
        self.connection = self.container._connection
        self.authentication: AuthenticationService = self.container.authentication
        self.accounts: UserAdministrationService = (
            self.container.user_administration
        )
        self.departments: DepartmentService = self.container.departments
        self.doctors: DoctorService = self.container.doctors
        self.patients: PatientService = self.container.patients
        self.owner_id = self.authentication.create_first_owner(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )
        self.owner = self.authentication.login(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )
        self.admin_id = self._create_user(
            "synthetic-admin",
            _ADMIN_PASSWORD,
            UserRole.ADMIN,
        )
        self.receptionist_id = self._create_user(
            "synthetic-reception",
            _RECEPTION_PASSWORD,
            UserRole.RECEPTIONIST,
        )
        self.doctor_user_id = self._create_user(
            "synthetic-doctor",
            _DOCTOR_PASSWORD,
            UserRole.DOCTOR,
        )
        self.second_doctor_user_id = self._create_user(
            "synthetic-doctor-two",
            _SECOND_DOCTOR_PASSWORD,
            UserRole.DOCTOR,
        )
        self.admin = self.authentication.login(
            "synthetic-admin",
            _ADMIN_PASSWORD,
        )
        self.receptionist = self.authentication.login(
            "synthetic-reception",
            _RECEPTION_PASSWORD,
        )
        self.doctor = self.authentication.login(
            "synthetic-doctor",
            _DOCTOR_PASSWORD,
        )
        self.second_doctor = self.authentication.login(
            "synthetic-doctor-two",
            _SECOND_DOCTOR_PASSWORD,
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(lambda: self.container.close())

    def _create_user(
        self,
        username: str,
        password: str,
        role: UserRole,
    ) -> int:
        created = self.accounts.create_user(
            self.owner.session_token,
            username,
            password,
            role,
        )
        return created.user_id

    def test_department_service_crud_activation_search_and_role_boundaries(
        self,
    ) -> None:
        department = self.departments.create(
            self.admin.session_token,
            " Synthetic Pediatrics ",
            " Synthetic description ",
        )
        self.assertEqual(department.name, "Synthetic Pediatrics")
        self.assertEqual(department.description, "Synthetic description")
        self.assertEqual(
            self.departments.search(
                self.owner.session_token,
                name="Synthetic Pediatrics",
            ).total_count,
            1,
        )
        updated = self.departments.update(
            self.owner.session_token,
            department.department_id,
            "Synthetic Child Health",
            "Updated synthetic description",
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.name, "Synthetic Child Health")

        deactivated = self.departments.set_active(
            self.admin.session_token,
            department.department_id,
            False,
        )
        self.assertFalse(deactivated.is_active)
        reactivated = self.departments.set_active(
            self.admin.session_token,
            department.department_id,
            True,
        )
        self.assertTrue(reactivated.is_active)
        self.assertIsNone(self.departments.find_by_id(self.admin.session_token, 9999))

        with self.assertRaises(PermissionError):
            self.departments.search(self.doctor.session_token)
        with self.assertRaises(PermissionError):
            self.departments.create(
                self.receptionist.session_token,
                "Synthetic denied department",
            )
        with self.assertRaises(ValueError):
            self.departments.create(self.admin.session_token, "  ")
        with self.assertRaises(TypeError):
            self.departments.set_active(
                self.admin.session_token,
                department.department_id,
                1,
            )
        self.assertFalse(hasattr(self.departments, "delete"))

    def test_department_write_and_audit_event_roll_back_together(self) -> None:
        self.connection.execute(
            """
            CREATE TRIGGER reject_test_department_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'department_created'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic audit failure');
            END
            """
        )
        before = self.connection.execute(
            "SELECT COUNT(*) FROM departments"
        ).fetchone()[0]

        with self.assertRaises(PersistenceConstraintError):
            self.departments.create(
                self.admin.session_token,
                "Synthetic rollback department",
            )

        after = self.connection.execute(
            "SELECT COUNT(*) FROM departments"
        ).fetchone()[0]
        self.assertEqual(after, before)

    def test_doctor_service_links_only_active_doctor_accounts_and_active_departments(
        self,
    ) -> None:
        department = self.departments.create(
            self.admin.session_token,
            "Synthetic Cardiology",
        )
        doctor = self.doctors.create(
            self.admin.session_token,
            self.doctor_user_id,
            department.department_id,
            "Synthetic Physician",
            "Synthetic Specialty",
            "555-0101",
        )
        self.assertEqual(doctor.user_id, self.doctor_user_id)

        profile = self.doctors.find_my_profile(self.doctor.session_token)
        self.assertEqual(profile.doctor_id, doctor.doctor_id)
        self.assertEqual(profile.full_name, "Synthetic Physician")
        with self.assertRaises(PermissionError):
            self.doctors.search(self.doctor.session_token)
        with self.assertRaises(PermissionError):
            self.doctors.find_my_profile(self.receptionist.session_token)

        directory = self.doctors.search(
            self.receptionist.session_token,
            full_name="Physician",
        )
        self.assertEqual(directory.total_count, 1)
        self.assertEqual(directory.items.get(0).specialty, "Synthetic Specialty")
        with self.assertRaises(PermissionError):
            self.doctors.create(
                self.receptionist.session_token,
                self.second_doctor_user_id,
                department.department_id,
                "Synthetic Denied",
                "Synthetic Specialty",
            )
        with self.assertRaises(ValueError):
            self.doctors.create(
                self.admin.session_token,
                self.receptionist_id,
                department.department_id,
                "Synthetic Wrong Role",
                "Synthetic Specialty",
            )
        with self.assertRaises(ValueError):
            self.doctors.create(
                self.admin.session_token,
                self.second_doctor_user_id,
                99999,
                "Synthetic Missing Department",
                "Synthetic Specialty",
            )
        with self.assertRaises(ValueError):
            self.doctors.create(
                self.admin.session_token,
                self.doctor_user_id,
                department.department_id,
                "Synthetic Duplicate",
                "Synthetic Specialty",
            )

        updated = self.doctors.update(
            self.admin.session_token,
            doctor.doctor_id,
            department.department_id,
            "Synthetic Updated Physician",
            "Synthetic Updated Specialty",
        )
        self.assertEqual(updated.full_name, "Synthetic Updated Physician")
        inactive_department = self.departments.set_active(
            self.admin.session_token,
            department.department_id,
            False,
        )
        with self.assertRaises(ValueError):
            self.doctors.update(
                self.admin.session_token,
                doctor.doctor_id,
                inactive_department.department_id,
                "Synthetic Physician",
                "Synthetic Specialty",
            )

        deactivated = self.doctors.set_active(
            self.admin.session_token,
            doctor.doctor_id,
            False,
        )
        self.assertFalse(deactivated.is_active)
        linked_account = self.container.authentication.user_repository.find_by_id(
            self.doctor_user_id
        )
        self.assertFalse(linked_account.is_active)
        with self.assertRaises(PermissionError):
            self.patients.search(self.doctor.session_token)
        reactivated = self.doctors.set_active(
            self.owner.session_token,
            doctor.doctor_id,
            True,
        )
        self.assertTrue(reactivated.is_active)
        self.assertTrue(
            self.container.authentication.user_repository.find_by_id(
                self.doctor_user_id
            ).is_active
        )
        self.assertFalse(hasattr(self.doctors, "delete"))

    def test_doctor_reactivation_preserves_a_previously_inactive_account(self) -> None:
        department = self.departments.create(
            self.admin.session_token,
            "Synthetic Account State Department",
        )
        doctor = self.doctors.create(
            self.admin.session_token,
            self.doctor_user_id,
            department.department_id,
            "Synthetic Account State Doctor",
            "Synthetic Specialty",
        )
        self.container.authentication.user_repository.deactivate(
            self.doctor_user_id
        )

        self.doctors.set_active(
            self.admin.session_token,
            doctor.doctor_id,
            False,
        )
        self.assertEqual(
            self.connection.execute(
                """
                SELECT account_was_active_before_deactivation
                FROM doctors WHERE doctor_id = ?
                """,
                (doctor.doctor_id,),
            ).fetchone()[0],
            0,
        )
        self.doctors.set_active(
            self.owner.session_token,
            doctor.doctor_id,
            True,
        )

        account = self.container.authentication.user_repository.find_by_id(
            self.doctor_user_id
        )
        saved_state = self.connection.execute(
            """
            SELECT account_was_active_before_deactivation
            FROM doctors WHERE doctor_id = ?
            """,
            (doctor.doctor_id,),
        ).fetchone()[0]
        self.assertFalse(account.is_active)
        self.assertIsNone(saved_state)

    def test_doctor_deactivation_and_account_update_roll_back_together(self) -> None:
        department = self.departments.create(
            self.admin.session_token,
            "Synthetic Deactivation Rollback Department",
        )
        doctor = self.doctors.create(
            self.admin.session_token,
            self.doctor_user_id,
            department.department_id,
            "Synthetic Deactivation Rollback Doctor",
            "Synthetic Specialty",
        )
        self.connection.execute(
            f"""
            CREATE TRIGGER reject_synthetic_doctor_deactivation
            BEFORE UPDATE ON users
            WHEN NEW.user_id = {self.doctor_user_id} AND NEW.is_active = 0
            BEGIN
                SELECT RAISE(ABORT, 'synthetic account update failure');
            END
            """
        )
        with self.assertRaises(PersistenceConstraintError):
            self.doctors.set_active(
                self.admin.session_token,
                doctor.doctor_id,
                False,
            )

        persisted_doctor = self.doctors.doctor_repository.find_by_id(
            doctor.doctor_id
        )
        persisted_user = self.container.authentication.user_repository.find_by_id(
            self.doctor_user_id
        )
        marker = self.connection.execute(
            """
            SELECT account_was_active_before_deactivation
            FROM doctors WHERE doctor_id = ?
            """,
            (doctor.doctor_id,),
        ).fetchone()[0]
        self.assertTrue(persisted_doctor.is_active)
        self.assertTrue(persisted_user.is_active)
        self.assertIsNone(marker)

    def test_doctor_deactivation_and_audit_failure_roll_back_together(self) -> None:
        department = self.departments.create(
            self.admin.session_token,
            "Synthetic Audit Rollback Department",
        )
        doctor = self.doctors.create(
            self.admin.session_token,
            self.doctor_user_id,
            department.department_id,
            "Synthetic Audit Rollback Doctor",
            "Synthetic Specialty",
        )
        self.connection.execute(
            """
            CREATE TRIGGER reject_synthetic_doctor_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'doctor_deactivated'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic audit failure');
            END
            """
        )
        audit_before = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]

        with self.assertRaises(PersistenceConstraintError):
            self.doctors.set_active(
                self.admin.session_token,
                doctor.doctor_id,
                False,
            )

        persisted_doctor = self.doctors.doctor_repository.find_by_id(
            doctor.doctor_id
        )
        persisted_user = self.container.authentication.user_repository.find_by_id(
            self.doctor_user_id
        )
        audit_after = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]
        self.assertTrue(persisted_doctor.is_active)
        self.assertTrue(persisted_user.is_active)
        self.assertEqual(audit_after, audit_before)

    def test_patient_service_scopes_doctors_and_keeps_medical_content_out_of_api(
        self,
    ) -> None:
        department = self.departments.create(
            self.admin.session_token,
            "Synthetic Family Medicine",
        )
        doctor_profile = self.doctors.create(
            self.admin.session_token,
            self.doctor_user_id,
            department.department_id,
            "Synthetic Doctor One",
            "Synthetic Specialty",
        )
        self.doctors.create(
            self.admin.session_token,
            self.second_doctor_user_id,
            department.department_id,
            "Synthetic Doctor Two",
            "Synthetic Specialty",
        )
        patient = self.patients.create(
            self.receptionist.session_token,
            "SYNTH-DIR-001",
            "Synthetic Patient One",
            "1985-06-07",
            sex="Synthetic value",
            phone="555-0123",
            address="Synthetic address",
            emergency_contact="Synthetic contact",
        )
        other_patient = self.patients.create(
            self.owner.session_token,
            "SYNTH-DIR-002",
            "Synthetic Patient Two",
            "1990-01-02",
        )
        self.connection.execute(
            """
            INSERT INTO appointments (
                patient_id, doctor_id, scheduled_start, scheduled_end, status,
                cancellation_reason, created_by_user_id
            )
            VALUES (?, ?, '2031-01-01T10:00:00Z', '2031-01-01T10:30:00Z',
                    'Cancelled', 'Synthetic cancellation', ?)
            """,
            (other_patient.patient_id, doctor_profile.doctor_id, self.admin_id),
        )
        self.connection.execute(
            """
            INSERT INTO doctor_patient_assignments (
                doctor_id, patient_id, assigned_by_user_id
            )
            VALUES (?, ?, ?)
            """,
            (doctor_profile.doctor_id, patient.patient_id, self.admin_id),
        )

        doctor_page = self.patients.search(
            self.doctor.session_token,
            query="Synthetic",
        )
        self.assertEqual(doctor_page.total_count, 1)
        self.assertEqual(doctor_page.items.get(0).patient_id, patient.patient_id)
        self.assertEqual(
            self.patients.find_by_id(
                self.doctor.session_token,
                patient.patient_id,
            ).full_name,
            "Synthetic Patient One",
        )
        with self.assertRaises(PermissionError):
            self.patients.find_by_id(
                self.doctor.session_token,
                other_patient.patient_id,
            )
        with self.assertRaises(PermissionError):
            self.patients.update_demographics(
                self.doctor.session_token,
                other_patient.patient_id,
                "Synthetic Unauthorized Update",
                "1990-01-02",
            )
        with self.assertRaises(PermissionError):
            self.patients.create(
                self.doctor.session_token,
                "SYNTH-DIR-003",
                "Synthetic Doctor-Created Patient",
                "1980-01-01",
            )

        updated = self.patients.update_demographics(
            self.doctor.session_token,
            patient.patient_id,
            "Synthetic Patient One Updated",
            "1985-06-07",
            phone="555-0199",
        )
        self.assertEqual(updated.full_name, "Synthetic Patient One Updated")
        self.assertEqual(updated.phone, "555-0199")
        receptionist_view = self.patients.find_by_id(
            self.receptionist.session_token,
            patient.patient_id,
        )
        self.assertFalse(hasattr(receptionist_view, "medical_record"))
        self.assertFalse(hasattr(receptionist_view, "record_content"))

        self.connection.execute(
            "UPDATE doctors SET is_active = 0 WHERE doctor_id = ?",
            (doctor_profile.doctor_id,),
        )
        with self.assertRaises(PermissionError):
            self.patients.search(self.doctor.session_token)

        deactivated = self.patients.set_active(
            self.receptionist.session_token,
            patient.patient_id,
            False,
        )
        self.assertFalse(deactivated.is_active)
        reactivated = self.patients.set_active(
            self.admin.session_token,
            patient.patient_id,
            True,
        )
        self.assertTrue(reactivated.is_active)
        self.assertFalse(hasattr(self.patients, "delete"))

    def test_patient_validation_conflicts_and_audit_failure_are_safe(self) -> None:
        with self.assertRaises(ValueError):
            self.patients.create(
                self.receptionist.session_token,
                "SYNTH-BAD-DATE",
                "Synthetic Invalid Date",
                "2024-02-30",
            )
        with self.assertRaises(ValueError):
            self.patients.create(
                self.receptionist.session_token,
                "SYNTH-FUTURE-DATE",
                "Synthetic Future Date",
                "2999-01-01",
            )
        self.patients.create(
            self.receptionist.session_token,
            "SYNTH-DUPLICATE",
            "Synthetic Duplicate One",
            "1980-01-01",
        )
        with self.assertRaises(PersistenceConflictError):
            self.patients.create(
                self.receptionist.session_token,
                "SYNTH-DUPLICATE",
                "Synthetic Duplicate Two",
                "1980-01-01",
            )

        self.connection.execute(
            """
            CREATE TRIGGER reject_test_patient_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'patient_created'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic audit failure');
            END
            """
        )
        before = self.connection.execute(
            "SELECT COUNT(*) FROM patients"
        ).fetchone()[0]
        audit_before = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'patient_created'"
        ).fetchone()[0]
        with self.assertRaises(PersistenceConstraintError):
            self.patients.create(
                self.receptionist.session_token,
                "SYNTH-ROLLBACK",
                "Synthetic Rollback Patient",
                "1980-01-01",
            )
        after = self.connection.execute(
            "SELECT COUNT(*) FROM patients"
        ).fetchone()[0]
        self.assertEqual(after, before)
        audit_after = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'patient_created'"
        ).fetchone()[0]
        self.assertEqual(audit_after, audit_before)

    def test_patient_directory_persists_after_reopening_the_database(self) -> None:
        self.patients.create(
            self.receptionist.session_token,
            "SYNTH-PERSIST-001",
            "Synthetic Persistent Patient",
            "1975-12-03",
        )
        self.container.close()
        self.container = create_service_container(self.database_path)
        self.connection = self.container._connection
        reopened_owner = self.container.authentication.login(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )

        found = self.container.patients.search(
            self.container.authentication.login(
                "synthetic-reception",
                _RECEPTION_PASSWORD,
            ).session_token,
            query="SYNTH-PERSIST-001",
        )
        self.assertEqual(found.total_count, 1)
        self.assertEqual(
            found.items.get(0).full_name,
            "Synthetic Persistent Patient",
        )
        self.assertIsNotNone(reopened_owner)


if __name__ == "__main__":
    unittest.main()
