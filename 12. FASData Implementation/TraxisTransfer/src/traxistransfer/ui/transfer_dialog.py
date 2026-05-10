"""Transfer confirmation dialog."""

import customtkinter as ctk

from traxistransfer.ui.styles import *


class TransferDialog(ctk.CTkToplevel):
    """Confirmation popup before sending a program."""

    def __init__(self, parent, machine_name: str, file_name: str,
                 file_size: int, program_number: str = "",
                 on_confirm=None, on_cancel=None):
        super().__init__(parent)

        self.title("Confirm Transfer")
        self.geometry("420x320")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

        # Title
        ctk.CTkLabel(
            self, text="Confirm Send", font=FONT_TITLE,
            text_color=COLOR_TEXT,
        ).pack(pady=(PADDING * 2, PADDING))

        # Details frame
        details = ctk.CTkFrame(self, fg_color=COLOR_BG_SECONDARY, corner_radius=CORNER_RADIUS)
        details.pack(fill="x", padx=PADDING * 2, pady=PADDING)

        rows = [
            ("File:", file_name),
            ("Machine:", machine_name),
            ("Size:", f"{file_size / 1024:.1f} KB"),
        ]
        if program_number:
            rows.insert(1, ("Program:", program_number))

        for label, value in rows:
            row = ctk.CTkFrame(details, fg_color="transparent")
            row.pack(fill="x", padx=PADDING, pady=4)
            ctk.CTkLabel(row, text=label, font=FONT_BODY_BOLD,
                        text_color=COLOR_TEXT_DIM, width=80, anchor="e").pack(side="left")
            ctk.CTkLabel(row, text=value, font=FONT_BODY,
                        text_color=COLOR_TEXT, anchor="w").pack(side="left", padx=8)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=PADDING * 2, pady=PADDING * 2)

        ctk.CTkButton(
            btn_frame, text="CANCEL", font=FONT_BODY,
            height=BUTTON_HEIGHT, width=120,
            fg_color=COLOR_BG_TERTIARY, hover_color="#555555",
            command=self._cancel,
        ).pack(side="left", expand=True)

        ctk.CTkButton(
            btn_frame, text="SEND", font=FONT_HEADING,
            height=BUTTON_HEIGHT, width=160,
            fg_color=COLOR_SUCCESS, hover_color="#388E3C",
            command=self._confirm,
        ).pack(side="right", expand=True)

    def _confirm(self):
        self.destroy()
        if self._on_confirm:
            self._on_confirm()

    def _cancel(self):
        self.destroy()
        if self._on_cancel:
            self._on_cancel()
