"""App bootstrap — load config, create services, launch GUI."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from traxistransfer import __version__
from traxistransfer.config import load_env_file, load_machines
from traxistransfer.services import audit_log
from traxistransfer.services.folder_resolver import FolderResolver
from traxistransfer.services.proshop_client import ProShopClient
from traxistransfer.services.status_checker import StatusChecker
from traxistransfer.services import transfer_service
from traxistransfer.ui.transfer_dialog import TransferDialog

log = logging.getLogger(__name__)


def run():
    """Launch the TraxisTransfer application."""
    # ---- Logging ----
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("TraxisTransfer v%s starting", __version__)

    # ---- Environment + config ----
    load_env_file()
    machines = load_machines()
    log.info("Loaded %d machines", len(machines))

    # ---- Database ----
    db_path = audit_log.get_db_path()
    db_conn = audit_log.get_connection(db_path)
    audit_log.init_db(db_conn)
    log.info("Database ready at %s", db_path)

    # ---- ProShop client (may fail silently) ----
    try:
        proshop = ProShopClient()
    except Exception:
        proshop = None
        log.warning("ProShop client not available — folder resolver will use defaults")

    # ---- Folder resolver ----
    folder_resolver = FolderResolver(proshop=proshop, db_conn=db_conn)

    # ---- UI ----
    import customtkinter as ctk
    from traxistransfer.ui.app_window import AppWindow

    app = AppWindow(
        machines=machines,
        on_send=lambda machine, file_info: _handle_send(
            app, machine, file_info, folder_resolver, db_conn
        ),
        on_receive=lambda machine, program=None: _handle_receive(
            app, machine, db_conn, selected_program=program
        ),
        on_refresh_programs=lambda: _refresh_programs(app),
    )

    # Hook machine selection → update all right-side panels
    original_on_machine_selected = app._on_machine_selected

    def _on_machine_selected_with_resolver(machine):
        original_on_machine_selected(machine)
        if machine:
            # 1. Update WO panel (background thread)
            _update_wo_panel_async(app, machine, proshop)

            # 2. Update Last Sent panel (audit log + folder scan)
            _update_last_sent_panel(app, machine, db_conn, folder_resolver)

            # 3. Update CNC program browser (background thread)
            _list_programs_async(app, machine)
        else:
            app.wo_panel.clear()
            app.last_sent_panel.clear()
            app.program_browser.clear()

    app.machine_panel._on_select = _on_machine_selected_with_resolver

    # Load recent transfers into log viewer
    try:
        recent = audit_log.get_recent_transfers(db_conn, limit=10)
        app.log_viewer.load_entries(recent)
    except Exception:
        log.warning("Could not load recent transfers", exc_info=True)

    # ---- Status checker ----
    def _on_status_update(machine_id: str, reachable: bool):
        # Schedule UI update on main thread via Tk's after()
        app.after(0, app.update_machine_status, machine_id, reachable)

    status_checker = StatusChecker(
        machines=machines,
        callback=_on_status_update,
    )
    status_checker.start()
    log.info("Status checker started (30s interval)")

    # ---- Window close cleanup ----
    def _on_close():
        log.info("Shutting down...")
        status_checker.stop()
        try:
            db_conn.close()
        except Exception:
            pass
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", _on_close)

    # ---- Run ----
    log.info("TraxisTransfer ready")
    app.mainloop()


def _update_wo_panel_async(app, machine, proshop):
    """Query ProShop for the active WO and update the WO panel."""
    if not proshop or not machine.proshop_pot_id:
        app.wo_panel.set_no_wo()
        return

    app.wo_panel.set_loading()

    def _run():
        try:
            wo = proshop.get_active_wo_for_workcell(machine.proshop_pot_id)
            if wo:
                wo_number = wo.get("woNumber", "")
                part_number = wo.get("partNumber", "")
                # Try to get customer PN
                customer_pn = ""
                if part_number:
                    customer_pn = proshop.get_customer_part_number(part_number) or ""
                app.after(0, app.wo_panel.set_wo, wo_number, part_number, customer_pn)
            else:
                app.after(0, app.wo_panel.set_no_wo)
        except Exception as exc:
            log.warning("Failed to fetch WO for %s: %s", machine.display_name, exc)
            app.after(0, app.wo_panel.set_error)

    thread = threading.Thread(target=_run, daemon=True, name="FetchWO")
    thread.start()


def _update_last_sent_panel(app, machine, db_conn, folder_resolver):
    """Look up the last sent program and resolve the latest version on disk."""
    last_sent = audit_log.get_last_sent_to_machine(db_conn, machine.id)

    if not last_sent:
        app.last_sent_panel.set_no_history()
        return

    sent_file_name = last_sent.get("file_name", "")
    if not sent_file_name:
        app.last_sent_panel.set_no_history()
        return

    # Resolve folders for this machine to search for latest version
    folders = folder_resolver.resolve(machine)

    # Find the latest version of the same PN+OP on disk
    latest = FolderResolver.find_latest_version(sent_file_name, folders)

    if latest:
        # Determine the version that was originally sent (for hint text)
        import re
        tpm_pattern = re.compile(r"^(.+)_OP(\d+)_v(\d+)\.nc$", re.IGNORECASE)
        m = tpm_pattern.match(sent_file_name)
        sent_version = int(m.group(3)) if m else None
        app.last_sent_panel.set_file(latest, sent_version=sent_version)
    else:
        # File no longer exists on disk
        app.last_sent_panel.set_file_missing(sent_file_name)


def _list_programs_async(app, machine):
    """Fetch the program list from a CNC in a background thread."""
    app.program_browser.set_loading(machine.display_name)

    def _run():
        try:
            driver = transfer_service.get_driver(machine)
            programs = driver.list_programs()
            app.after(0, app.program_browser.set_programs, programs)
        except Exception as exc:
            log.warning("Failed to list programs on %s: %s", machine.display_name, exc)
            app.after(0, app.program_browser.set_error, str(exc))

    thread = threading.Thread(target=_run, daemon=True, name="ListPrograms")
    thread.start()


def _refresh_programs(app):
    """Re-query the currently selected machine's program list."""
    machine = app._selected_machine
    if machine:
        _list_programs_async(app, machine)


def _handle_send(app, machine, file_info, folder_resolver, db_conn):
    """Show confirmation dialog, then send in background thread."""
    file_path = file_info["path"]
    file_name = file_info["name"]
    file_size = file_info.get("size", 0)
    program_number = file_info.get("part_number", "")

    def _do_send():
        # Show dialog first
        dialog = TransferDialog(
            app,
            machine_name=machine.display_name,
            file_name=file_name,
            file_size=file_size,
            program_number=program_number,
            on_confirm=lambda: _execute_send(
                app, machine, Path(file_path), program_number,
                folder_resolver, db_conn
            ),
        )
        dialog.focus()

    _do_send()


def _execute_send(app, machine, file_path, program_number, folder_resolver, db_conn):
    """Execute the send in a background thread with progress updates."""

    def _progress_cb(sent: int, total: int):
        if total > 0:
            pct = sent / total
            app.after(0, app.show_progress, f"Sending... {int(pct * 100)}%", pct)

    def _run():
        app.after(0, app.show_progress, "Connecting...", 0.0)
        result = transfer_service.send_program(
            machine=machine,
            file_path=file_path,
            program_number=program_number,
            progress_cb=_progress_cb,
            db_conn=db_conn,
        )

        def _finish():
            if result.success:
                app.show_progress("Transfer complete!", 1.0)
            else:
                app.show_progress(f"FAILED: {result.error_message}", 0.0)

            # Log the result in the viewer
            app.add_log_entry({
                "success": result.success,
                "file_name": result.file_name,
                "machine_name": result.machine_name,
                "timestamp": result.timestamp.strftime("%H:%M") if result.timestamp else "",
            })

            # Save folder choice for this machine
            folder_resolver.save_choice(machine, file_path.parent)

            # Refresh the Last Sent panel after a successful send
            if result.success:
                _update_last_sent_panel(app, machine, db_conn, folder_resolver)

            # Auto-hide progress after 3 seconds on success
            if result.success:
                app.after(3000, app.hide_progress)

        app.after(0, _finish)

    thread = threading.Thread(target=_run, daemon=True, name="SendTransfer")
    thread.start()


def _handle_receive(app, machine, db_conn, selected_program=None):
    """Receive a program. If a CNC program is selected, use it directly."""
    import customtkinter as ctk

    # If a program is selected in the CNC browser, use its number directly
    if selected_program is not None:
        program_number = selected_program.number
    else:
        # Prompt for program number
        dialog = ctk.CTkInputDialog(
            text=f"Enter program name/number to receive from {machine.display_name}:",
            title="Receive Program",
        )
        program_number = dialog.get_input()
        if not program_number:
            return

    # Ask where to save
    from tkinter import filedialog
    dest_path = filedialog.asksaveasfilename(
        defaultextension=".nc",
        filetypes=[("NC Programs", "*.nc"), ("All Files", "*.*")],
        initialfile=program_number,
        title="Save received program as...",
    )
    if not dest_path:
        return

    def _progress_cb(sent: int, total: int):
        if total > 0:
            pct = sent / total
            app.after(0, app.show_progress, f"Receiving... {int(pct * 100)}%", pct)

    def _run():
        app.after(0, app.show_progress, "Connecting...", 0.0)
        result = transfer_service.receive_program(
            machine=machine,
            program_number=program_number,
            dest_path=Path(dest_path),
            progress_cb=_progress_cb,
            db_conn=db_conn,
        )

        def _finish():
            if result.success:
                app.show_progress("Receive complete!", 1.0)
            else:
                app.show_progress(f"FAILED: {result.error_message}", 0.0)

            app.add_log_entry({
                "success": result.success,
                "file_name": result.file_name,
                "machine_name": result.machine_name,
                "timestamp": result.timestamp.strftime("%H:%M") if result.timestamp else "",
            })

            if result.success:
                app.after(3000, app.hide_progress)

        app.after(0, _finish)

    thread = threading.Thread(target=_run, daemon=True, name="ReceiveTransfer")
    thread.start()
