"""Service-backed department, doctor, and patient directory screens."""

from collections.abc import Callable
import logging
import sqlite3

import customtkinter as ctk

from models import Department, Doctor, Patient, UserRole
from services.department_service import DepartmentService
from services.doctor_service import DoctorService
from services.patient_service import PatientService
from services import (
    AuthenticatedSession,
    PersistenceConflictError,
    PersistenceError,
)


_LOGGER = logging.getLogger(__name__)
_FONT = "Segoe UI"


class DirectoryScreen(ctk.CTkFrame):
    PAGE_SIZE = 50

    def __init__(
        self,
        master: ctk.CTk,
        title: str,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_back = on_back
        self.pack(fill="both", expand=True)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(24, 8))
        ctk.CTkButton(
            header,
            text="Back to dashboard",
            width=150,
            command=on_back,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(family=_FONT, size=24, weight="bold"),
        ).pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=32, pady=(8, 24))

    def show_message(self, label: ctk.CTkLabel, message: str, *, error: bool) -> None:
        label.configure(
            text=message,
            text_color="#c2413b" if error else "#278357",
        )

    @staticmethod
    def replace_list(frame: ctk.CTkScrollableFrame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _panels(self) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        panels = ctk.CTkFrame(self.body, fg_color="transparent")
        panels.pack(fill="both", expand=True)
        panels.grid_columnconfigure(0, weight=3)
        panels.grid_columnconfigure(1, weight=2)
        panels.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(panels, corner_radius=14)
        left.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        right = ctk.CTkFrame(panels, corner_radius=14)
        right.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        return left, right

    @staticmethod
    def _entry(master: ctk.CTkBaseClass, placeholder: str) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            master,
            height=38,
            placeholder_text=placeholder,
            font=ctk.CTkFont(family=_FONT, size=13),
        )

    @staticmethod
    def _message(master: ctk.CTkBaseClass) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master,
            text="",
            wraplength=360,
            justify="left",
            text_color="#c2413b",
            font=ctk.CTkFont(family=_FONT, size=12),
        )

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str) -> None:
        was_disabled = str(entry.cget("state")) == "disabled"
        if was_disabled:
            entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        if was_disabled:
            entry.configure(state="disabled")

    @staticmethod
    def _positive_int(value: str, field_name: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise ValueError(f"{field_name} must be a positive integer.") from error
        if parsed < 1:
            raise ValueError(f"{field_name} must be a positive integer.")
        return parsed

    def _create_pagination(self, parent: ctk.CTkFrame) -> None:
        self.offset = 0
        self.total_count = 0
        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(0, 10))
        self.previous_button = ctk.CTkButton(
            controls,
            text="Previous",
            width=100,
            command=self._previous_page,
        )
        self.previous_button.pack(side="left")
        self.page_label = ctk.CTkLabel(
            controls,
            text="0 results",
            text_color=("gray40", "gray65"),
        )
        self.page_label.pack(side="left", expand=True)
        self.next_button = ctk.CTkButton(
            controls,
            text="Next",
            width=100,
            command=self._next_page,
        )
        self.next_button.pack(side="right")
        self._update_pagination()

    def reset_search(self) -> None:
        self.offset = 0
        self.refresh()

    def _previous_page(self) -> None:
        self.offset = max(0, self.offset - self.PAGE_SIZE)
        self.refresh()

    def _next_page(self) -> None:
        if self.offset + self.PAGE_SIZE < self.total_count:
            self.offset += self.PAGE_SIZE
            self.refresh()

    def _update_pagination(self) -> None:
        first = self.offset + 1 if self.total_count else 0
        last = min(self.offset + self.PAGE_SIZE, self.total_count)
        self.page_label.configure(
            text=f"{first}-{last} of {self.total_count}"
        )
        self.previous_button.configure(
            state="normal" if self.offset > 0 else "disabled"
        )
        self.next_button.configure(
            state=(
                "normal"
                if self.offset + self.PAGE_SIZE < self.total_count
                else "disabled"
            )
        )


class DepartmentDirectoryScreen(DirectoryScreen):
    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        service: DepartmentService,
        doctor_service: DoctorService,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(master, "Departments", on_back)
        self.session = session
        self.service = service
        self.doctor_service = doctor_service
        self.selected_id: int | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        left, right = self._panels()
        self.list_frame = ctk.CTkScrollableFrame(left, corner_radius=12)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self._create_pagination(left)
        ctk.CTkLabel(
            right,
            text="Department details",
            font=ctk.CTkFont(family=_FONT, size=17, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))
        self.search_entry = self._entry(left, "Exact department name")
        self.search_entry.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkButton(
            left,
            text="Search",
            command=self.reset_search,
        ).pack(fill="x", padx=12, pady=(0, 4))
        self.name = self._entry(right, "Name")
        self.name.pack(fill="x", padx=18, pady=6)
        self.description = self._entry(right, "Description")
        self.description.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(
            right,
            text="Associated active doctors",
            font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(10, 2))
        self.associated_doctors = self._message(right)
        self.associated_doctors.pack(fill="x", padx=18, pady=(0, 6))
        self.message = self._message(right)
        self.message.pack(fill="x", padx=18, pady=8)
        ctk.CTkButton(
            right,
            text="Save department",
            command=self.save,
        ).pack(fill="x", padx=18, pady=5)
        self.toggle_button = ctk.CTkButton(
            right,
            text="Deactivate selected",
            fg_color=("#b8433d", "#8e302b"),
            hover_color=("#9e3732", "#752722"),
            command=self.toggle_active,
        )
        self.toggle_button.pack(fill="x", padx=18, pady=5)
        ctk.CTkButton(
            right,
            text="Clear form",
            fg_color="transparent",
            border_width=1,
            command=self.clear_form,
        ).pack(fill="x", padx=18, pady=(5, 16))

    def refresh(self) -> None:
        try:
            page = self.service.search(
                self.session.session_token,
                name=self.search_entry.get().strip() or None,
                limit=self.PAGE_SIZE,
                offset=self.offset,
            )
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Department search failed.")
            self.show_message(
                self.message,
                "Could not load departments. Check the application log.",
                error=True,
            )
            return

        self.replace_list(self.list_frame)
        self.total_count = page.total_count
        self._update_pagination()
        ctk.CTkLabel(
            self.list_frame,
            text=f"{page.total_count} department(s)",
            text_color=("gray40", "gray65"),
        ).pack(anchor="w", padx=8, pady=(4, 8))
        for department in page.items:
            state = "Active" if department.is_active else "Inactive"
            ctk.CTkButton(
                self.list_frame,
                text=f"#{department.department_id}  ·  {department.name}  ·  {state}",
                anchor="w",
                fg_color="transparent",
                border_width=1,
                text_color=("gray10", "gray90"),
                command=lambda selected=department: self.select(selected),
            ).pack(fill="x", padx=4, pady=3)

    def select(self, department: Department) -> None:
        self.selected_id = department.department_id
        self._set_entry(self.name, department.name)
        self._set_entry(self.description, department.description)
        try:
            doctors = self.doctor_service.search(
                self.session.session_token,
                department_id=department.department_id,
                is_active=True,
                limit=200,
            )
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Associated department doctors could not be loaded.")
            self.show_message(
                self.associated_doctors,
                "Could not load associated doctors.",
                error=True,
            )
        else:
            names = [doctor.full_name for doctor in doctors.items]
            self.show_message(
                self.associated_doctors,
                ", ".join(names) if names else "No active doctors.",
                error=False,
            )
        self.toggle_button.configure(
            text="Deactivate selected"
            if department.is_active
            else "Reactivate selected"
        )

    def save(self) -> None:
        try:
            if self.selected_id is None:
                self.service.create(
                    self.session.session_token,
                    self.name.get(),
                    self.description.get(),
                )
                message = "Department created."
            else:
                updated = self.service.update(
                    self.session.session_token,
                    self.selected_id,
                    self.name.get(),
                    self.description.get(),
                )
                if updated is None:
                    self.show_message(
                        self.message,
                        "The selected department no longer exists.",
                        error=True,
                    )
                    self.refresh()
                    return
                message = "Department updated."
        except ValueError as error:
            self.show_message(self.message, str(error), error=True)
            return
        except PermissionError as error:
            self.show_message(self.message, str(error), error=True)
            return
        except PersistenceConflictError:
            self.show_message(
                self.message,
                "A department with that name already exists.",
                error=True,
            )
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Department save failed.")
            self.show_message(
                self.message,
                "Could not save the department. Check the application log.",
                error=True,
            )
            return
        self.show_message(self.message, message, error=False)
        self.refresh()

    def toggle_active(self) -> None:
        if self.selected_id is None:
            self.show_message(
                self.message,
                "Select a department first.",
                error=True,
            )
            return
        try:
            department = self.service.find_by_id(
                self.session.session_token,
                self.selected_id,
            )
            if department is None:
                self.show_message(
                    self.message,
                    "The selected department no longer exists.",
                    error=True,
                )
                self.refresh()
                return
            updated = self.service.set_active(
                self.session.session_token,
                self.selected_id,
                not department.is_active,
            )
            message = (
                "Department reactivated."
                if department.is_active is False
                else "Department deactivated."
            )
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Department status change failed.")
            self.show_message(
                self.message,
                "Could not change department status. Check the application log.",
                error=True,
            )
            return
        if updated is not None:
            self.show_message(self.message, message, error=False)
        self.refresh()

    def clear_form(self) -> None:
        self.selected_id = None
        self._set_entry(self.name, "")
        self._set_entry(self.description, "")
        self.toggle_button.configure(text="Deactivate selected")


class DoctorDirectoryScreen(DirectoryScreen):
    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        service: DoctorService,
        on_back: Callable[[], None],
        *,
        own_profile: bool = False,
    ) -> None:
        title = "My doctor profile" if own_profile else "Doctor directory"
        super().__init__(master, title, on_back)
        self.session = session
        self.service = service
        self.own_profile = own_profile
        self.can_manage = session.role in {UserRole.OWNER, UserRole.ADMIN}
        self.selected_id: int | None = None
        self._build()
        if own_profile:
            self.load_profile()
        else:
            self.refresh()

    def _build(self) -> None:
        left, right = self._panels()
        self.list_frame = ctk.CTkScrollableFrame(left, corner_radius=12)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self._create_pagination(left)
        self.search_entry = self._entry(left, "Search by doctor name")
        self.search_entry.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkButton(
            left,
            text="Search directory",
            command=self.reset_search,
        ).pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            right,
            text="Doctor directory details",
            font=ctk.CTkFont(family=_FONT, size=17, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))
        self.user_id = self._entry(right, "Existing Doctor account ID")
        self.department_id = self._entry(right, "Active department ID")
        self.full_name = self._entry(right, "Full name")
        self.specialty = self._entry(right, "Specialty")
        self.phone = self._entry(right, "Phone (optional)")
        for entry in (
            self.user_id,
            self.department_id,
            self.full_name,
            self.specialty,
            self.phone,
        ):
            entry.pack(fill="x", padx=18, pady=5)
        self.message = self._message(right)
        self.message.pack(fill="x", padx=18, pady=7)
        self.save_button = ctk.CTkButton(
            right,
            text="Save doctor profile",
            command=self.save,
        )
        self.save_button.pack(fill="x", padx=18, pady=5)
        self.toggle_button = ctk.CTkButton(
            right,
            text="Deactivate selected",
            fg_color=("#b8433d", "#8e302b"),
            hover_color=("#9e3732", "#752722"),
            command=self.toggle_active,
        )
        self.toggle_button.pack(fill="x", padx=18, pady=5)
        self.clear_button = ctk.CTkButton(
            right,
            text="Clear form",
            fg_color="transparent",
            border_width=1,
            command=self.clear_form,
        )
        self.clear_button.pack(fill="x", padx=18, pady=(5, 16))
        if not self.can_manage:
            for widget in (
                self.user_id,
                self.department_id,
                self.full_name,
                self.specialty,
                self.phone,
                self.save_button,
                self.toggle_button,
                self.clear_button,
            ):
                widget.configure(state="disabled")
        if self.own_profile:
            self.list_frame.pack_forget()
            self.previous_button.master.pack_forget()
            self.search_entry.pack_forget()

    def refresh(self) -> None:
        try:
            page = self.service.search(
                self.session.session_token,
                full_name=self.search_entry.get().strip() or None,
                limit=self.PAGE_SIZE,
                offset=self.offset,
            )
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Doctor directory search failed.")
            self.show_message(
                self.message,
                "Could not load the doctor directory. Check the application log.",
                error=True,
            )
            return

        self.replace_list(self.list_frame)
        self.total_count = page.total_count
        self._update_pagination()
        ctk.CTkLabel(
            self.list_frame,
            text=f"{page.total_count} doctor(s)",
            text_color=("gray40", "gray65"),
        ).pack(anchor="w", padx=8, pady=(4, 8))
        for doctor in page.items:
            state = "Active" if doctor.is_active else "Inactive"
            ctk.CTkButton(
                self.list_frame,
                text=(
                    f"{doctor.full_name}  ·  {doctor.specialty}  ·  "
                    f"Department {doctor.department_id}  ·  {state}"
                ),
                anchor="w",
                fg_color="transparent",
                border_width=1,
                text_color=("gray10", "gray90"),
                command=lambda selected=doctor: self.select(selected),
            ).pack(fill="x", padx=4, pady=3)

    def load_profile(self) -> None:
        try:
            doctor = self.service.find_my_profile(self.session.session_token)
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Doctor profile lookup failed.")
            self.show_message(
                self.message,
                "Could not load your profile. Check the application log.",
                error=True,
            )
            return
        if doctor is None:
            self.show_message(
                self.message,
                "No doctor directory profile is linked to this account.",
                error=True,
            )
            return
        self.select(doctor)

    def select(self, doctor: Doctor) -> None:
        self.selected_id = doctor.doctor_id
        self._set_entry(self.user_id, str(doctor.user_id))
        self.user_id.configure(state="disabled")
        self._set_entry(self.department_id, str(doctor.department_id))
        self._set_entry(self.full_name, doctor.full_name)
        self._set_entry(self.specialty, doctor.specialty)
        self._set_entry(self.phone, doctor.phone or "")
        self.toggle_button.configure(
            text="Deactivate selected"
            if doctor.is_active
            else "Reactivate selected"
        )

    def save(self) -> None:
        try:
            department_id = self._positive_int(
                self.department_id.get(),
                "department ID",
            )
            if self.selected_id is None:
                user_id = self._positive_int(self.user_id.get(), "user ID")
                self.service.create(
                    self.session.session_token,
                    user_id,
                    department_id,
                    self.full_name.get(),
                    self.specialty.get(),
                    self.phone.get(),
                )
                message = "Doctor directory entry created."
            else:
                doctor = self.service.update(
                    self.session.session_token,
                    self.selected_id,
                    department_id,
                    self.full_name.get(),
                    self.specialty.get(),
                    self.phone.get(),
                )
                if doctor is None:
                    self.show_message(
                        self.message,
                        "The selected doctor no longer exists.",
                        error=True,
                    )
                    self.refresh()
                    return
                message = "Doctor directory entry updated."
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except PersistenceConflictError:
            self.show_message(
                self.message,
                "That account is already linked to a doctor profile.",
                error=True,
            )
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Doctor directory save failed.")
            self.show_message(
                self.message,
                "Could not save the doctor entry. Check the application log.",
                error=True,
            )
            return
        self.show_message(self.message, message, error=False)
        self.refresh()

    def clear_form(self) -> None:
        self.selected_id = None
        self._set_entry(self.user_id, "")
        self.user_id.configure(state="normal" if self.can_manage else "disabled")
        self._set_entry(self.department_id, "")
        self._set_entry(self.full_name, "")
        self._set_entry(self.specialty, "")
        self._set_entry(self.phone, "")
        self.toggle_button.configure(text="Deactivate selected")

    def toggle_active(self) -> None:
        if self.selected_id is None:
            self.show_message(self.message, "Select a doctor first.", error=True)
            return
        try:
            current = self.service.find_by_id(
                self.session.session_token,
                self.selected_id,
            )
            if current is None:
                self.show_message(
                    self.message,
                    "The selected doctor no longer exists.",
                    error=True,
                )
                self.refresh()
                return
            updated = self.service.set_active(
                self.session.session_token,
                self.selected_id,
                not current.is_active,
            )
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Doctor activation change failed.")
            self.show_message(
                self.message,
                "Could not change doctor status. Check the application log.",
                error=True,
            )
            return
        if updated is not None:
            self.show_message(
                self.message,
                "Doctor profile and linked account status updated.",
                error=False,
            )
        self.refresh()


class PatientDirectoryScreen(DirectoryScreen):
    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        service: PatientService,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(master, "Patient demographics", on_back)
        self.session = session
        self.service = service
        self.can_create = session.role is not UserRole.DOCTOR
        self.selected_id: int | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        left, right = self._panels()
        self.list_frame = ctk.CTkScrollableFrame(left, corner_radius=12)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self._create_pagination(left)
        self.search_entry = self._entry(left, "Search by patient number or name")
        self.search_entry.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkButton(
            left,
            text="Search patients",
            command=self.reset_search,
        ).pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            right,
            text="Demographic details",
            font=ctk.CTkFont(family=_FONT, size=17, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))
        self.patient_number = self._entry(right, "Patient number")
        self.patient_number.pack(fill="x", padx=18, pady=5)
        self.full_name = self._entry(right, "Full name")
        self.full_name.pack(fill="x", padx=18, pady=5)
        self.date_of_birth = self._entry(right, "Date of birth (YYYY-MM-DD)")
        self.date_of_birth.pack(fill="x", padx=18, pady=5)
        self.sex = self._entry(right, "Sex (optional)")
        self.sex.pack(fill="x", padx=18, pady=5)
        self.phone = self._entry(right, "Phone (optional)")
        self.phone.pack(fill="x", padx=18, pady=5)
        self.address = self._entry(right, "Address (optional)")
        self.address.pack(fill="x", padx=18, pady=5)
        self.emergency_contact = self._entry(right, "Emergency contact (optional)")
        self.emergency_contact.pack(fill="x", padx=18, pady=5)
        self.message = self._message(right)
        self.message.pack(fill="x", padx=18, pady=7)
        self.save_button = ctk.CTkButton(
            right,
            text="Save patient",
            command=self.save,
        )
        self.save_button.pack(fill="x", padx=18, pady=5)
        self.toggle_button = ctk.CTkButton(
            right,
            text="Deactivate selected",
            fg_color=("#b8433d", "#8e302b"),
            hover_color=("#9e3732", "#752722"),
            command=self.toggle_active,
        )
        self.toggle_button.pack(fill="x", padx=18, pady=5)
        ctk.CTkButton(
            right,
            text="Clear form",
            fg_color="transparent",
            border_width=1,
            command=self.clear_form,
        ).pack(fill="x", padx=18, pady=(5, 16))
        if not self.can_create:
            self.patient_number.configure(state="disabled")
            self.save_button.configure(text="Update demographics")

    def refresh(self) -> None:
        query = self.search_entry.get().strip()
        try:
            page = self.service.search(
                self.session.session_token,
                query=query or None,
                limit=self.PAGE_SIZE,
                offset=self.offset,
            )
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Patient search failed.")
            self.show_message(
                self.message,
                "Could not load patients. Check the application log.",
                error=True,
            )
            return

        self.replace_list(self.list_frame)
        self.total_count = page.total_count
        self._update_pagination()
        ctk.CTkLabel(
            self.list_frame,
            text=f"{page.total_count} patient(s)",
            text_color=("gray40", "gray65"),
        ).pack(anchor="w", padx=8, pady=(4, 8))
        for patient in page.items:
            state = "Active" if patient.is_active else "Inactive"
            ctk.CTkButton(
                self.list_frame,
                text=(
                    f"{patient.patient_number}  ·  {patient.full_name}  ·  {state}"
                ),
                anchor="w",
                fg_color="transparent",
                border_width=1,
                text_color=("gray10", "gray90"),
                command=lambda selected=patient: self.select(selected),
            ).pack(fill="x", padx=4, pady=3)

    def select(self, patient: Patient) -> None:
        self.selected_id = patient.patient_id
        self._set_entry(self.patient_number, patient.patient_number)
        self._set_entry(self.full_name, patient.full_name)
        self._set_entry(self.date_of_birth, patient.date_of_birth)
        self._set_entry(self.sex, patient.sex or "")
        self._set_entry(self.phone, patient.phone or "")
        self._set_entry(self.address, patient.address or "")
        self._set_entry(self.emergency_contact, patient.emergency_contact or "")
        self.patient_number.configure(state="disabled")
        self.toggle_button.configure(
            text="Deactivate selected"
            if patient.is_active
            else "Reactivate selected"
        )

    def save(self) -> None:
        try:
            if self.selected_id is None:
                if not self.can_create:
                    self.show_message(
                        self.message,
                        "Doctors can edit demographics only for patients in their care.",
                        error=True,
                    )
                    return
                self.service.create(
                    self.session.session_token,
                    self.patient_number.get(),
                    self.full_name.get(),
                    self.date_of_birth.get(),
                    sex=self.sex.get(),
                    phone=self.phone.get(),
                    address=self.address.get(),
                    emergency_contact=self.emergency_contact.get(),
                )
                message = "Patient demographics saved."
            else:
                updated = self.service.update_demographics(
                    self.session.session_token,
                    self.selected_id,
                    self.full_name.get(),
                    self.date_of_birth.get(),
                    sex=self.sex.get(),
                    phone=self.phone.get(),
                    address=self.address.get(),
                    emergency_contact=self.emergency_contact.get(),
                )
                if updated is None:
                    self.show_message(
                        self.message,
                        "The selected patient no longer exists.",
                        error=True,
                    )
                    self.refresh()
                    return
                message = "Patient demographics updated."
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except PersistenceConflictError:
            self.show_message(
                self.message,
                "That patient number is already in use.",
                error=True,
            )
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Patient save failed.")
            self.show_message(
                self.message,
                "Could not save patient demographics. Check the application log.",
                error=True,
            )
            return
        self.show_message(self.message, message, error=False)
        self.clear_form()
        self.refresh()

    def toggle_active(self) -> None:
        if self.selected_id is None:
            self.show_message(self.message, "Select a patient first.", error=True)
            return
        try:
            current = self.service.find_by_id(
                self.session.session_token,
                self.selected_id,
            )
            if current is None:
                self.show_message(
                    self.message,
                    "The selected patient no longer exists.",
                    error=True,
                )
                self.refresh()
                return
            updated = self.service.set_active(
                self.session.session_token,
                self.selected_id,
                not current.is_active,
            )
        except (ValueError, PermissionError) as error:
            self.show_message(self.message, str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Patient activation change failed.")
            self.show_message(
                self.message,
                "Could not change patient status. Check the application log.",
                error=True,
            )
            return
        if updated is not None:
            self.show_message(self.message, "Patient status updated.", error=False)
        self.refresh()

    def clear_form(self) -> None:
        self.selected_id = None
        self._set_entry(self.patient_number, "")
        self._set_entry(self.full_name, "")
        self._set_entry(self.date_of_birth, "")
        self._set_entry(self.sex, "")
        self._set_entry(self.phone, "")
        self._set_entry(self.address, "")
        self._set_entry(self.emergency_contact, "")
        self.patient_number.configure(
            state="normal" if self.can_create else "disabled"
        )
        self.toggle_button.configure(text="Deactivate selected")
