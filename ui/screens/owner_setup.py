"""First-run Owner account setup screen."""

from collections.abc import Callable

import customtkinter as ctk


class OwnerSetupScreen(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTk,
        on_create_owner: Callable[[str, str], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_create_owner = on_create_owner
        self.pack(fill="both", expand=True)

        card = ctk.CTkFrame(self, corner_radius=18, width=480)
        card.place(relx=0.5, rely=0.47, anchor="center")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="Initial Owner setup",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
        ).grid(row=0, column=0, padx=36, pady=(34, 8))
        ctk.CTkLabel(
            card,
            text=(
                "Create the single Owner account for this installation. "
                "This setup is available only while no user accounts exist."
            ),
            wraplength=380,
            justify="center",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=1, column=0, padx=36, pady=(0, 18))

        self.username = ctk.CTkEntry(
            card,
            width=370,
            height=42,
            placeholder_text="Owner username",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.username.grid(row=2, column=0, padx=36, pady=7)
        self.password = ctk.CTkEntry(
            card,
            width=370,
            height=42,
            placeholder_text="Password (at least 12 characters)",
            show="*",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.password.grid(row=3, column=0, padx=36, pady=7)
        self.confirm_password = ctk.CTkEntry(
            card,
            width=370,
            height=42,
            placeholder_text="Confirm password",
            show="*",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.confirm_password.grid(row=4, column=0, padx=36, pady=7)
        self.confirm_password.bind("<Return>", self._submit_event)

        ctk.CTkLabel(
            card,
            text="Arabic usernames and text are supported.",
            text_color=("gray40", "gray65"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).grid(row=5, column=0, padx=36, pady=(4, 6))
        self.feedback = ctk.CTkLabel(
            card,
            text="",
            text_color="#c2413b",
            wraplength=370,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.feedback.grid(row=6, column=0, padx=36, pady=(0, 8))
        self.submit_button = ctk.CTkButton(
            card,
            text="Create Owner account",
            width=370,
            height=42,
            command=self._submit,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        self.submit_button.grid(row=7, column=0, padx=36, pady=(4, 30))
        self.username.focus_set()

    def show_feedback(self, message: str, *, error: bool = True) -> None:
        self.feedback.configure(
            text=message,
            text_color="#c2413b" if error else "#278357",
        )

    def _submit_event(self, event: object) -> None:
        if getattr(event, "widget", None) is self.confirm_password:
            self._submit()

    def _submit(self) -> None:
        username = self.username.get().strip()
        password = self.password.get()
        confirmation = self.confirm_password.get()
        self.password.delete(0, "end")
        self.confirm_password.delete(0, "end")

        if not username:
            self.show_feedback("Enter a username.")
            return
        if len(password) < 12:
            self.show_feedback("Password must contain at least 12 characters.")
            return
        if password != confirmation:
            self.show_feedback("The passwords do not match.")
            return

        self.submit_button.configure(state="disabled", text="Creating account...")
        try:
            self.on_create_owner(username, password)
        finally:
            if self.winfo_exists():
                self.submit_button.configure(
                    state="normal",
                    text="Create Owner account",
                )
