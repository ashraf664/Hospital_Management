"""Role-specific dashboard screen."""

from collections.abc import Callable

import customtkinter as ctk

from models.enums import UserRole
from services.session import AuthenticatedSession
from ui.dashboard import dashboard_features_for


class DashboardScreen(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTk,
        session: AuthenticatedSession,
        on_logout: Callable[[], None],
        on_open_feature: Callable[[str], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.on_logout = on_logout
        self.on_open_feature = on_open_feature
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text="Hospital Management",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
        ).pack(side="left", padx=32)
        ctk.CTkButton(
            header,
            text="Sign out",
            width=110,
            command=self.on_logout,
        ).pack(side="right", padx=32)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=34, pady=26)
        ctk.CTkLabel(
            content,
            text=f"Welcome, {self.session.username}",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            content,
            text=f"{self.session.role.value} workspace",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(family="Segoe UI", size=15),
        ).pack(anchor="w", pady=(2, 20))

        cards = ctk.CTkScrollableFrame(
            content,
            corner_radius=14,
            fg_color=("gray92", "gray14"),
        )
        cards.pack(fill="both", expand=True)
        for column in range(3):
            cards.grid_columnconfigure(column, weight=1)

        features = dashboard_features_for(self.session.role)
        for index, feature in enumerate(features):
            row, column = divmod(index, 3)
            card = ctk.CTkFrame(cards, corner_radius=14, height=178)
            card.grid(
                row=row,
                column=column,
                padx=12,
                pady=12,
                sticky="nsew",
            )
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card,
                text=feature.title,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            ).grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
            ctk.CTkLabel(
                card,
                text=feature.description,
                anchor="nw",
                justify="left",
                wraplength=250,
                height=48,
                text_color=("gray35", "gray70"),
                font=ctk.CTkFont(family="Segoe UI", size=13),
            ).grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")

            if feature.available:
                ctk.CTkButton(
                    card,
                    text="Open",
                    height=34,
                    command=lambda key=feature.key: self.on_open_feature(key),
                ).grid(row=2, column=0, padx=18, pady=(0, 16), sticky="ew")
            else:
                ctk.CTkLabel(
                    card,
                    text="Module not connected yet",
                    text_color=("gray45", "gray60"),
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                ).grid(row=2, column=0, padx=18, pady=(0, 16), sticky="w")

        if self.session.role in {UserRole.OWNER, UserRole.ADMIN}:
            ctk.CTkLabel(
                content,
                text=(
                    "Administrative access does not include medical-record "
                    "contents."
                ),
                text_color=("gray40", "gray65"),
                font=ctk.CTkFont(family="Segoe UI", size=12),
            ).pack(anchor="w", pady=(12, 0))
