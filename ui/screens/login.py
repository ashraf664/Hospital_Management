"""Sign-in screen."""

from collections.abc import Callable

import customtkinter as ctk


class LoginScreen(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTk,
        on_login: Callable[[str, str], None],
        *,
        message: str = "",
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_login = on_login
        self.pack(fill="both", expand=True)

        card = ctk.CTkFrame(self, corner_radius=18, width=440)
        card.place(relx=0.5, rely=0.47, anchor="center")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="Hospital Management",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
        ).grid(row=0, column=0, padx=36, pady=(36, 5))
        ctk.CTkLabel(
            card,
            text="Secure staff sign in",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(family="Segoe UI", size=15),
        ).grid(row=1, column=0, padx=36, pady=(0, 25))

        self.username = ctk.CTkEntry(
            card,
            width=340,
            height=42,
            placeholder_text="Username",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.username.grid(row=2, column=0, padx=36, pady=8)
        self.password = ctk.CTkEntry(
            card,
            width=340,
            height=42,
            placeholder_text="Password",
            show="*",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.password.grid(row=3, column=0, padx=36, pady=8)
        self.password.bind("<Return>", self._submit_event)

        ctk.CTkLabel(
            card,
            text="Arabic usernames and text are supported.",
            text_color=("gray40", "gray65"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).grid(row=4, column=0, padx=36, pady=(4, 8))
        self.feedback = ctk.CTkLabel(
            card,
            text=message,
            text_color="#c2413b",
            wraplength=330,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.feedback.grid(row=5, column=0, padx=36, pady=(0, 8))
        self.submit_button = ctk.CTkButton(
            card,
            text="Sign in",
            width=340,
            height=42,
            command=self._submit,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        self.submit_button.grid(row=6, column=0, padx=36, pady=(4, 32))
        self.username.focus_set()

    def show_feedback(self, message: str, *, error: bool = True) -> None:
        self.feedback.configure(
            text=message,
            text_color="#c2413b" if error else "#278357",
        )

    def _submit_event(self, event: object) -> None:
        if getattr(event, "widget", None) is self.password:
            self._submit()

    def _submit(self) -> None:
        username = self.username.get().strip()
        password = self.password.get()
        self.password.delete(0, "end")
        if not username or not password:
            self.show_feedback("Enter both your username and password.")
            return
        self.submit_button.configure(state="disabled", text="Signing in...")
        try:
            self.on_login(username, password)
        finally:
            if self.winfo_exists():
                self.submit_button.configure(state="normal", text="Sign in")
