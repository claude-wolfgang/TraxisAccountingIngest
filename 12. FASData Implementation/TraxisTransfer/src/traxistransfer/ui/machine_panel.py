"""Machine selector panel with status indicators."""

import customtkinter as ctk

from traxistransfer.ui.styles import *


class MachinePanel(ctk.CTkFrame):
    """Left panel showing machines with green/gray status dots."""

    def __init__(self, parent, machines=None, on_select=None, **kwargs):
        super().__init__(parent, fg_color=COLOR_BG_SECONDARY,
                        corner_radius=CORNER_RADIUS, width=220, **kwargs)
        self.pack_propagate(False)

        self._on_select = on_select
        self._machine_widgets = {}
        self._selected_id = None

        ctk.CTkLabel(
            self, text="MACHINES", font=FONT_HEADING,
            text_color=COLOR_TEXT,
        ).pack(padx=PADDING, pady=(PADDING, 4))

        # Scrollable machine list
        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLOR_BG_SECONDARY,
        )
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        for machine in (machines or []):
            if machine.enabled:
                self._add_machine(machine)

    def _add_machine(self, machine):
        frame = ctk.CTkFrame(
            self._list_frame, fg_color=COLOR_BG_TERTIARY,
            corner_radius=6, height=50,
        )
        frame.pack(fill="x", pady=2, padx=2)
        frame.pack_propagate(False)

        # Status dot
        status_dot = ctk.CTkLabel(
            frame, text="\u25cf", font=(FONT_FAMILY, 18),
            text_color=COLOR_OFFLINE, width=24,
        )
        status_dot.pack(side="left", padx=(8, 4))

        # Machine name
        label = ctk.CTkLabel(
            frame, text=machine.display_name,
            font=FONT_BODY, text_color=COLOR_TEXT,
            anchor="w",
        )
        label.pack(side="left", fill="x", expand=True, padx=4)

        # Click binding
        for widget in (frame, label, status_dot):
            widget.bind("<Button-1>", lambda e, m=machine: self._select(m))

        self._machine_widgets[machine.id] = {
            "frame": frame,
            "dot": status_dot,
            "label": label,
            "machine": machine,
        }

    def _select(self, machine):
        # Deselect previous
        if self._selected_id and self._selected_id in self._machine_widgets:
            prev = self._machine_widgets[self._selected_id]["frame"]
            prev.configure(fg_color=COLOR_BG_TERTIARY)

        # Select new
        self._selected_id = machine.id
        self._machine_widgets[machine.id]["frame"].configure(fg_color=COLOR_ACCENT)

        if self._on_select:
            self._on_select(machine)

    def update_status(self, machine_id: str, reachable: bool):
        if machine_id in self._machine_widgets:
            color = COLOR_REACHABLE if reachable else COLOR_UNREACHABLE
            self._machine_widgets[machine_id]["dot"].configure(text_color=color)
