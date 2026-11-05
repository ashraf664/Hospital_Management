"""Authentication, authorization, session, and security-audit tests."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from database.connection_manager import ConnectionManager
from database.database_initializer import DatabaseInitializer
from models import Department, Doctor, EmergencyCase, Patient, User, UserRole
from repositories import (
    DepartmentRepository,
    DoctorRepository,
    EmergencyCaseRepository,
    PatientRepository,
    PersistenceConstraintError,
    UserRepository,
)
from services import (
    AuthenticationError,
    AuthenticationService,
    AuthorizationService,
    Permission,
    UserAdministrationService,
)
from services.password_hasher import PasswordHasher


_OWNER_PASSWORD = "Synthetic Owner Passphrase 2026!"
_ADMIN_PASSWORD = "Synthetic Admin Passphrase 2026!"
_DOCTOR_PASSWORD = "Synthetic Doctor Passphrase 2026!"
_RECEPTION_PASSWORD = "Synthetic Reception Passphrase 2026!"


class AuthenticationAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "auth.db"
        DatabaseInitializer(self.database_path).initialize()
        self.connection = ConnectionManager(self.database_path).connect()
        self.authentication = AuthenticationService(self.connection)
        self.authorization = AuthorizationService(
            self.connection,
            self.authentication.session_registry,
        )
        self.accounts = UserAdministrationService(
            self.connection,
            self.authorization,
        )
        self.users = UserRepository(self.connection)
        self.patients = PatientRepository(self.connection)
        self.doctors = DoctorRepository(self.connection)
        self.departments = DepartmentRepository(self.connection)
        self.cases = EmergencyCaseRepository(self.connection)
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.connection.close)

    def create_owner(self):
        user_id = self.authentication.create_first_owner(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )
        return self.authentication.login("synthetic-owner", _OWNER_PASSWORD), user_id

    def create_user(
        self,
        session_token: str,
        username: str,
        password: str,
        role: UserRole,
    ) -> int:
        user = self.accounts.create_user(
            session_token,
            username,
            password,
            role,
        )
        return user.user_id

    def test_password_hashing_is_salted_and_verified_without_plaintext(self) -> None:
        hasher = PasswordHasher()
        first_hash = hasher.hash_password(_OWNER_PASSWORD)
        second_hash = hasher.hash_password(_OWNER_PASSWORD)

        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(first_hash.startswith("scrypt$"))
        self.assertNotIn(_OWNER_PASSWORD, first_hash)
        self.assertTrue(hasher.verify_password(_OWNER_PASSWORD, first_hash))
        self.assertFalse(hasher.verify_password("Wrong synthetic password", first_hash))
        self.assertFalse(hasher.verify_password(_OWNER_PASSWORD, "invalid"))
        with self.assertRaises(ValueError):
            hasher.hash_password("short")

    def test_first_owner_setup_is_single_use_hashed_and_audited(self) -> None:
        self.assertTrue(self.authentication.first_owner_setup_available())
        owner_id = self.authentication.create_first_owner(
            "synthetic-owner",
            _OWNER_PASSWORD,
        )
        self.assertFalse(self.authentication.first_owner_setup_available())
        owner = self.users.find_by_id(owner_id)
        self.assertIsNotNone(owner)
        self.assertIs(owner.role, UserRole.OWNER)
        stored = self.connection.execute(
            "SELECT password_hash, role FROM users WHERE user_id = ?",
            (owner_id,),
        ).fetchone()
        self.assertTrue(stored["password_hash"].startswith("scrypt$"))
        self.assertNotIn(_OWNER_PASSWORD, stored["password_hash"])
        self.assertEqual(stored["role"], UserRole.ADMIN.value)
        owner_row = self.connection.execute(
            "SELECT singleton_id, user_id FROM owner_accounts"
        ).fetchone()
        self.assertEqual(tuple(owner_row), (1, owner_id))
        setup_audit = self.connection.execute(
            """
            SELECT user_id, actor_type, action, details
            FROM audit_logs
            WHERE action = 'first_owner_created'
            """
        ).fetchone()
        self.assertIsNone(setup_audit["user_id"])
        self.assertEqual(setup_audit["actor_type"], "first_admin_setup")
        self.assertNotIn(_OWNER_PASSWORD, setup_audit["details"])

        with self.assertRaises(PermissionError):
            self.authentication.create_first_owner(
                "synthetic-owner-two",
                "Synthetic Another Owner Password 2026!",
            )
        with self.assertRaises(ValueError):
            self.users.create(
                User(
                    username="synthetic-owner-three",
                    password_hash="never-used",
                    role=UserRole.OWNER,
                )
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "DELETE FROM owner_accounts WHERE singleton_id = 1"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "UPDATE users SET is_active = 0 WHERE user_id = ?",
                (owner_id,),
            )

    def test_first_owner_setup_is_blocked_if_any_account_exists(self) -> None:
        self.users.create(
            User(
                username="preexisting-admin",
                password_hash="synthetic-hash",
                role=UserRole.ADMIN,
            )
        )

        self.assertFalse(self.authentication.first_owner_setup_available())
        with self.assertRaises(PermissionError):
            self.authentication.create_first_owner(
                "late-owner",
                "Synthetic Late Owner Password 2026!",
            )

    def test_login_inactive_denied_and_logout_revokes_session(self) -> None:
        owner_session, owner_id = self.create_owner()
        receptionist_id = self.create_user(
            owner_session.session_token,
            "synthetic-receptionist",
            _RECEPTION_PASSWORD,
            UserRole.RECEPTIONIST,
        )

        logged_in = self.authentication.login(
            "synthetic-receptionist",
            _RECEPTION_PASSWORD,
        )
        self.assertEqual(logged_in.user_id, receptionist_id)
        self.assertIs(logged_in.role, UserRole.RECEPTIONIST)
        self.authorization.require_permission(
            logged_in.session_token,
            Permission.MANAGE_APPOINTMENTS,
        )

        with self.assertRaises(AuthenticationError):
            self.authentication.login("synthetic-receptionist", "wrong password")
        with self.assertRaises(AuthenticationError):
            self.authentication.login("unknown-synthetic-user", _OWNER_PASSWORD)

        self.users.deactivate(receptionist_id)
        with self.assertRaises(AuthenticationError):
            self.authentication.login(
                "synthetic-receptionist",
                _RECEPTION_PASSWORD,
            )
        with self.assertRaises(PermissionError):
            self.authorization.require_permission(
                logged_in.session_token,
                Permission.MANAGE_APPOINTMENTS,
            )

        self.authentication.logout(owner_session.session_token)
        with self.assertRaises(PermissionError):
            self.authorization.require_permission(
                owner_session.session_token,
                Permission.MANAGE_USERS,
            )
        events = self.connection.execute(
            """
            SELECT action, details
            FROM audit_logs
            WHERE action IN (
                'authentication_succeeded', 'authentication_failed',
                'session_ended'
            )
            """
        ).fetchall()
        self.assertGreaterEqual(
            sum(row["action"] == "authentication_failed" for row in events),
            3,
        )
        self.assertTrue(
            any(
                row["action"] == "session_ended"
                for row in events
            )
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE user_id = ?",
                (owner_id,),
            ).fetchone()[0],
            4,
        )
        self.assertNotIn(
            _RECEPTION_PASSWORD,
            " ".join(row["details"] for row in events),
        )

    def test_failed_audit_write_never_grants_a_session(self) -> None:
        self.authentication.create_first_owner("synthetic-owner", _OWNER_PASSWORD)
        self.connection.execute(
            """
            CREATE TEMP TRIGGER reject_authentication_audit
            BEFORE INSERT ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'synthetic audit failure');
            END
            """
        )

        with self.assertRaises(PersistenceConstraintError):
            self.authentication.login("synthetic-owner", _OWNER_PASSWORD)
        with self.assertRaises(PersistenceConstraintError):
            self.authorization.require_permission(
                "fabricated-session-token",
                Permission.MANAGE_USERS,
            )

    def test_service_roles_and_doctor_care_scope_are_enforced_and_audited(
        self,
    ) -> None:
        owner_session, owner_id = self.create_owner()
        self.create_user(
            owner_session.session_token,
            "synthetic-admin",
            _ADMIN_PASSWORD,
            UserRole.ADMIN,
        )
        doctor_user_id = self.create_user(
            owner_session.session_token,
            "synthetic-doctor",
            _DOCTOR_PASSWORD,
            UserRole.DOCTOR,
        )
        second_doctor_user_id = self.create_user(
            owner_session.session_token,
            "synthetic-doctor-two",
            "Synthetic Former Doctor Password 2026!",
            UserRole.DOCTOR,
        )
        receptionist_id = self.create_user(
            owner_session.session_token,
            "synthetic-receptionist",
            _RECEPTION_PASSWORD,
            UserRole.RECEPTIONIST,
        )
        admin_user = self.users.find_for_authentication("synthetic-admin")
        self.assertIsNotNone(admin_user)
        self.assertTrue(admin_user.password_hash.startswith("scrypt$"))
        self.assertNotIn(_ADMIN_PASSWORD, admin_user.password_hash)
        self.assertFalse(
            any(
                _ADMIN_PASSWORD in row["details"]
                for row in self.connection.execute(
                    "SELECT details FROM audit_logs"
                )
            )
        )
        admin_session = self.authentication.login("synthetic-admin", _ADMIN_PASSWORD)
        doctor_session = self.authentication.login("synthetic-doctor", _DOCTOR_PASSWORD)
        receptionist_session = self.authentication.login(
            "synthetic-receptionist",
            _RECEPTION_PASSWORD,
        )

        with self.assertRaises(PermissionError):
            self.accounts.create_user(
                receptionist_session.session_token,
                "forged-admin",
                "Synthetic Forged Admin Password 2026!",
                UserRole.ADMIN,
            )
        with self.assertRaises(PermissionError):
            self.authorization.require_permission(
                "forged-session-token",
                Permission.MANAGE_USERS,
            )
        with self.assertRaises(PermissionError):
            self.accounts.create_user(
                admin_session.session_token,
                "synthetic-second-owner",
                "Synthetic Second Owner Password 2026!",
                UserRole.OWNER,
            )
        with self.assertRaises(PermissionError):
            self.accounts.update_user(
                admin_session.session_token,
                owner_id,
                "renamed-owner",
                UserRole.ADMIN,
            )
        with self.assertRaises(PermissionError):
            self.accounts.deactivate_user(admin_session.session_token, owner_id)
        self.assertIsNone(
            self.users.update_account(owner_id, "repo-renamed-owner", UserRole.ADMIN)
        )
        self.assertIsNone(self.users.deactivate(owner_id))

        department = self.departments.create(
            Department(name="Synthetic Care Department")
        )
        doctor = self.doctors.create(
            Doctor(
                user_id=doctor_user_id,
                department_id=department.department_id,
                full_name="Synthetic Care Doctor",
                specialty="Synthetic Specialty",
            )
        )
        second_doctor = self.doctors.create(
            Doctor(
                user_id=second_doctor_user_id,
                department_id=department.department_id,
                full_name="Synthetic Doctor Two",
                specialty="Synthetic Specialty",
            )
        )
        second_doctor_session = self.authentication.login(
            "synthetic-doctor-two",
            "Synthetic Former Doctor Password 2026!",
        )
        cared_patient = self.patients.create(
            Patient(
                patient_number="SYNTH-AUTH-CARE",
                full_name="Synthetic Care Patient",
                date_of_birth="1980-01-02",
            )
        )
        unrelated_patient = self.patients.create(
            Patient(
                patient_number="SYNTH-AUTH-OTHER",
                full_name="Synthetic Unrelated Patient",
                date_of_birth="1982-03-04",
            )
        )
        self.connection.execute(
            """
            INSERT INTO doctor_patient_assignments (
                doctor_id, patient_id, assigned_by_user_id
            )
            VALUES (?, ?, ?)
            """,
            (doctor.doctor_id, cared_patient.patient_id, owner_id),
        )
        self.connection.execute(
            """
            INSERT INTO appointments (
                patient_id, doctor_id, scheduled_start, scheduled_end, status,
                created_by_user_id
            )
            VALUES (?, ?, '2031-01-01T10:00:00Z', '2031-01-01T10:30:00Z',
                    'Scheduled', ?)
            """,
            (unrelated_patient.patient_id, doctor.doctor_id, owner_id),
        )
        self.connection.execute(
            """
            INSERT INTO appointments (
                patient_id, doctor_id, scheduled_start, scheduled_end, status,
                created_by_user_id
            )
            VALUES (?, ?, '2031-01-01T11:00:00Z', '2031-01-01T11:30:00Z',
                    'Scheduled', ?)
            """,
            (cared_patient.patient_id, second_doctor.doctor_id, owner_id),
        )
        medical_record_cursor = self.connection.execute(
            """
            INSERT INTO medical_records (
                patient_id, doctor_id, record_type, record_content
            )
            VALUES (?, ?, 'Synthetic note', 'Synthetic clinical content')
            """,
            (cared_patient.patient_id, doctor.doctor_id),
        )
        medical_record_id = int(medical_record_cursor.lastrowid)

        self.authorization.require_patient_access(
            doctor_session.session_token,
            cared_patient.patient_id,
            clinical=True,
        )
        self.authorization.require_patient_access(
            doctor_session.session_token,
            cared_patient.patient_id,
            clinical=True,
            write=True,
        )
        self.authorization.require_medical_record_access(
            doctor_session.session_token,
            medical_record_id,
            write=True,
        )
        with self.assertRaises(PermissionError):
            self.authorization.require_patient_access(
                doctor_session.session_token,
                unrelated_patient.patient_id,
                clinical=True,
            )
        for session in (owner_session, admin_session, receptionist_session):
            with self.subTest(role=session.role):
                with self.assertRaises(PermissionError):
                    self.authorization.require_patient_access(
                        session.session_token,
                        cared_patient.patient_id,
                        clinical=True,
                    )
                with self.assertRaises(PermissionError):
                    self.authorization.require_medical_record_access(
                        session.session_token,
                        medical_record_id,
                    )

        case = self.cases.create(
            EmergencyCase(
                case_number="ER-SYNTH-AUTH-001",
                patient_id=cared_patient.patient_id,
                assigned_doctor_id=doctor.doctor_id,
                intake_user_id=receptionist_id,
                status="Open",
                arrival_at="2031-01-01T09:00:00Z",
            )
        )
        self.authorization.require_emergency_case_access(
            doctor_session.session_token,
            case.emergency_case_id,
            clinical=True,
            write=True,
        )
        with self.assertRaises(PermissionError):
            self.authorization.require_emergency_case_access(
                second_doctor_session.session_token,
                case.emergency_case_id,
                clinical=True,
            )
        with self.assertRaises(PermissionError):
            self.authorization.require_emergency_case_access(
                admin_session.session_token,
                case.emergency_case_id,
                clinical=True,
            )
        self.authorization.require_emergency_case_access(
            owner_session.session_token,
            case.emergency_case_id,
            clinical=False,
            write=True,
        )
        with self.assertRaises(PermissionError):
            self.authorization.require_emergency_case_access(
                owner_session.session_token,
                case.emergency_case_id,
                clinical=True,
            )

        audit_cursor = self.connection.execute(
            """
            INSERT INTO audit_logs (
                user_id, actor_type, action, entity_type, entity_id, details
            )
            VALUES (?, 'user', 'emergency_doctor_reassigned',
                    'emergency_case', ?, 'Synthetic reassignment')
            """,
            (owner_id, str(case.emergency_case_id)),
        )
        self.connection.execute(
            """
            INSERT INTO emergency_doctor_assignments (
                emergency_case_id, sequence_no, previous_doctor_id,
                new_doctor_id, change_reason, record_origin, event_at,
                actor_user_id, audit_log_id
            )
            VALUES (?, 1, ?, ?, 'Synthetic reassignment',
                    'application_event', '2031-01-01T10:00:00Z', ?, ?)
            """,
            (
                case.emergency_case_id,
                doctor.doctor_id,
                second_doctor.doctor_id,
                owner_id,
                int(audit_cursor.lastrowid),
            ),
        )
        self.authorization.require_emergency_case_access(
            doctor_session.session_token,
            case.emergency_case_id,
            clinical=True,
            write=False,
        )
        with self.assertRaises(PermissionError):
            self.authorization.require_emergency_case_access(
                doctor_session.session_token,
                case.emergency_case_id,
                clinical=True,
                write=True,
            )
        self.authorization.require_emergency_case_access(
            second_doctor_session.session_token,
            case.emergency_case_id,
            clinical=True,
            write=True,
        )
        self.authorization.require_emergency_case_access(
            receptionist_session.session_token,
            case.emergency_case_id,
            clinical=False,
            write=True,
        )
        appointments = self.connection.execute(
            """
            SELECT appointment_id FROM appointments
            ORDER BY appointment_id
            """
        ).fetchall()
        own_appointment_id = int(appointments[0]["appointment_id"])
        another_doctor_appointment_id = int(appointments[1]["appointment_id"])
        self.authorization.require_appointment_access(
            doctor_session.session_token,
            own_appointment_id,
        )
        self.authorization.require_appointment_access(
            doctor_session.session_token,
            own_appointment_id,
            update_clinical_status=True,
        )
        with self.assertRaises(PermissionError):
            self.authorization.require_appointment_access(
                doctor_session.session_token,
                another_doctor_appointment_id,
            )
