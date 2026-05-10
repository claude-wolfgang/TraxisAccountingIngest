"""File browser with search, sort, and file details."""

import customtkinter as ctk
from pathlib import Path

from traxistransfer.ui.styles import *


class FileBrowser(ctk.CTkFrame):
    """NC file browser with search box and sortable list."""

    def __init__(self, parent, on_select=None, **kwargs):
        super().__init__(parent, fg_color=COLOR_BG_SECONDARY,
                        corner_radius=CORNER_RADIUS, **kwargs)

        self._on_select = on_select
        self._files = []
        self._filtered_files = []
        self._selected_index = None
        self._file_widgets = []

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PADDING, pady=(PADDING, 4))

        ctk.CTkLabel(
            header, text="NC PROGRAMS", font=FONT_HEADING,
            text_color=COLOR_TEXT,
        ).pack(side="left")

        self._folder_label = ctk.CTkLabel(
            header, text="", font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        )
        self._folder_label.pack(side="right")

        # Search box
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        search = ctk.CTkEntry(
            self, textvariable=self._search_var,
            placeholder_text="Search files...",
            font=FONT_BODY, height=36,
        )
        search.pack(fill="x", padx=PADDING, pady=(0, 4))

        # Sort buttons
        sort_frame = ctk.CTkFrame(self, fg_color="transparent")
        sort_frame.pack(fill="x", padx=PADDING, pady=(0, 4))

        self._sort_by = "modified"
        ctk.CTkButton(
            sort_frame, text="Name", font=FONT_SMALL, width=60, height=28,
            fg_color=COLOR_BG_TERTIARY, command=lambda: self._sort("name"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            sort_frame, text="Date", font=FONT_SMALL, width=60, height=28,
            fg_color=COLOR_BG_TERTIARY, command=lambda: self._sort("modified"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            sort_frame, text="Size", font=FONT_SMALL, width=60, height=28,
            fg_color=COLOR_BG_TERTIARY, command=lambda: self._sort("size"),
        ).pack(side="left")

        # File list
        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLOR_BG,
        )
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # File details panel at bottom
        self._details = ctk.CTkLabel(
            self, text="Select a file to see details",
            font=FONT_SMALL, text_color=COLOR_TEXT_DIM,
            height=30,
        )
        self._details.pack(fill="x", padx=PADDING, pady=(0, PADDING))

    def set_files(self, files: list[dict], folder_label: str = ""):
        """Update the file list."""
        self._files = files
        self._folder_label.configure(text=folder_label)
        self._apply_filter()

    def _on_search(self, *args):
        self._apply_filter()

    def _apply_filter(self):
        query = self._search_var.get().lower()
        if query:
            self._filtered_files = [f for f in self._files if query in f["name"].lower()]
        else:
            self._filtered_files = list(self._files)
        self._sort(self._sort_by)

    def _sort(self, key):
        self._sort_by = key
        reverse = key in ("modified", "size")  # newest/largest first
        self._filtered_files.sort(key=lambda f: f.get(key, ""), reverse=reverse)
        self._render()

    def _render(self):
        # Clear existing widgets
        for w in self._file_widgets:
            w.destroy()
        self._file_widgets.clear()
        self._selected_index = None

        for i, f in enumerate(self._filtered_files):
            row = ctk.CTkFrame(
                self._list_frame, fg_color=COLOR_BG_TERTIARY,
                corner_radius=4, height=40,
            )
            row.pack(fill="x", pady=1, padx=2)
            row.pack_propagate(False)

            name_label = ctk.CTkLabel(
                row, text=f["name"], font=FONT_BODY,
                text_color=COLOR_TEXT, anchor="w",
            )
            name_label.pack(side="left", fill="x", expand=True, padx=8)

            size_kb = f.get("size", 0) / 1024
            size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            ctk.CTkLabel(
                row, text=size_text, font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM, width=80,
            ).pack(side="right", padx=8)

            for widget in (row, name_label):
                widget.bind("<Button-1>", lambda e, idx=i: self._select_file(idx))

            self._file_widgets.append(row)

    def _select_file(self, index):
        # Deselect previous
        if self._selected_index is not None and self._selected_index < len(self._file_widgets):
            self._file_widgets[self._selected_index].configure(fg_color=COLOR_BG_TERTIARY)

        self._selected_index = index
        self._file_widgets[index].configure(fg_color=COLOR_ACCENT)

        f = self._filtered_files[index]
        # Update details
        size_kb = f.get("size", 0) / 1024
        details_parts = [f["name"]]
        if f.get("op_number"):
            details_parts.append(f"OP{f['op_number']}")
        if f.get("version"):
            details_parts.append(f"v{f['version']}")
        details_parts.append(f"{size_kb:.1f} KB")
        self._details.configure(text="  |  ".join(details_parts))

        if self._on_select:
            self._on_select(f)
