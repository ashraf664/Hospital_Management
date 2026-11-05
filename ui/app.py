"""Main CustomTkinter window and navigation."""

import logging
import sqlite3

import customtkinter as ctk

from models.enums import UserRole
from repositories.exceptions import PersistenceConflictError, PersistenceError
from services.authentication_service import (
    AuthenticationError,
    AuthenticationService,
)
from services.appointment_service import AppointmentService
from services.department_service import DepartmentService
from services.doctor_service import DoctorService
from services.emergency_case_service import EmergencyCaseService
from services.patient_service import PatientService
from services.session import AuthenticatedSession
from services.user_administration_service import UserAdministrationService
from ui.bootstrap import ServiceContainer
from ui.screens.dashboard import DashboardScreen
from ui.screens.directories import (
    DepartmentDirectoryScreen,
    DoctorDirectoryScreen,
    PatientDirectoryScreen,
)
from ui.screens.login import LoginScreen
from ui.screens.owner_setup import OwnerSetupScreen
from ui.screens.appointments import AppointmentScreen
from ui.screens.emergency_intake import EmergencyIntakeScreen
from ui.screens.user_management import UserManagementScreen


_LOGGER = logging.getLogger(__name__)


class HospitalManagementApp(ctk.CTk):
    """Present screens while delegating authentication and permissions."""

    def __init__(self, services: ServiceContainer) -> None:
        super().__init__()
        self.services = services
        self.authentication: AuthenticationService = services.authentication
        self.user_administration: UserAdministrationService = (
            services.user_administration
        )
        self.department_service: DepartmentService = services.departments
        self.doctor_service: DoctorService = services.doctors
        self.patient_service: PatientService = services.patients
        self.appointment_service: AppointmentService = services.appointments
        self.emergency_case_service: EmergencyCaseService = (
            services.emergency_cases
        )
        self.session: AuthenticatedSession | None = None
        self.current_screen: ctk.CTkFrame | None = None

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.title("Hospital Management System")
        self.geometry("1080x760")
        self.minsize(860, 620)
        self.configure(fg_color=("gray96", "gray10"))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._show_initial_screen()

    def _show_initial_screen(self) -> None:
        if self.authentication.first_owner_setup_available():
            self._show_owner_setup()
        else:
            self._show_login()

    def _show_login(self, message: str = "") -> None:
        self._replace_screen(
            LoginScreen(
                self,
                self._login,
                message=message,
            )
        )

    def _show_owner_setup(self) -> None:
        self._replace_screen(
            OwnerSetupScreen(
                self,
                self._create_first_owner,
            )
        )

    def _show_dashboard(self) -> None:
        if self.session is None:
            self._show_login()
            return
        self._replace_screen(
            DashboardScreen(
                self,
                self.session,
                self._logout,
                self._open_feature,
            )
        )

    def _open_feature(self, feature_key: str) -> None:
        if self.session is None:
            return
        if feature_key == "manage_users":
            if self.session.role not in {UserRole.OWNER, UserRole.ADMIN}:
                return
            screen = UserManagementScreen(
                self,
                self.session,
                self.user_administration,
                self._show_dashboard,
            )
        elif feature_key == "departments":
            if self.session.role not in {UserRole.OWNER, UserRole.ADMIN}:
                return
            screen = DepartmentDirectoryScreen(
                self,
                self.session,
                self.department_service,
                self.doctor_service,
                self._show_dashboard,
            )
        elif feature_key == "doctors":
            if self.session.role not in {
                UserRole.OWNER,
                UserRole.ADMIN,
                UserRole.RECEPTIONIST,
            }:
                return
            screen = DoctorDirectoryScreen(
                self,
                self.session,
                self.doctor_service,
                self._show_dashboard,
            )
        elif feature_key == "doctor_profile":
            if self.session.role is not UserRole.DOCTOR:
                return
            screen = DoctorDirectoryScreen(
                self,
                self.session,
                self.doctor_service,
                self._show_dashboard,
                own_profile=True,
            )
        elif feature_key in {"appointments", "schedule"}:
            if feature_key == "schedule" and self.session.role is not UserRole.DOCTOR:
                return
            if feature_key == "appointments" and self.session.role is UserRole.DOCTOR:
                return
            screen = AppointmentScreen(
                self,
                self.session,
                self.appointment_service,
                self._show_dashboard,
            )
        elif feature_key == "patients":
            screen = PatientDirectoryScreen(
                self,
                self.session,
                self.patient_service,
                self._show_dashboard,
            )
        elif feature_key in {"emergency_intake", "emergency_cases"}:
            if self.session.role not in {
                UserRole.OWNER,
                UserRole.ADMIN,
                UserRole.RECEPTIONIST,
                UserRole.DOCTOR,
            }:
                return
            screen = EmergencyIntakeScreen(
                self,
                self.session,
                self.emergency_case_service,
                self._show_dashboard,
            )
        else:
            return
        self._replace_screen(screen)

    def _login(self, username: str, password: str) -> None:
        screen = self.current_screen
        if not isinstance(screen, LoginScreen):
            return
        try:
            self.session = self.authentication.login(username, password)
        except AuthenticationError:
            screen.show_feedback("Invalid username or password.")
        except PersistenceError:
            _LOGGER.exception("Authentication could not be completed.")
            screen.show_feedback(
                "Sign in is temporarily unavailable. Check the application log."
            )
        except sqlite3.Error:
            _LOGGER.exception("Authentication encountered a database error.")
            screen.show_feedback(
                "Sign in is temporarily unavailable. Check the application log."
            )
        else:
            self._show_dashboard()

    def _create_first_owner(self, username: str, password: str) -> None:
        screen = self.current_screen
        if not isinstance(screen, OwnerSetupScreen):
            return
        try:
            self.authentication.create_first_owner(username, password)
        except (ValueError, PermissionError) as error:
            if isinstance(error, PermissionError):
                if not self.authentication.first_owner_setup_available():
                    self._show_login(
                        "Initial setup is no longer available. Sign in instead."
                    )
                    return
            screen.show_feedback(str(error))
        except PersistenceConflictError:
            screen.show_feedback("That username is already in use.")
        except PersistenceError:
            _LOGGER.exception("Initial Owner setup could not be completed.")
            screen.show_feedback(
                "The account could not be saved. Check the application log."
            )
        except sqlite3.Error:
            _LOGGER.exception("Initial Owner setup encountered a database error.")
            screen.show_feedback(
                "The account could not be saved. Check the application log."
            )
        else:
            self._show_login("Owner account created. Sign in to continue.")

    def _logout(self) -> None:
        session = self.session
        if session is None:
            self._show_login()
            return
        message = "You have signed out."
        try:
            self.authentication.logout(session.session_token)
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Could not audit session sign-out.")
            message = (
                "Your session ended locally, but sign-out auditing failed. "
                "Check the application log."
            )
        finally:
            self.session = None
            self._show_login(message)

    def _replace_screen(self, screen: ctk.CTkFrame) -> None:
        if self.current_screen is not None:
            self.current_screen.destroy()
        self.current_screen = screen

    def _close(self) -> None:
        if self.session is not None:
            try:
                self.authentication.logout(self.session.session_token)
            except (PersistenceError, sqlite3.Error):
                _LOGGER.exception("Could not audit sign-out while closing.")
            finally:
                self.session = None
        self.destroy()
