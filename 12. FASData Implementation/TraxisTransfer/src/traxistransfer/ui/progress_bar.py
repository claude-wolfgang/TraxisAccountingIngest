"""Transfer progress bar with status text."""

import customtkinter as ctk

from traxistransfer.ui.styles import *


class TransferProgress(ctk.CTkFrame):
    """Progress bar with status text for transfers."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", height=50, **kwargs)
        self.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            self, text="", font=FONT_BODY,
            text_color=COLOR_TEXT,
        )
        self._status_label.pack(fill="x", padx=PADDING)

        self._progress_bar = ctk.CTkProgressBar(
            self, height=16, corner_radius=4,
            fg_color=COLOR_BG_TERTIARY,
            progress_color=COLOR_ACCENT,
        )
        self._progress_bar.pack(fill="x", padx=PADDING, pady=(4, 0))
        self._progress_bar.set(0)

        self.pack_forget()  # Hidden by default

    def update_progress(self, message: str, value: float = 0):
        """Show progress. value is 0.0-1.0."""
        self.pack(fill="x", pady=(0, PADDING))
        self._status_label.configure(text=message)
        self._progress_bar.set(max(0.0, min(1.0, value)))

    def reset(self):
        """Hide the progress bar."""
        self._progress_bar.set(0)
        self._status_label.configure(text="")
        self.pack_forget()
