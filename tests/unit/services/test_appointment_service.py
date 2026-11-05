"""Authorization, validation, and transaction tests for appointment services."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from models import UserRole
from services import (
    AppointmentConflictError,
    AppointmentService,
    AuthenticationService,
    DepartmentService,
    DoctorService,
    PatientService,
    PersistenceConstraintError,
    UserAdministrationService,
)
from ui.bootstrap import create_service_container


_OWNER_PASSWORD = "Synthetic Appointment Owner Password 2026!"
_ADMIN_PASSWORD = "Synthetic Appointment Admin Password 2026!"
_RECEPTION_PASSWORD = "Synthetic Appointment Reception Password 2026!"
_DOCTOR_PASSWORD = "Synthetic Appointment Doctor Password 2026!"
_OTHER_DOCTOR_PASSWORD = "Synthetic Appointment Other Doctor Password 2026!"


class AppointmentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "appointments.db"
        self.container = create_service_container(self.database_path)
        self.connection = self.container._connection
        self.authentication: AuthenticationService = self.container.authentication
        self.accounts: UserAdministrationService = (
            self.container.user_administration
        )
        self.departments: DepartmentService = self.container.departments
        self.doctors: DoctorService = self.container.doctors
        self.patients: PatientService = self.container.patients
        self.appointments: AppointmentService = self.container.appointments
        self.owner_id = self.authentication.create_first_owner(
            "synthetic-appointment-owner",
            _OWNER_PASSWORD,
        )
        self.owner = self.authentication.login(
            "synthetic-appointment-owner",
            _OWNER_PASSWORD,
        )
        self.admin_id = self._create_user(
            "synthetic-appointment-admin",
            _ADMIN_PASSWORD,
            UserRole.ADMIN,
        )
        self.receptionist_id = self._create_user(
            "synthetic-appointment-reception",
            _RECEPTION_PASSWORD,
            UserRole.RECEPTIONIST,
        )
        self.doctor_user_id = self._create_user(
            "synthetic-appointment-doctor",
            _DOCTOR_PASSWORD,
            UserRole.DOCTOR,
        )
        self.other_doctor_user_id = self._create_user(
            "synthetic-appointment-doctor-two",
            _OTHER_DOCTOR_PASSWORD,
            UserRole.DOCTOR,
        )
        self.admin = self.authentication.login(
            "synthetic-appointment-admin",
            _ADMIN_PASSWORD,
        )
        self.receptionist = self.authentication.login(
            "synthetic-appointment-reception",
            _RECEPTION_PASSWORD,
        )
        self.doctor = self.authentication.login(
            "synthetic-appointment-doctor",
            _DOCTOR_PASSWORD,
        )
        self.other_doctor = self.authentication.login(
            "synthetic-appointment-doctor-two",
            _OTHER_DOCTOR_PASSWORD,
        )
        self.department = self.departments.create(
            self.admin.session_token,
            "Synthetic Appointment Department",
        )
        self.doctor_profile = self.doctors.create(
            self.admin.session_token,
            self.doctor_user_id,
            self.department.department_id,
            "Synthetic Appointment Doctor",
            "Synthetic Specialty",
        )
        self.other_doctor_profile = self.doctors.create(
            self.admin.session_token,
            self.other_doctor_user_id,
            self.department.department_id,
            "Synthetic Appointment Doctor Two",
            "Synthetic Specialty",
        )
        self.patient = self.patients.create(
            self.receptionist.session_token,
            "SYNTH-APPT-001",
            "مريض موعد تجريبي",
            "1985-06-07",
        )
        self.other_patient = self.patients.create(
            self.receptionist.session_token,
            "SYNTH-APPT-002",
            "Synthetic Appointment Patient Two",
            "1990-01-02",
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self.container.close)

    def _create_user(
        self,
        username: str,
        password: str,
        role: UserRole,
    ) -> int:
        return self.accounts.create_user(
            self.owner.session_token,
            username,
            password,
            role,
        ).user_id

    def create_appointment(
        self,
        *,
        doctor_id: int | None = None,
        scheduled_start: str = "2031-02-03T10:00:00Z",
    ):
        return self.appointments.create(
            self.receptionist.session_token,
            self.patient.patient_id,
            self.doctor_profile.doctor_id if doctor_id is None else doctor_id,
            scheduled_start,
        )

    def _create_appointment_in_state(self, status: str, index: int):
        start = (
            datetime(2032, 1, 1, 8, tzinfo=timezone.utc)
            + timedelta(days=index)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        appointment = self.create_appointment(scheduled_start=start)
        if status == "Scheduled":
            return appointment
        if status == "Confirmed":
            self.appointments.update_status(
                self.owner.session_token,
                appointment.appointment_id,
                "Confirmed",
            )
        elif status == "Checked In":
            self.appointments.update_status(
                self.owner.session_token,
                appointment.appointment_id,
                "Checked In",
            )
        elif status == "In Progress":
            self.appointments.update_status(
                self.owner.session_token,
                appointment.appointment_id,
                "Checked In",
            )
            self.appointments.update_status(
                self.doctor.session_token,
                appointment.appointment_id,
                "In Progress",
            )
        elif status == "Completed":
            self.appointments.update_status(
                self.owner.session_token,
                appointment.appointment_id,
                "Checked In",
            )
            self.appointments.update_status(
                self.doctor.session_token,
                appointment.appointment_id,
                "In Progress",
            )
            self.appointments.update_status(
                self.doctor.session_token,
                appointment.appointment_id,
                "Completed",
            )
        elif status == "Cancelled":
            self.appointments.cancel(
                self.owner.session_token,
                appointment.appointment_id,
                "Synthetic terminal-state setup",
            )
        elif status == "No Show":
            self.appointments.update_status(
                self.owner.session_token,
                appointment.appointment_id,
                "No Show",
            )
        else:
            raise AssertionError(f"Unknown test setup status: {status}")
        return self.appointments.appointment_repository.find_by_id(
            appointment.appointment_id
        )

    def test_create_reschedule_and_cancel_preserve_history(self) -> None:
        created = self.appointments.create(
            self.owner.session_token,
            self.patient.patient_id,
            self.doctor_profile.doctor_id,
            "2031-02-03T10:00:00+00:00",
        )
        self.assertEqual(created.scheduled_start, "2031-02-03T10:00:00Z")
        self.assertEqual(created.scheduled_end, "2031-02-03T10:30:00Z")
        self.assertEqual(created.status, "Scheduled")

        updated = self.appointments.reschedule(
            self.admin.session_token,
            created.appointment_id,
            "2031-02-03T11:00:00Z",
            duration_minutes=45,
        )
        self.assertEqual(updated.scheduled_start, "2031-02-03T11:00:00Z")
        self.assertEqual(updated.scheduled_end, "2031-02-03T11:45:00Z")
        self.assertEqual(updated.appointment_id, created.appointment_id)

        cancelled = self.appointments.cancel(
            self.receptionist.session_token,
            created.appointment_id,
            "المريض طلب الإلغاء",
        )
        self.assertEqual(cancelled.status, "Cancelled")
        self.assertEqual(cancelled.cancellation_reason, "المريض طلب الإلغاء")
        self.assertEqual(
            self.appointments.find_by_id(
                self.admin.session_token,
                created.appointment_id,
            ),
            cancelled,
        )

    def test_configurable_duration_and_invalid_time_values(self) -> None:
        configured = AppointmentService(
            self.connection,
            self.container.authorization,
            default_duration_minutes=45,
        )
        created = configured.create(
            self.receptionist.session_token,
            self.patient.patient_id,
            self.doctor_profile.doctor_id,
            "2031-02-03T10:00:00+02:00",
        )
        self.assertEqual(created.scheduled_start, "2031-02-03T08:00:00Z")
        self.assertEqual(created.scheduled_end, "2031-02-03T08:45:00Z")

        for start in (
            "not-a-time",
            "2031-02-03T10:00:00",
            "2031-02-30T10:00:00Z",
        ):
            with self.subTest(start=start), self.assertRaises(ValueError):
                self.appointments.create(
                    self.receptionist.session_token,
                    self.patient.patient_id,
                    self.doctor_profile.doctor_id,
                    start,
                )
        for duration in (0, -1, True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.appointments.create(
                    self.receptionist.session_token,
                    self.patient.patient_id,
                    self.doctor_profile.doctor_id,
                    "2031-02-03T12:00:00Z",
                    duration_minutes=duration,
                )

    def test_invalid_or_inactive_references_are_rejected(self) -> None:
        for patient_id, doctor_id in (
            (9999, self.doctor_profile.doctor_id),
            (self.patient.patient_id, 9999),
        ):
            with self.subTest(patient_id=patient_id, doctor_id=doctor_id):
                with self.assertRaises(ValueError):
                    self.appointments.create(
                        self.receptionist.session_token,
                        patient_id,
                        doctor_id,
                        "2031-02-03T10:00:00Z",
                    )

        self.patients.set_active(
            self.admin.session_token,
            self.patient.patient_id,
            False,
        )
        with self.assertRaisesRegex(ValueError, "active patient"):
            self.create_appointment()

        self.patients.set_active(
            self.admin.session_token,
            self.patient.patient_id,
            True,
        )
        self.doctors.set_active(
            self.admin.session_token,
            self.doctor_profile.doctor_id,
            False,
        )
        with self.assertRaisesRegex(ValueError, "active doctor"):
            self.create_appointment()

        self.doctors.set_active(
            self.admin.session_token,
            self.doctor_profile.doctor_id,
            True,
        )
        self.container.authentication.user_repository.deactivate(
            self.doctor_user_id
        )
        with self.assertRaisesRegex(ValueError, "active doctor"):
            self.create_appointment()

    def test_overlap_and_time_boundaries_are_checked(self) -> None:
        first = self.create_appointment()
        with self.assertRaises(AppointmentConflictError):
            self.appointments.create(
                self.receptionist.session_token,
                self.other_patient.patient_id,
                self.doctor_profile.doctor_id,
                "2031-02-03T10:29:00Z",
            )
        back_to_back = self.appointments.create(
            self.receptionist.session_token,
            self.other_patient.patient_id,
            self.doctor_profile.doctor_id,
            first.scheduled_end,
        )
        other_doctor = self.appointments.create(
            self.receptionist.session_token,
            self.other_patient.patient_id,
            self.other_doctor_profile.doctor_id,
            first.scheduled_start,
        )
        self.assertNotEqual(back_to_back.appointment_id, other_doctor.appointment_id)

        with self.assertRaises(AppointmentConflictError):
            self.appointments.reschedule(
                self.admin.session_token,
                back_to_back.appointment_id,
                "2031-02-03T10:15:00Z",
            )

    def test_cancellation_releases_slot_and_retains_record(self) -> None:
        appointment = self.create_appointment()
        with self.assertRaisesRegex(ValueError, "cancellation_reason is required"):
            self.appointments.cancel(
                self.admin.session_token,
                appointment.appointment_id,
                "   ",
            )
        self.appointments.cancel(
            self.admin.session_token,
            appointment.appointment_id,
            "Synthetic cancellation reason",
        )
        replacement = self.create_appointment()
        self.assertNotEqual(replacement.appointment_id, appointment.appointment_id)
        retained = self.appointments.appointment_repository.find_by_id(
            appointment.appointment_id
        )
        self.assertEqual(retained.status, "Cancelled")
        self.assertEqual(
            retained.cancellation_reason,
            "Synthetic cancellation reason",
        )
        with self.assertRaisesRegex(ValueError, "terminal appointment"):
            self.appointments.reschedule(
                self.admin.session_token,
                appointment.appointment_id,
                "2031-02-04T10:00:00Z",
            )
        with self.assertRaisesRegex(PermissionError, "cannot transition"):
            self.appointments.cancel(
                self.admin.session_token,
                appointment.appointment_id,
                "Second cancellation attempt",
            )
        self.assertIsNone(
            self.appointments.cancel(
                self.admin.session_token,
                9999,
                "Unknown appointment cancellation",
            )
        )

    def test_doctor_schedule_scope_status_rights_and_no_patient_scope_grant(self) -> None:
        own = self.create_appointment()
        other = self.appointments.create(
            self.receptionist.session_token,
            self.other_patient.patient_id,
            self.other_doctor_profile.doctor_id,
            "2031-02-03T12:00:00Z",
        )
        page = self.appointments.search(self.doctor.session_token)
        self.assertEqual(
            [item.appointment_id for item in page.items],
            [own.appointment_id],
        )
        self.appointments.update_status(
            self.owner.session_token,
            own.appointment_id,
            "Checked In",
        )
        self.assertEqual(
            self.appointments.update_status(
                self.doctor.session_token,
                own.appointment_id,
                "In Progress",
            ).status,
            "In Progress",
        )
        self.assertEqual(
            self.appointments.update_status(
                self.doctor.session_token,
                own.appointment_id,
                "Completed",
            ).status,
            "Completed",
        )
        with self.assertRaises(PermissionError):
            self.appointments.find_by_id(
                self.doctor.session_token,
                other.appointment_id,
            )
        with self.assertRaises(PermissionError):
            self.appointments.search(
                self.doctor.session_token,
                doctor_id=self.other_doctor_profile.doctor_id,
            )
        with self.assertRaises(PermissionError):
            self.container.authorization.require_patient_access(
                self.doctor.session_token,
                self.patient.patient_id,
            )
        for action in (
            lambda: self.appointments.create(
                self.doctor.session_token,
                self.patient.patient_id,
                self.doctor_profile.doctor_id,
                "2031-02-04T10:00:00Z",
            ),
            lambda: self.appointments.reschedule(
                self.doctor.session_token,
                own.appointment_id,
                "2031-02-04T10:00:00Z",
            ),
            lambda: self.appointments.cancel(
                self.doctor.session_token,
                own.appointment_id,
                "Doctor may not cancel",
            ),
        ):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                action()
        for role_session in (self.owner, self.admin, self.receptionist):
            with self.subTest(role=role_session.role):
                with self.assertRaises(PermissionError):
                    self.appointments.update_status(
                        role_session.session_token,
                        own.appointment_id,
                        "Completed",
                    )
        with self.assertRaises(ValueError):
            self.appointments.update_status(
                self.doctor.session_token,
                own.appointment_id,
                "Cancelled",
            )

    def test_only_approved_status_values_are_accepted(self) -> None:
        appointment = self.create_appointment()
        for invalid_status in ("Booked", "Arrived", "completed", "cancelled", ""):
            with self.subTest(status=invalid_status), self.assertRaises(ValueError):
                self.appointments.update_status(
                    self.owner.session_token,
                    appointment.appointment_id,
                    invalid_status,
                )
        with self.assertRaises(ValueError):
            self.appointments.search(
                self.admin.session_token,
                status="Booked",
            )
        self.assertEqual(
            self.appointments.available_transitions(
                self.receptionist.session_token,
                appointment.appointment_id,
            ),
            ("Confirmed", "Checked In", "Cancelled", "No Show"),
        )

    def test_every_approved_transition_and_role_boundary(self) -> None:
        allowed_roles = {
            ("Scheduled", "Confirmed"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Scheduled", "Checked In"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Scheduled", "Cancelled"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Scheduled", "No Show"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Confirmed", "Checked In"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Confirmed", "Cancelled"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Confirmed", "No Show"): (
                self.owner,
                self.admin,
                self.receptionist,
            ),
            ("Checked In", "In Progress"): (self.doctor,),
            ("In Progress", "Completed"): (self.doctor,),
            ("Checked In", "Cancelled"): (self.owner, self.admin),
        }
        all_roles = (self.owner, self.admin, self.receptionist, self.doctor)
        case_index = 0
        for (current_status, next_status), permitted in allowed_roles.items():
            for actor in all_roles:
                with self.subTest(
                    current=current_status,
                    next=next_status,
                    role=actor.role,
                ):
                    appointment = self._create_appointment_in_state(
                        current_status,
                        case_index,
                    )
                    case_index += 1
                    available = self.appointments.available_transitions(
                        actor.session_token,
                        appointment.appointment_id,
                    )
                    if actor in permitted:
                        self.assertIn(next_status, available)
                        if next_status == "Cancelled":
                            updated = self.appointments.cancel(
                                actor.session_token,
                                appointment.appointment_id,
                                "Synthetic approved cancellation",
                            )
                        else:
                            updated = self.appointments.update_status(
                                actor.session_token,
                                appointment.appointment_id,
                                next_status,
                            )
                        self.assertEqual(updated.status, next_status)
                    else:
                        self.assertNotIn(next_status, available)
                        with self.assertRaises(PermissionError):
                            if next_status == "Cancelled":
                                self.appointments.cancel(
                                    actor.session_token,
                                    appointment.appointment_id,
                                    "Synthetic denied cancellation",
                                )
                            else:
                                self.appointments.update_status(
                                    actor.session_token,
                                    appointment.appointment_id,
                                    next_status,
                                )
                        persisted = (
                            self.appointments.appointment_repository.find_by_id(
                                appointment.appointment_id
                            )
                        )
                        self.assertEqual(persisted.status, current_status)

    def test_terminal_appointments_cannot_transition_or_be_rescheduled(self) -> None:
        for index, terminal_status in enumerate(
            ("Completed", "Cancelled", "No Show"),
            start=100,
        ):
            appointment = self._create_appointment_in_state(
                terminal_status,
                index,
            )
            for actor in (
                self.owner,
                self.admin,
                self.receptionist,
                self.doctor,
            ):
                with self.subTest(status=terminal_status, role=actor.role):
                    self.assertEqual(
                        self.appointments.available_transitions(
                            actor.session_token,
                            appointment.appointment_id,
                        ),
                        (),
                    )
                    for target_status in self.appointments.STATUSES:
                        with self.subTest(target=target_status):
                            with self.assertRaises(PermissionError):
                                if target_status == "Cancelled":
                                    self.appointments.cancel(
                                        actor.session_token,
                                        appointment.appointment_id,
                                        "Synthetic terminal transition attempt",
                                    )
                                else:
                                    self.appointments.update_status(
                                        actor.session_token,
                                        appointment.appointment_id,
                                        target_status,
                                    )
            with self.assertRaisesRegex(ValueError, "terminal appointment"):
                self.appointments.reschedule(
                    self.admin.session_token,
                    appointment.appointment_id,
                    "2033-01-01T10:00:00Z",
                )

    def test_search_filters_paginates_and_validates_filters(self) -> None:
        first = self.create_appointment()
        second = self.appointments.create(
            self.receptionist.session_token,
            self.other_patient.patient_id,
            self.other_doctor_profile.doctor_id,
            "2031-02-03T11:00:00Z",
        )
        page = self.appointments.search(
            self.admin.session_token,
            start_from="2031-02-03T10:00:00Z",
            start_to="2031-02-03T12:00:00Z",
            limit=1,
        )
        next_page = self.appointments.search(
            self.admin.session_token,
            start_from="2031-02-03T10:00:00Z",
            start_to="2031-02-03T12:00:00Z",
            limit=1,
            offset=1,
        )
        self.assertEqual(page.total_count, 2)
        self.assertEqual(page.items.get(0).appointment_id, first.appointment_id)
        self.assertEqual(next_page.items.get(0).appointment_id, second.appointment_id)
        with self.assertRaises(ValueError):
            self.appointments.search(
                self.admin.session_token,
                start_from="2031-02-03T12:00:00Z",
                start_to="2031-02-03T10:00:00Z",
            )
        for limit, offset in ((0, 0), (201, 0), (1, -1)):
            with self.subTest(limit=limit, offset=offset), self.assertRaises(ValueError):
                self.appointments.search(
                    self.admin.session_token,
                    limit=limit,
                    offset=offset,
                )

    def test_role_permissions_include_owner_admin_and_receptionist_schedule_access(
        self,
    ) -> None:
        for role_session in (self.owner, self.admin, self.receptionist):
            with self.subTest(role=role_session.role):
                page = self.appointments.search(role_session.session_token)
                self.assertEqual(page.total_count, 0)
        for session in (self.doctor, self.other_doctor):
            with self.subTest(role=session.role, user_id=session.user_id):
                self.assertEqual(
                    self.appointments.search(session.session_token).total_count,
                    0,
                )
        self.assertIsNone(
            self.appointments.find_by_id(
                self.admin.session_token,
                9999,
            )
        )

    def test_create_and_audit_roll_back_together_on_audit_failure(self) -> None:
        self.connection.execute(
            """
            CREATE TRIGGER reject_synthetic_appointment_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'appointment_created'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic appointment audit failure');
            END
            """
        )
        before = self.connection.execute(
            "SELECT COUNT(*) FROM appointments"
        ).fetchone()[0]
        audit_before = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]

        with self.assertRaises(PersistenceConstraintError):
            self.create_appointment()

        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM appointments"
            ).fetchone()[0],
            before,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            audit_before,
        )

    def test_status_and_audit_roll_back_together_on_audit_failure(self) -> None:
        appointment = self.create_appointment()
        self.appointments.update_status(
            self.owner.session_token,
            appointment.appointment_id,
            "Checked In",
        )
        self.appointments.update_status(
            self.doctor.session_token,
            appointment.appointment_id,
            "In Progress",
        )
        self.connection.execute(
            """
            CREATE TRIGGER reject_synthetic_appointment_status_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'appointment_status_updated'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic status audit failure');
            END
            """
        )
        audit_before = self.connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0]
        with self.assertRaises(PersistenceConstraintError):
            self.appointments.update_status(
                self.doctor.session_token,
                appointment.appointment_id,
                "Completed",
            )
        persisted = self.appointments.appointment_repository.find_by_id(
            appointment.appointment_id
        )
        self.assertEqual(persisted.status, "In Progress")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            audit_before,
        )

    def test_real_ui_composition_flow_survives_database_reopen(self) -> None:
        created = self.appointments.create(
            self.receptionist.session_token,
            self.patient.patient_id,
            self.doctor_profile.doctor_id,
            "2031-02-05T09:00:00Z",
        )
        self.container.close()
        reopened = create_service_container(self.database_path)
        self.addCleanup(reopened.close)
        admin_session = reopened.authentication.login(
            "synthetic-appointment-admin",
            _ADMIN_PASSWORD,
        )
        persisted = reopened.appointments.find_by_id(
            admin_session.session_token,
            created.appointment_id,
        )
        self.assertEqual(persisted, created)
        reopened.authentication.logout(admin_session.session_token)


if __name__ == "__main__":
    unittest.main()
