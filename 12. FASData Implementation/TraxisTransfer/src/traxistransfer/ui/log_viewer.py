"""Recent transfer history log viewer."""

from datetime import datetime
import customtkinter as ctk

from traxistransfer.ui.styles import *


class LogViewer(ctk.CTkFrame):
    """Bottom strip showing recent transfer history."""

    MAX_ENTRIES = 10

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLOR_BG_SECONDARY,
                        corner_radius=CORNER_RADIUS, height=120, **kwargs)
        self.pack_propagate(False)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING, pady=(8, 2))
        ctk.CTkLabel(
            header, text="RECENT TRANSFERS", font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        ).pack(side="left")

        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=80,
        )
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self._entries = []

    def add_entry(self, entry: dict):
        """Add a transfer log entry to the display."""
        if len(self._entries) >= self.MAX_ENTRIES:
            oldest = self._entries.pop(0)
            oldest.destroy()

        success = entry.get("success", True)
        icon = "\u2713" if success else "\u2717"
        color = COLOR_SUCCESS if success else COLOR_ERROR

        ts = entry.get("timestamp", datetime.now().strftime("%H:%M"))
        if isinstance(ts, str) and len(ts) > 16:
            ts = ts[11:16]  # Extract HH:MM from datetime string

        text = f"{icon}  {ts}  {entry.get('file_name', '?')}  \u2192  {entry.get('machine_name', '?')}"

        label = ctk.CTkLabel(
            self._list_frame, text=text, font=FONT_SMALL,
            text_color=color, anchor="w",
        )
        label.pack(fill="x", padx=4, pady=1)
        self._entries.append(label)

    def load_entries(self, entries: list[dict]):
        """Load a batch of log entries."""
        for e in entries:
            self.add_entry(e)
