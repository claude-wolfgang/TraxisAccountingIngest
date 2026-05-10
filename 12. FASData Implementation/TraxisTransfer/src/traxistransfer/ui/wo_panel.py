"""Active Work Order panel — shows the WO running on the selected machine."""

import customtkinter as ctk

from traxistransfer.ui.styles import *


class WorkOrderPanel(ctk.CTkFrame):
    """Compact panel displaying the active work order for a machine."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLOR_BG_SECONDARY,
                         corner_radius=CORNER_RADIUS, **kwargs)

        # Header
        ctk.CTkLabel(
            self, text="ACTIVE WORK ORDER", font=FONT_HEADING,
            text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=PADDING, pady=(PADDING, 2))

        # Info line (WO · Part · Customer PN)
        self._info_label = ctk.CTkLabel(
            self, text="Select a machine", font=FONT_BODY,
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self._info_label.pack(fill="x", padx=PADDING, pady=(0, PADDING))

    def set_loading(self):
        """Show loading state."""
        self._info_label.configure(
            text="Loading work order...",
            text_color=COLOR_TEXT_DIM,
        )

    def set_wo(self, wo_number: str, part_number: str, customer_pn: str = ""):
        """Display active work order info."""
        parts = [wo_number]
        if part_number:
            parts.append(f"Part: {part_number}")
        if customer_pn:
            parts.append(f"Cust: {customer_pn}")
        self._info_label.configure(
            text="  \u00b7  ".join(parts),
            text_color=COLOR_TEXT,
        )

    def set_no_wo(self):
        """Show 'no active WO' state."""
        self._info_label.configure(
            text="No active work order",
            text_color=COLOR_TEXT_DIM,
        )

    def set_error(self, msg: str = ""):
        """Show error state."""
        text = "ProShop unavailable"
        if msg:
            text += f" — {msg}"
        self._info_label.configure(
            text=text,
            text_color=COLOR_WARNING,
        )

    def clear(self):
        """Reset to initial state."""
        self._info_label.configure(
            text="Select a machine",
            text_color=COLOR_TEXT_DIM,
        )
