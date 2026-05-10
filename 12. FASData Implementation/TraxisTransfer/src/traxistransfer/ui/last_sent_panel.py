"""Last Sent Program panel — shows the file ready to send to a machine."""

import customtkinter as ctk

from traxistransfer.ui.styles import *


class LastSentPanel(ctk.CTkFrame):
    """Compact panel showing the last-sent / latest-version program with Send button."""

    def __init__(self, parent, on_send=None, **kwargs):
        super().__init__(parent, fg_color=COLOR_BG_SECONDARY,
                         corner_radius=CORNER_RADIUS, **kwargs)

        self._on_send = on_send
        self._file_info: dict | None = None

        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING, pady=(PADDING, 2))

        ctk.CTkLabel(
            header, text="LAST SENT", font=FONT_HEADING,
            text_color=COLOR_TEXT,
        ).pack(side="left")

        self._hint_label = ctk.CTkLabel(
            header, text="", font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        )
        self._hint_label.pack(side="right")

        # File info row
        info_row = ctk.CTkFrame(self, fg_color="transparent")
        info_row.pack(fill="x", padx=PADDING, pady=(0, 2))

        self._file_label = ctk.CTkLabel(
            info_row, text="No programs sent to this machine yet",
            font=FONT_BODY, text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self._file_label.pack(side="left", fill="x", expand=True)

        self._size_label = ctk.CTkLabel(
            info_row, text="", font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM, width=80,
        )
        self._size_label.pack(side="right")

        # Send button
        self.send_btn = ctk.CTkButton(
            self, text="SEND TO MACHINE",
            font=FONT_HEADING, height=BUTTON_HEIGHT,
            fg_color=COLOR_ACCENT, hover_color="#1976D2",
            command=self._handle_send, state="disabled",
        )
        self.send_btn.pack(fill="x", padx=PADDING, pady=(4, PADDING))

    def set_file(self, file_info: dict, sent_version: int | None = None):
        """Display a file ready to send.

        Args:
            file_info: File dict from FolderResolver (path, name, size, version, etc.)
            sent_version: The version that was last sent (for hint text).
                          None if the displayed file IS the last sent file.
        """
        self._file_info = file_info
        self._file_label.configure(
            text=file_info["name"],
            text_color=COLOR_TEXT,
        )

        # Size
        size_kb = file_info.get("size", 0) / 1024
        size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
        self._size_label.configure(text=size_text)

        # Hint — show if this is a newer version than what was sent
        if sent_version is not None and file_info.get("version") and file_info["version"] != sent_version:
            self._hint_label.configure(
                text=f"latest \u2014 v{sent_version} was last sent",
                text_color=COLOR_WARNING,
            )
        else:
            self._hint_label.configure(text="")

        self.send_btn.configure(state="normal")

    def set_no_history(self):
        """Show 'no programs sent' state."""
        self._file_info = None
        self._file_label.configure(
            text="No programs sent to this machine yet",
            text_color=COLOR_TEXT_DIM,
        )
        self._size_label.configure(text="")
        self._hint_label.configure(text="")
        self.send_btn.configure(state="disabled")

    def set_file_missing(self, file_name: str):
        """Show 'file no longer on disk' state."""
        self._file_info = None
        self._file_label.configure(
            text=f"{file_name} (no longer on disk)",
            text_color=COLOR_WARNING,
        )
        self._size_label.configure(text="")
        self._hint_label.configure(text="")
        self.send_btn.configure(state="disabled")

    def clear(self):
        """Reset to initial empty state."""
        self._file_info = None
        self._file_label.configure(
            text="Select a machine",
            text_color=COLOR_TEXT_DIM,
        )
        self._size_label.configure(text="")
        self._hint_label.configure(text="")
        self.send_btn.configure(state="disabled")

    def get_file_info(self) -> dict | None:
        """Return the currently displayed file info, or None."""
        return self._file_info

    def _handle_send(self):
        if self._on_send and self._file_info:
            self._on_send(self._file_info)
