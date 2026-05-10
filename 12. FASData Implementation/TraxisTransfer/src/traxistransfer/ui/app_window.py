"""Main application window."""

import customtkinter as ctk

from traxistransfer import __version__
from traxistransfer.ui.styles import *
from traxistransfer.ui.machine_panel import MachinePanel
from traxistransfer.ui.wo_panel import WorkOrderPanel
from traxistransfer.ui.last_sent_panel import LastSentPanel
from traxistransfer.ui.program_browser import ProgramBrowser
from traxistransfer.ui.progress_bar import TransferProgress
from traxistransfer.ui.log_viewer import LogViewer


class AppWindow(ctk.CTk):
    """Main TraxisTransfer window."""

    def __init__(self, machines=None, on_send=None, on_receive=None,
                 on_program_selected=None, on_refresh_programs=None):
        super().__init__()

        self.title(f"TraxisTransfer v{__version__}")
        self.geometry("1000x750")
        self.minsize(900, 650)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLOR_BG)

        self._on_send = on_send
        self._on_receive = on_receive
        self._selected_machine = None
        self._selected_program = None

        self._build_layout(machines or [], on_program_selected, on_refresh_programs)

    def _build_layout(self, machines, on_program_selected, on_refresh_programs):
        # Top bar with title
        top_frame = ctk.CTkFrame(self, fg_color=COLOR_BG_SECONDARY, height=50)
        top_frame.pack(fill="x", padx=0, pady=0)
        top_frame.pack_propagate(False)
        ctk.CTkLabel(
            top_frame, text="TraxisTransfer",
            font=FONT_TITLE, text_color=COLOR_TEXT,
        ).pack(side="left", padx=PADDING)

        # Main content area
        content = ctk.CTkFrame(self, fg_color=COLOR_BG)
        content.pack(fill="both", expand=True, padx=PADDING, pady=PADDING)

        # Left panel — Machine selector
        self.machine_panel = MachinePanel(
            content, machines=machines,
            on_select=self._on_machine_selected,
        )
        self.machine_panel.pack(side="left", fill="y", padx=(0, PADDING))

        # Right area — WO info + Last Sent + CNC Programs
        right = ctk.CTkFrame(content, fg_color=COLOR_BG)
        right.pack(side="left", fill="both", expand=True)

        # 1. Active Work Order (compact, fixed height)
        self.wo_panel = WorkOrderPanel(right)
        self.wo_panel.pack(fill="x", pady=(0, PADDING))

        # 2. Last Sent Program (compact, with Send button)
        self.last_sent_panel = LastSentPanel(
            right,
            on_send=self._handle_send_from_panel,
        )
        self.last_sent_panel.pack(fill="x", pady=(0, PADDING))

        # 3. CNC Program browser (expandable, fills remaining space)
        self.program_browser = ProgramBrowser(
            right,
            on_select=self._on_cnc_program_selected,
            on_refresh=on_refresh_programs,
        )
        self.program_browser.pack(fill="both", expand=True, pady=(0, PADDING))

        # Wire external callback
        self._on_program_selected_cb = on_program_selected

        # Receive button — inside program browser area
        self.receive_btn = ctk.CTkButton(
            right, text="RECEIVE FROM MACHINE",
            font=FONT_BODY, height=BUTTON_HEIGHT,
            fg_color=COLOR_BG_TERTIARY, hover_color="#555555",
            command=self._handle_receive, state="disabled",
        )
        self.receive_btn.pack(fill="x", pady=(0, PADDING))

        # Progress bar
        self.progress = TransferProgress(right)
        self.progress.pack(fill="x", pady=(0, PADDING))

        # Bottom — Log viewer
        self.log_viewer = LogViewer(self)
        self.log_viewer.pack(fill="x", padx=PADDING, pady=(0, PADDING))

    def _on_machine_selected(self, machine):
        self._selected_machine = machine
        self._selected_program = None
        if machine:
            self.receive_btn.configure(state="normal")
        else:
            self.receive_btn.configure(state="disabled")

    def _on_cnc_program_selected(self, program):
        self._selected_program = program
        if self._on_program_selected_cb:
            self._on_program_selected_cb(program)

    def _handle_send_from_panel(self, file_info):
        """Called by LastSentPanel's Send button."""
        if self._on_send and self._selected_machine:
            self._on_send(self._selected_machine, file_info)

    def _handle_receive(self):
        if self._on_receive and self._selected_machine:
            self._on_receive(self._selected_machine, self._selected_program)

    def update_machine_status(self, machine_id: str, reachable: bool):
        """Update a machine's status indicator (call from main thread)."""
        self.machine_panel.update_status(machine_id, reachable)

    def show_progress(self, message: str, value: float = 0):
        self.progress.update_progress(message, value)

    def hide_progress(self):
        self.progress.reset()

    def add_log_entry(self, entry: dict):
        self.log_viewer.add_entry(entry)
