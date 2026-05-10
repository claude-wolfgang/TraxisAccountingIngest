"""CNC Program Browser — displays programs loaded on the selected CNC."""

import customtkinter as ctk

from traxistransfer.drivers.base import ProgramInfo
from traxistransfer.ui.styles import *


class ProgramBrowser(ctk.CTkFrame):
    """Scrollable list of programs on the CNC, with loading/error states."""

    def __init__(self, parent, on_select=None, on_refresh=None, **kwargs):
        super().__init__(parent, fg_color=COLOR_BG_SECONDARY,
                         corner_radius=CORNER_RADIUS, **kwargs)

        self._on_select = on_select
        self._on_refresh = on_refresh
        self._programs: list[ProgramInfo] = []
        self._selected_index: int | None = None
        self._row_widgets: list[ctk.CTkFrame] = []

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING, pady=(PADDING, 4))

        ctk.CTkLabel(
            header, text="CNC PROGRAMS", font=FONT_HEADING,
            text_color=COLOR_TEXT,
        ).pack(side="left")

        self._refresh_btn = ctk.CTkButton(
            header, text="Refresh", font=FONT_SMALL,
            width=70, height=28,
            fg_color=COLOR_BG_TERTIARY, hover_color="#555555",
            command=self._handle_refresh, state="disabled",
        )
        self._refresh_btn.pack(side="right")

        self._machine_label = ctk.CTkLabel(
            header, text="", font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        )
        self._machine_label.pack(side="right", padx=(0, 8))

        # Content area (scrollable list or status message)
        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLOR_BG,
        )
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Status label (shown for loading/error/empty states)
        self._status_label = ctk.CTkLabel(
            self._list_frame, text="Select a machine to browse programs",
            font=FONT_BODY, text_color=COLOR_TEXT_DIM,
        )
        self._status_label.pack(pady=20)

        # Details at bottom
        self._details = ctk.CTkLabel(
            self, text="",
            font=FONT_SMALL, text_color=COLOR_TEXT_DIM,
            height=30,
        )
        self._details.pack(fill="x", padx=PADDING, pady=(0, PADDING))

    def set_loading(self, machine_name: str):
        """Show a loading message for the given machine."""
        self._clear_rows()
        self._machine_label.configure(text=machine_name)
        self._status_label.configure(
            text=f"Connecting to {machine_name}...",
            text_color=COLOR_TEXT_DIM,
        )
        self._status_label.pack(pady=20)
        self._refresh_btn.configure(state="disabled")
        self._details.configure(text="")

    def set_programs(self, programs: list[ProgramInfo]):
        """Populate the list with programs from the CNC."""
        self._clear_rows()
        self._programs = programs
        self._status_label.pack_forget()
        self._refresh_btn.configure(state="normal")

        if not programs:
            self._status_label.configure(
                text="No programs found on CNC",
                text_color=COLOR_TEXT_DIM,
            )
            self._status_label.pack(pady=20)
            self._details.configure(text=f"{len(programs)} programs")
            return

        for i, prog in enumerate(programs):
            row = ctk.CTkFrame(
                self._list_frame, fg_color=COLOR_BG_TERTIARY,
                corner_radius=4, height=40,
            )
            row.pack(fill="x", pady=1, padx=2)
            row.pack_propagate(False)

            # O-number
            num_label = ctk.CTkLabel(
                row, text=prog.number, font=FONT_BODY_BOLD,
                text_color=COLOR_TEXT, width=80, anchor="w",
            )
            num_label.pack(side="left", padx=(8, 4))

            # Comment
            comment_text = prog.comment if prog.comment else ""
            comment_label = ctk.CTkLabel(
                row, text=comment_text, font=FONT_BODY,
                text_color=COLOR_TEXT_DIM, anchor="w",
            )
            comment_label.pack(side="left", fill="x", expand=True, padx=4)

            # Size
            if prog.size > 0:
                size_kb = prog.size / 1024
                size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
            else:
                size_text = ""
            ctk.CTkLabel(
                row, text=size_text, font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM, width=70,
            ).pack(side="right", padx=8)

            # Click binding on all child widgets
            for widget in (row, num_label, comment_label):
                widget.bind("<Button-1>", lambda e, idx=i: self._select_program(idx))

            self._row_widgets.append(row)

        self._details.configure(text=f"{len(programs)} programs")

    def set_error(self, msg: str):
        """Show an error message (not a popup)."""
        self._clear_rows()
        self._status_label.configure(
            text=f"Could not connect: {msg}",
            text_color=COLOR_ERROR,
        )
        self._status_label.pack(pady=20)
        self._refresh_btn.configure(state="normal")
        self._details.configure(text="")

    def clear(self):
        """Reset to initial empty state."""
        self._clear_rows()
        self._programs = []
        self._machine_label.configure(text="")
        self._status_label.configure(
            text="Select a machine to browse programs",
            text_color=COLOR_TEXT_DIM,
        )
        self._status_label.pack(pady=20)
        self._refresh_btn.configure(state="disabled")
        self._details.configure(text="")

    def get_selected_program(self) -> ProgramInfo | None:
        """Return the currently selected program, or None."""
        if self._selected_index is not None and self._selected_index < len(self._programs):
            return self._programs[self._selected_index]
        return None

    def _clear_rows(self):
        """Remove all program row widgets."""
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets.clear()
        self._selected_index = None

    def _select_program(self, index: int):
        # Deselect previous
        if self._selected_index is not None and self._selected_index < len(self._row_widgets):
            self._row_widgets[self._selected_index].configure(fg_color=COLOR_BG_TERTIARY)

        self._selected_index = index
        self._row_widgets[index].configure(fg_color=COLOR_ACCENT)

        prog = self._programs[index]
        parts = [prog.number]
        if prog.comment:
            parts.append(prog.comment)
        if prog.size > 0:
            parts.append(f"{prog.size / 1024:.1f} KB")
        self._details.configure(text="  |  ".join(parts))

        if self._on_select:
            self._on_select(prog)

    def _handle_refresh(self):
        if self._on_refresh:
            self._on_refresh()
