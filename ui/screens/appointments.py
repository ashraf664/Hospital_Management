"""Service-backed appointment schedule and management screen."""

from collections.abc import Callable
from datetime import datetime
import logging
import sqlite3

import customtkinter as ctk

from models import Appointment, UserRole
from services.appointment_service import AppointmentService
from services.session import AuthenticatedSession
from repositories.exceptions import PersistenceError


_LOGGER = logging.getLogger(__name__)
_FONT = "Segoe UI"


class AppointmentScreen(ctk.CTkFrame):
    PAGE_SIZE = 50

    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        service: AppointmentService,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.service = service
        self.on_back = on_back
        self.offset = 0
        self.total_count = 0
        self.selected_id: int | None = None
        self.pack(fill="both", expand=True)
        self._build()
        self.refresh()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(20, 10))
        ctk.CTkButton(
            header,
            text="Back to dashboard",
            width=150,
            command=self.on_back,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=(
                "My schedule"
                if self.session.role is UserRole.DOCTOR
                else "Appointments"
            ),
            font=ctk.CTkFont(family=_FONT, size=24, weight="bold"),
        ).pack(side="right")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)
        listing = ctk.CTkFrame(content, corner_radius=14)
        listing.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        editor = ctk.CTkFrame(content, corner_radius=14)
        editor.grid(row=0, column=1, padx=(8, 0), sticky="nsew")

        filters = ctk.CTkFrame(listing, fg_color="transparent")
        filters.pack(fill="x", padx=12, pady=12)
        self.patient_filter = self._entry(filters, "Patient ID")
        self.patient_filter.pack(fill="x", pady=3)
        if self.session.role is not UserRole.DOCTOR:
            self.doctor_filter = self._entry(filters, "Doctor ID")
            self.doctor_filter.pack(fill="x", pady=3)
        else:
            self.doctor_filter = None
        self.start_filter = self._entry(filters, "From (ISO 8601 with timezone)")
        self.start_filter.pack(fill="x", pady=3)
        self.end_filter = self._entry(filters, "To (ISO 8601 with timezone)")
        self.end_filter.pack(fill="x", pady=3)
        self.status_filter = self._entry(filters, "Status")
        self.status_filter.pack(fill="x", pady=3)
        ctk.CTkButton(filters, text="Search", command=self.reset_search).pack(
            fill="x",
            pady=(6, 0),
        )

        self.list_frame = ctk.CTkScrollableFrame(listing, corner_radius=12)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        pagination = ctk.CTkFrame(listing, fg_color="transparent")
        pagination.pack(fill="x", padx=12, pady=(0, 10))
        self.previous_button = ctk.CTkButton(
            pagination,
            text="Previous",
            width=90,
            command=self._previous_page,
        )
        self.previous_button.pack(side="left")
        self.page_label = ctk.CTkLabel(pagination, text="0 results")
        self.page_label.pack(side="left", expand=True)
        self.next_button = ctk.CTkButton(
            pagination,
            text="Next",
            width=90,
            command=self._next_page,
        )
        self.next_button.pack(side="right")

        ctk.CTkLabel(
            editor,
            text="Appointment details",
            font=ctk.CTkFont(family=_FONT, size=17, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        self.form = ctk.CTkFrame(editor, fg_color="transparent")
        self.form.pack(fill="x", padx=16)
        self.patient_id = self._entry(self.form, "Patient ID")
        self.patient_id.pack(fill="x", pady=4)
        self.doctor_id = self._entry(self.form, "Doctor ID")
        self.doctor_id.pack(fill="x", pady=4)
        self.scheduled_start = self._entry(
            self.form,
            "Start (ISO 8601 with timezone, e.g. 2030-01-02T10:00:00Z)",
        )
        self.scheduled_start.pack(fill="x", pady=4)
        self.duration = self._entry(self.form, "Duration in minutes (default 30)")
        self.duration.insert(0, str(self.service.default_duration_minutes))
        self.duration.pack(fill="x", pady=4)
        self.cancellation_reason = self._entry(
            self.form,
            "Cancellation reason (required for Cancelled; Arabic supported)",
        )
        self.cancellation_reason.pack(fill="x", pady=4)
        self.message = ctk.CTkLabel(
            editor,
            text="",
            wraplength=340,
            justify="left",
            text_color="#c2413b",
            font=ctk.CTkFont(family=_FONT, size=12),
        )
        self.message.pack(fill="x", padx=16, pady=(8, 4))

        self.save_button: ctk.CTkButton | None = None
        self.status_menu: ctk.CTkOptionMenu | None = None
        self.status_button: ctk.CTkButton | None = None
        self.status_menu = ctk.CTkOptionMenu(
            self.form,
            values=["Select a status"],
            height=36,
            font=ctk.CTkFont(family=_FONT, size=12),
        )
        self.status_menu.pack(fill="x", pady=(10, 4))
        self.status_button = ctk.CTkButton(
            self.form,
            text="Apply status transition",
            command=self.update_status,
        )
        self.status_button.pack(fill="x", pady=4)
        if self.session.role is UserRole.DOCTOR:
            for entry in (
                self.patient_id,
                self.doctor_id,
                self.scheduled_start,
                self.duration,
                self.cancellation_reason,
            ):
                entry.configure(state="disabled")
        else:
            self.save_button = ctk.CTkButton(
                self.form,
                text="Create appointment",
                command=self.save,
            )
            self.save_button.pack(fill="x", pady=(8, 4))

    @staticmethod
    def _entry(master: ctk.CTkBaseClass, placeholder: str) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            master,
            height=36,
            placeholder_text=placeholder,
            font=ctk.CTkFont(family=_FONT, size=12),
        )

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str) -> None:
        disabled = str(entry.cget("state")) == "disabled"
        if disabled:
            entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        if disabled:
            entry.configure(state="disabled")

    def reset_search(self) -> None:
        self.offset = 0
        self.refresh()

    def refresh(self) -> None:
        try:
            page = self.service.search(
                self.session.session_token,
                patient_id=self._optional_id(self.patient_filter.get(), "patient ID"),
                doctor_id=(
                    self._optional_id(self.doctor_filter.get(), "doctor ID")
                    if self.doctor_filter is not None
                    else None
                ),
                start_from=self.start_filter.get().strip() or None,
                start_to=self.end_filter.get().strip() or None,
                status=self.status_filter.get().strip() or None,
                limit=self.PAGE_SIZE,
                offset=self.offset,
            )
        except (ValueError, PermissionError) as error:
            self._show_message(str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Appointment search failed.")
            self._show_message(
                "Could not load appointments. Check the application log.",
                error=True,
            )
            return

        for child in self.list_frame.winfo_children():
            child.destroy()
        self.total_count = page.total_count
        self._update_pagination()
        for appointment in page.items:
            ctk.CTkButton(
                self.list_frame,
                text=(
                    f"#{appointment.appointment_id}  ·  Patient "
                    f"{appointment.patient_id}  ·  Doctor {appointment.doctor_id}\n"
                    f"{appointment.scheduled_start} – {appointment.scheduled_end}"
                    f"  ·  {appointment.status}"
                ),
                anchor="w",
                height=58,
                fg_color="transparent",
                border_width=1,
                text_color=("gray10", "gray90"),
                command=lambda selected=appointment: self.select(selected),
            ).pack(fill="x", padx=4, pady=3)

    def select(self, appointment: Appointment) -> None:
        self.selected_id = appointment.appointment_id
        self._set_entry(self.patient_id, str(appointment.patient_id))
        self._set_entry(self.doctor_id, str(appointment.doctor_id))
        self._set_entry(self.scheduled_start, appointment.scheduled_start)
        start = datetime.fromisoformat(
            appointment.scheduled_start.replace("Z", "+00:00")
        )
        end = datetime.fromisoformat(
            appointment.scheduled_end.replace("Z", "+00:00")
        )
        duration_minutes = int((end - start).total_seconds() // 60)
        self._set_entry(self.duration, str(duration_minutes))
        self._load_available_transitions()
        if self.save_button is not None:
            self.save_button.configure(text="Reschedule selected appointment")
        self._show_message(f"Selected appointment #{appointment.appointment_id}.")

    def save(self) -> None:
        is_reschedule = self.selected_id is not None
        try:
            patient_id = self._positive_id(self.patient_id.get(), "patient ID")
            doctor_id = self._positive_id(self.doctor_id.get(), "doctor ID")
            duration = self._positive_id(self.duration.get(), "duration")
            if self.selected_id is None:
                self.service.create(
                    self.session.session_token,
                    patient_id,
                    doctor_id,
                    self.scheduled_start.get(),
                    duration_minutes=duration,
                )
                success = "Appointment created."
            else:
                appointment = self.service.reschedule(
                    self.session.session_token,
                    self.selected_id,
                    self.scheduled_start.get(),
                    duration_minutes=duration,
                )
                if appointment is None:
                    self._show_message("The selected appointment no longer exists.", error=True)
                    self.refresh()
                    return
                success = "Appointment rescheduled."
        except (ValueError, PermissionError) as error:
            self._show_message(str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Appointment save failed.")
            self._show_message(
                "Could not save the appointment. Check the application log.",
                error=True,
            )
            return
        if not is_reschedule:
            self._clear_selection()
        self._show_message(success)
        self.refresh()

    def update_status(self) -> None:
        if self.selected_id is None or self.status_menu is None:
            self._show_message("Select an appointment first.", error=True)
            return
        next_status = self.status_menu.get()
        if next_status not in self.service.STATUSES:
            self._show_message("Select an available status transition.", error=True)
            return
        try:
            if next_status == "Cancelled":
                appointment = self.service.cancel(
                    self.session.session_token,
                    self.selected_id,
                    self.cancellation_reason.get(),
                )
            else:
                appointment = self.service.update_status(
                    self.session.session_token,
                    self.selected_id,
                    next_status,
                )
            if appointment is None:
                self._show_message("The selected appointment no longer exists.", error=True)
                self.refresh()
                return
        except (ValueError, PermissionError) as error:
            self._show_message(str(error), error=True)
            return
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Appointment status transition failed.")
            self._show_message(
                "Could not apply the appointment status transition. "
                "Check the application log.",
                error=True,
            )
            return
        self._clear_selection()
        self._show_message(f"Appointment status changed to {appointment.status}.")
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
        self.page_label.configure(text=f"{first}-{last} of {self.total_count}")
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

    def _show_message(self, message: str, *, error: bool = False) -> None:
        self.message.configure(
            text=message,
            text_color="#c2413b" if error else "#278357",
        )

    def _clear_selection(self) -> None:
        self.selected_id = None
        if self.save_button is not None:
            self.save_button.configure(text="Create appointment")
        if self.status_menu is not None:
            self.status_menu.configure(values=["Select a status"], state="disabled")
            self.status_menu.set("Select a status")
        if self.status_button is not None:
            self.status_button.configure(state="disabled")

    def _load_available_transitions(self) -> None:
        if self.selected_id is None or self.status_menu is None:
            return
        try:
            transitions = self.service.available_transitions(
                self.session.session_token,
                self.selected_id,
            )
        except (ValueError, PermissionError) as error:
            self._show_message(str(error), error=True)
            transitions = ()
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Could not load appointment status transitions.")
            self._show_message(
                "Could not load available status transitions. "
                "Check the application log.",
                error=True,
            )
            transitions = ()
        values = transitions or ("No available transitions",)
        self.status_menu.configure(
            values=list(values),
            state="normal" if transitions else "disabled",
        )
        self.status_menu.set(values[0])
        if self.status_button is not None:
            self.status_button.configure(
                state="normal" if transitions else "disabled"
            )

    @staticmethod
    def _optional_id(value: str, field_name: str) -> int | None:
        return (
            AppointmentScreen._positive_id(value, field_name)
            if value.strip()
            else None
        )

    @staticmethod
    def _positive_id(value: str, field_name: str) -> int:
        try:
            parsed = int(value.strip())
        except ValueError as error:
            raise ValueError(f"{field_name} must be a positive integer.") from error
        if parsed < 1:
            raise ValueError(f"{field_name} must be a positive integer.")
        return parsed
