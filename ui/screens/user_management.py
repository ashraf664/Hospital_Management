"""Service-backed staff account creation screen."""

from collections.abc import Callable
import logging
import sqlite3

import customtkinter as ctk

from models.enums import UserRole
from services import PersistenceConflictError, PersistenceError
from services.user_administration_service import UserAdministrationService
from services.session import AuthenticatedSession


_LOGGER = logging.getLogger(__name__)
_ROLE_OPTIONS = {
    "Admin": UserRole.ADMIN,
    "Doctor": UserRole.DOCTOR,
    "Receptionist": UserRole.RECEPTIONIST,
}


class UserManagementScreen(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        user_administration: UserAdministrationService,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.user_administration = user_administration
        self.on_back = on_back
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self) -> None:
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=44, pady=34)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(0, 24))
        ctk.CTkButton(
            header,
            text="Back to dashboard",
            width=150,
            command=self.on_back,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Create staff account",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
        ).pack(side="right")

        card = ctk.CTkFrame(page, corner_radius=16, width=560)
        card.pack(anchor="n", fill="x", padx=80, pady=12)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text="Ordinary staff account",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        ).grid(row=0, column=0, padx=30, pady=(28, 8), sticky="w")
        ctk.CTkLabel(
            card,
            text=(
                "Owner accounts cannot be created here. Arabic usernames "
                "and text are supported."
            ),
            wraplength=460,
            justify="left",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=1, column=0, padx=30, pady=(0, 16), sticky="w")

        self.username = ctk.CTkEntry(
            card,
            height=40,
            placeholder_text="Username",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.username.grid(row=2, column=0, padx=30, pady=7, sticky="ew")
        self.password = ctk.CTkEntry(
            card,
            height=40,
            placeholder_text="Temporary password (at least 12 characters)",
            show="*",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.password.grid(row=3, column=0, padx=30, pady=7, sticky="ew")
        self.role = ctk.CTkOptionMenu(
            card,
            values=list(_ROLE_OPTIONS),
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.role.grid(row=4, column=0, padx=30, pady=7, sticky="ew")

        self.feedback = ctk.CTkLabel(
            card,
            text="",
            wraplength=460,
            text_color="#c2413b",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.feedback.grid(row=5, column=0, padx=30, pady=(8, 4), sticky="w")
        ctk.CTkButton(
            card,
            text="Create account",
            height=42,
            command=self._create_account,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        ).grid(row=6, column=0, padx=30, pady=(8, 28), sticky="ew")

    def _create_account(self) -> None:
        username = self.username.get().strip()
        password = self.password.get()
        self.password.delete(0, "end")
        if not username:
            self._show_feedback("Enter a username.")
            return
        if len(password) < 12:
            self._show_feedback("Password must contain at least 12 characters.")
            return

        selected_role = _ROLE_OPTIONS[self.role.get()]
        try:
            created = self.user_administration.create_user(
                self.session.session_token,
                username,
                password,
                selected_role,
            )
        except ValueError as error:
            self._show_feedback(str(error))
        except PermissionError as error:
            self._show_feedback(str(error))
        except PersistenceConflictError:
            self._show_feedback("That username is already in use.")
        except (PersistenceError, sqlite3.Error):
            _LOGGER.exception("Could not create a staff account.")
            self._show_feedback(
                "The account could not be saved. Check the application log."
            )
        else:
            self.username.delete(0, "end")
            self._show_feedback(
                f"Account '{username}' was created. User ID: {created.user_id}.",
                error=False,
            )

    def _show_feedback(self, message: str, *, error: bool = True) -> None:
        self.feedback.configure(
            text=message,
            text_color="#c2413b" if error else "#278357",
        )
