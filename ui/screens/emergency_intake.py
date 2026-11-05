"""Administrative emergency intake screen backed by EmergencyCaseService."""

from collections.abc import Callable
import logging
import sqlite3

import customtkinter as ctk

from models.enums import UserRole
from repositories.exceptions import PersistenceError
from services.emergency_case_service import EmergencyCaseService
from services.session import AuthenticatedSession


_LOGGER = logging.getLogger(__name__)
_FONT = "Segoe UI"


class EmergencyIntakeScreen(ctk.CTkFrame):
    PAGE_SIZE = 25

    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        service: EmergencyCaseService,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.service = service
        self.on_back = on_back
        self.offset = 0
        self.total_count = 0
        self.selected_case_id: int | None = None
        self.doctor_ids_by_label: dict[str, int] = {}
        self.is_doctor = session.role is UserRole.DOCTOR
        self.pack(fill="both", expand=True)
        self._build()
        if not self.is_doctor:
            self._load_doctors()
        self.refresh()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))
        ctk.CTkButton(
            header,
            text="Back to dashboard",
            width=150,
            command=self.on_back,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=(
                "Assigned emergency cases"
                if self.is_doctor
                else "Emergency intake"
            ),
            font=ctk.CTkFont(family=_FONT, size=24, weight="bold"),
        ).pack(side="right")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        listing = ctk.CTkFrame(content, corner_radius=14)
        listing.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        editor = ctk.CTkFrame(content, corner_radius=14)
        editor.grid(row=0, column=1, padx=(8, 0), sticky="nsew")

        filters = ctk.CTkFrame(listing, fg_color="transparent")
        filters.pack(fill="x", padx=12, pady=12)
        self.case_filter = self._entry(filters, "Case number")
        self.case_filter.pack(fill="x", pady=3)
        self.patient_filter = self._entry(filters, "Patient ID")
        self.patient_filter.pack(fill="x", pady=3)
        self.arrival_filter = self._entry(filters, "Arrival date (YYYY-MM-DD)")
        self.arrival_filter.pack(fill="x", pady=3)
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
            text="Case intake",
            font=ctk.CTkFont(family=_FONT, size=18, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        if not self.is_doctor:
            self.new_patient_id = self._entry(
                editor,
                "New case: patient ID (optional)",
            )
            self.new_patient_id.pack(fill="x", padx=16, pady=4)
            self.patient_id = self._entry(
                editor,
                "Selected case: patient ID to link",
            )
            self.patient_id.pack(fill="x", padx=16, pady=4)
            self.doctor_choice = ctk.CTkOptionMenu(
                editor,
                values=["No doctor assigned"],
            )
            self.doctor_choice.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(
            editor,
            text="Record intake notes (existing note contents are never retrieved here)",
            wraplength=310,
            justify="left",
            font=ctk.CTkFont(family=_FONT, size=12),
        ).pack(anchor="w", padx=16, pady=(10, 4))
        self.intake_notes = ctk.CTkTextbox(editor, height=76)
        self.intake_notes.pack(fill="x", padx=16, pady=4)
        self.change_reason = self._entry(editor, "Change reason")
        self.change_reason.pack(fill="x", padx=16, pady=4)

        actions = ctk.CTkFrame(editor, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=6)
        if not self.is_doctor:
            ctk.CTkButton(
                actions,
                text="Create case",
                command=self._create_case,
            ).pack(fill="x", pady=3)
            ctk.CTkButton(
                actions,
                text="Link patient to selected case",
                command=self._link_patient,
            ).pack(fill="x", pady=3)
            ctk.CTkButton(
                actions,
                text="Assign / reassign doctor",
                command=self._assign_doctor,
            ).pack(fill="x", pady=3)
        ctk.CTkButton(
            actions,
            text="Update intake notes",
            command=self._update_notes,
        ).pack(fill="x", pady=3)

        ctk.CTkLabel(
            editor,
            text="Selected case details",
            font=ctk.CTkFont(family=_FONT, size=15, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(10, 3))
        self.details = ctk.CTkLabel(
            editor,
            text="Select a case to view administrative details.",
            anchor="w",
            justify="left",
            wraplength=330,
        )
        self.details.pack(fill="x", padx=16, pady=(0, 8))
        self.feedback = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            text_color=("gray35", "gray70"),
        )
        self.feedback.pack(fill="x", padx=28, pady=(0, 12))

    def refresh(self) -> None:
        try:
            page = self.service.search_cases(
                self.session.session_token,
                case_number=self.case_filter.get().strip() or None,
                patient_id=self._optional_integer(self.patient_filter.get()),
                arrival_date=self.arrival_filter.get().strip() or None,
                status=self.status_filter.get().strip() or None,
                limit=self.PAGE_SIZE,
                offset=self.offset,
            )
        except (ValueError, PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return

        self.total_count = page.total_count
        for child in self.list_frame.winfo_children():
            child.destroy()
        if not page.items:
            ctk.CTkLabel(self.list_frame, text="No cases found.").pack(
                anchor="w",
                padx=8,
                pady=8,
            )
        for case in page.items:
            patient = str(case.patient_id) if case.patient_id is not None else "Unlinked"
            doctor = (
                str(case.assigned_doctor_id)
                if case.assigned_doctor_id is not None
                else "Unassigned"
            )
            text = (
                f"{case.case_number}  |  Patient: {patient}  |  "
                f"Doctor: {doctor}  |  {case.status}\n{case.arrival_at}"
            )
            ctk.CTkButton(
                self.list_frame,
                text=text,
                anchor="w",
                height=56,
                command=lambda case_id=case.emergency_case_id: self._select(case_id),
            ).pack(fill="x", padx=4, pady=3)

        start = self.offset + 1 if self.total_count else 0
        end = min(self.offset + len(page.items), self.total_count)
        self.page_label.configure(text=f"{start}-{end} of {self.total_count}")
        self.previous_button.configure(state="normal" if self.offset else "disabled")
        self.next_button.configure(
            state=(
                "normal"
                if self.offset + len(page.items) < self.total_count
                else "disabled"
            )
        )

    def _load_doctors(self) -> None:
        try:
            doctors = self.service.active_doctors(self.session.session_token)
        except (PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return
        values = ["No doctor assigned"]
        for doctor in doctors:
            label = f"{doctor.doctor_id} — {doctor.full_name}"
            self.doctor_ids_by_label[label] = int(doctor.doctor_id)
            values.append(label)
        self.doctor_choice.configure(values=values)
        self.doctor_choice.set(values[0])

    def _select(self, case_id: int) -> None:
        try:
            case = self.service.find_case(case_id, self.session.session_token)
        except (PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return
        if case is None:
            self._show_feedback("The case no longer exists.")
            self.refresh()
            return
        self.selected_case_id = case_id
        if not self.is_doctor:
            self.patient_id.delete(0, "end")
            if case.patient_id is not None:
                self.patient_id.insert(0, str(case.patient_id))
        self.intake_notes.delete("1.0", "end")
        self.details.configure(
            text=(
                f"Case: {case.case_number}\n"
                f"Patient ID: {case.patient_id or 'Not linked'}\n"
                f"Assigned doctor ID: "
                f"{case.assigned_doctor_id or 'Unassigned'}\n"
                f"Status: {case.status}\n"
                f"Arrival: {case.arrival_at}"
            )
        )
        self._show_feedback(f"Selected {case.case_number}.")

    def _create_case(self) -> None:
        try:
            patient_id = self._optional_integer(self.new_patient_id.get())
            doctor_id = self._selected_doctor_id()
            reason = self.change_reason.get().strip()
            case = self.service.create_case(
                self.session.session_token,
                patient_id=patient_id,
                intake_notes=self.intake_notes.get("1.0", "end").strip(),
                assigned_doctor_id=doctor_id,
                assignment_reason=reason if doctor_id is not None else None,
            )
        except (ValueError, PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return
        self.selected_case_id = case.emergency_case_id
        self.offset = 0
        self.intake_notes.delete("1.0", "end")
        self._show_feedback(f"Created emergency case {case.case_number}.")
        self.refresh()
        self._select(case.emergency_case_id)

    def _link_patient(self) -> None:
        try:
            patient_id = self._required_integer(self.patient_id.get(), "Patient ID")
        except ValueError as error:
            self._show_feedback(str(error))
            return
        case_id = self._require_selected_case()
        reason = self.change_reason.get().strip()
        if case_id is None:
            return
        try:
            case = self.service.link_patient(
                case_id,
                patient_id,
                self.session.session_token,
                reason,
            )
        except (ValueError, PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return
        self._finish_write(case, "Patient linked.")

    def _assign_doctor(self) -> None:
        case_id = self._require_selected_case()
        doctor_id = self._selected_doctor_id()
        reason = self.change_reason.get().strip()
        if case_id is None:
            return
        if doctor_id is None:
            self._show_feedback("Select an active doctor before assigning.")
            return
        try:
            case = self.service.assign_doctor(
                case_id,
                doctor_id,
                self.session.session_token,
                reason,
            )
        except (ValueError, PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return
        self._finish_write(case, "Doctor assignment saved.")

    def _update_notes(self) -> None:
        case_id = self._require_selected_case()
        reason = self.change_reason.get().strip()
        if case_id is None:
            return
        try:
            case = self.service.update_intake_notes(
                case_id,
                self.intake_notes.get("1.0", "end").strip(),
                self.session.session_token,
                reason,
            )
        except (ValueError, PermissionError, PersistenceError, sqlite3.Error) as error:
            self._show_error(error)
            return
        self._finish_write(case, "Intake notes updated.")

    def _finish_write(self, case, message: str) -> None:
        if case is None:
            self._show_feedback("No matching case was found.")
            return
        self._show_feedback(message)
        self.refresh()
        self._select(case.emergency_case_id)

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

    def _require_selected_case(self) -> int | None:
        if self.selected_case_id is None:
            self._show_feedback("Select a case first.")
            return None
        return self.selected_case_id

    def _selected_doctor_id(self) -> int | None:
        return self.doctor_ids_by_label.get(self.doctor_choice.get())

    @staticmethod
    def _optional_integer(value: str) -> int | None:
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            result = int(cleaned)
        except ValueError as error:
            raise ValueError("ID fields must contain a positive integer.") from error
        if result <= 0:
            raise ValueError("ID fields must contain a positive integer.")
        return result

    def _required_integer(self, value: str, label: str) -> int:
        result = self._optional_integer(value)
        if result is None:
            raise ValueError(f"{label} is required.")
        return result

    @staticmethod
    def _entry(master, placeholder: str) -> ctk.CTkEntry:
        return ctk.CTkEntry(master, placeholder_text=placeholder, height=34)

    def _show_error(self, error: Exception) -> None:
        if isinstance(error, (PersistenceError, sqlite3.Error)):
            _LOGGER.error(
                "Emergency intake operation failed.",
                exc_info=(type(error), error, error.__traceback__),
            )
            self._show_feedback(
                "The operation could not be completed. Check the application log."
            )
        else:
            self._show_feedback(str(error))

    def _show_feedback(self, message: str) -> None:
        self.feedback.configure(text=message)
