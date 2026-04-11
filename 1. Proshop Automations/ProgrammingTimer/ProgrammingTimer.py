"""
Programming Timer — Fusion 360 Add-In
Version: 1.2.0

Automatically tracks programming time per document.
Runs silently in background, detecting active/idle/switched states.
Logs session data locally for time analysis.

v1.2.0 — Eliminated cloud folder traversal in get_document_path() that
          blocked Fusion's UI thread. Path resolution now uses project name
          only (single cached API call). State saves throttled to dirty-only.
v1.1.0 — All file I/O moved to background thread (io_worker) to prevent
          Fusion freezes. Document mappings cached in memory.
"""

import adsk.core
import adsk.fusion
import traceback
import os
import sys

# Add the add-in folder to the path for imports
ADDIN_FOLDER = os.path.dirname(os.path.abspath(__file__))
if ADDIN_FOLDER not in sys.path:
    sys.path.insert(0, ADDIN_FOLDER)

from timer_core import TimerManager
from data_logger import recover_orphaned_sessions, init_cache
from config import is_company_file, get_poll_interval, load_config
import io_worker

# Global references
app = None
ui = None
timer_manager = None
handlers = []
poll_event = None
poll_handler = None
POLL_EVENT_ID = "ProgrammingTimerPollEvent"

# UI elements
toolbar_panel = None
toolbar_button = None
status_palette = None

# Document path cache — avoids repeated Fusion cloud API calls
_doc_path_cache = {}


def log(msg):
    """Log to Fusion's text commands panel."""
    try:
        if app:
            app.log(f"[Timer] {msg}")
        else:
            print(f"[Timer] {msg}")
    except Exception:
        print(f"[Timer] {msg}")


class DocumentOpenedHandler(adsk.core.DocumentEventHandler):
    """Handle document opened events."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.DocumentEventArgs.cast(args)
            doc = event_args.document

            if doc is None:
                return

            doc_name = doc.name
            doc_path = get_document_path(doc)

            log(f"Document opened: {doc_name}")

            # Check if this is a company file
            if not is_company_file(doc_path):
                log(f"Not a company file, ignoring: {doc_path}")
                return

            # Check if we need to ask for part identifier
            needs_input = timer_manager.on_document_opened(doc_name, doc_path, None)

            if needs_input:
                # Show dialog to get part identifier
                part_id = show_part_identifier_dialog(doc_name)
                timer_manager.on_document_opened(doc_name, doc_path, part_id)
                log(f"Tracking started: {doc_name} as {part_id}")
            else:
                # Already mapped - show toast
                show_tracking_toast(doc_name)

        except Exception:
            log(f"Error in document opened handler: {traceback.format_exc()}")


class DocumentActivatedHandler(adsk.core.DocumentEventHandler):
    """Handle document activation (switching between documents)."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.DocumentEventArgs.cast(args)
            doc = event_args.document

            if doc is None:
                return

            doc_name = doc.name
            doc_path = get_document_path(doc)

            log(f"Document activated: {doc_name}")

            # Check if this is a company file that should be tracked
            if is_company_file(doc_path):
                # Check if already tracked
                if doc_name in timer_manager.timers:
                    timer_manager.on_document_activated(doc_name, doc_path)
                else:
                    # New company file - need to start tracking
                    needs_input = timer_manager.on_document_opened(doc_name, doc_path, None)
                    if needs_input:
                        part_id = show_part_identifier_dialog(doc_name)
                        timer_manager.on_document_opened(doc_name, doc_path, part_id)
            else:
                # Non-company file activated - just update active document reference
                timer_manager.on_document_activated(doc_name, doc_path)

        except Exception:
            log(f"Error in document activated handler: {traceback.format_exc()}")


class DocumentClosingHandler(adsk.core.DocumentEventHandler):
    """Handle document closing events."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.DocumentEventArgs.cast(args)
            doc = event_args.document

            if doc is None:
                return

            doc_name = doc.name
            log(f"Document closing: {doc_name}")

            timer_manager.on_document_closed(doc_name)

        except Exception:
            log(f"Error in document closing handler: {traceback.format_exc()}")


class ApplicationActivatedHandler(adsk.core.ApplicationEventHandler):
    """Handle Fusion 360 gaining focus."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            log("Fusion 360 activated (focused)")
            timer_manager.on_fusion_focus_changed(True)
        except Exception:
            log(f"Error in app activated handler: {traceback.format_exc()}")


class ApplicationDeactivatedHandler(adsk.core.ApplicationEventHandler):
    """Handle Fusion 360 losing focus."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            log("Fusion 360 deactivated (unfocused)")
            timer_manager.on_fusion_focus_changed(False)
        except Exception:
            log(f"Error in app deactivated handler: {traceback.format_exc()}")


class PollEventHandler(adsk.core.CustomEventHandler):
    """Handle periodic polling for idle detection and focus tracking."""

    def __init__(self):
        super().__init__()
        self._was_focused = True

    def notify(self, args):
        try:
            # Check focus state since Fusion doesn't have focus events
            from idle_detector import is_fusion_foreground
            is_focused = is_fusion_foreground()
            if is_focused != self._was_focused:
                self._was_focused = is_focused
                timer_manager.on_fusion_focus_changed(is_focused)
                if is_focused:
                    log("Fusion 360 activated (focused)")
                else:
                    log("Fusion 360 deactivated (unfocused)")

            timer_manager.poll_activity(fusion_foreground=is_focused)
            # Schedule next poll
            schedule_poll()
        except Exception:
            log("Error in poll handler: {}".format(traceback.format_exc()))


class ButtonClickHandler(adsk.core.CommandCreatedEventHandler):
    """Handle toolbar button click."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            show_status_dialog()
        except Exception:
            log(f"Error in button click handler: {traceback.format_exc()}")


def get_document_path(doc):
    """Get document path for company-file detection.

    Uses cache to avoid repeated Fusion cloud API calls. Only fetches
    the project name (one API call), never traverses the folder hierarchy.
    """
    doc_name = doc.name if doc else ""
    if not doc_name:
        return ""

    # Return cached path instantly
    if doc_name in _doc_path_cache:
        return _doc_path_cache[doc_name]

    path = doc_name  # fallback
    try:
        if doc.dataFile:
            # Single API call — get project name only (no folder traversal)
            try:
                project_name = doc.dataFile.parentProject.name
                path = f"{project_name}/{doc_name}"
            except Exception:
                pass
        elif hasattr(doc, 'pathName') and doc.pathName:
            path = doc.pathName
    except Exception:
        pass

    _doc_path_cache[doc_name] = path
    return path


def show_part_identifier_dialog(doc_name):
    """
    Show dialog to get part identifier for a new document.
    Returns the entered part identifier.
    """
    try:
        # Extract default part number from document name (first token)
        default_part = doc_name.split()[0] if doc_name else doc_name

        result = ui.inputBox(
            f'New file detected: "{doc_name}"\n\nEnter part identifier:',
            "Programming Timer",
            default_part
        )

        if result[0]:  # result is (value, cancelled)
            return result[0].strip() or doc_name
        else:
            return doc_name

    except Exception:
        log(f"Error showing dialog: {traceback.format_exc()}")
        return doc_name


def show_tracking_toast(doc_name):
    """Show a brief notification that tracking has resumed."""
    try:
        timer = timer_manager.timers.get(doc_name)
        part_id = timer.part_identifier if timer else doc_name
        log(f"Tracking resumed: {part_id}")
    except Exception:
        pass


def show_status_dialog():
    """Show the status panel with current tracking info."""
    try:
        status = timer_manager.get_status()
        today_total = timer_manager.get_today_total()

        # Build status message
        lines = ["Programming Timer", "-" * 30]

        if status:
            for item in status:
                indicator = "●" if item["is_active"] else "○"
                duration = format_duration(item["duration_seconds"])
                state = "(active)" if item["is_active"] else "(paused)"
                lines.append(f"{indicator} {item['part_identifier']:<20} {duration} {state}")
        else:
            lines.append("No documents being tracked")

        lines.append("")
        lines.append(f"Today total: {format_duration(today_total)}")

        message = "\n".join(lines)
        ui.messageBox(message, "Programming Timer")

    except Exception:
        log(f"Error showing status: {traceback.format_exc()}")


def format_duration(seconds):
    """Format seconds as Xh Ym."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes:02d}m"


def schedule_poll():
    """Schedule the next poll event."""
    global poll_event
    try:
        if poll_event:
            # Fire after poll interval (converted to seconds)
            import threading
            interval = get_poll_interval()
            timer = threading.Timer(interval, fire_poll_event)
            timer.daemon = True
            timer.start()
    except Exception:
        log(f"Error scheduling poll: {traceback.format_exc()}")


def fire_poll_event():
    """Fire the poll custom event (thread-safe way to trigger poll)."""
    try:
        if app and poll_event:
            app.fireCustomEvent(POLL_EVENT_ID, "")
    except Exception:
        pass


def create_ui():
    """Create the toolbar button."""
    global toolbar_panel, toolbar_button

    try:
        # Get the Utilities tab
        toolbar_tabs = ui.allToolbarTabs
        utilities_tab = toolbar_tabs.itemById("UtilitiesTab")

        if utilities_tab:
            # Create a panel for our button
            toolbar_panels = utilities_tab.toolbarPanels
            toolbar_panel = toolbar_panels.itemById("TimerPanel")

            if not toolbar_panel:
                toolbar_panel = toolbar_panels.add("TimerPanel", "Timer")

            # Create the command definition
            cmd_defs = ui.commandDefinitions
            cmd_def = cmd_defs.itemById("TimerStatusCmd")

            if not cmd_def:
                cmd_def = cmd_defs.addButtonDefinition(
                    "TimerStatusCmd",
                    "Timer Status",
                    "Show programming timer status",
                    ""  # No icon for now
                )

            # Add handler
            on_click = ButtonClickHandler()
            cmd_def.commandCreated.add(on_click)
            handlers.append(on_click)

            # Add to panel
            control = toolbar_panel.controls.itemById("TimerStatusCmd")
            if not control:
                toolbar_panel.controls.addCommand(cmd_def)

            log("UI created")

    except Exception:
        log(f"Error creating UI: {traceback.format_exc()}")


def destroy_ui():
    """Remove the toolbar button."""
    global toolbar_panel, toolbar_button

    try:
        cmd_def = ui.commandDefinitions.itemById("TimerStatusCmd")
        if cmd_def:
            cmd_def.deleteMe()

        if toolbar_panel:
            toolbar_panel.deleteMe()
            toolbar_panel = None

        log("UI destroyed")

    except Exception:
        log(f"Error destroying UI: {traceback.format_exc()}")


def run(context):
    """Add-in entry point - called when add-in starts."""
    global app, ui, timer_manager, poll_event, poll_handler

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        log("Starting Programming Timer v1.1.0")

        # Load configuration
        load_config()

        # Start background I/O worker (must be before any file operations)
        io_worker.start()

        # Load mappings cache into memory (one-time synchronous read)
        init_cache()

        # Initialize timer manager
        timer_manager = TimerManager()

        # Recover any orphaned sessions from previous crash
        recovered = recover_orphaned_sessions()
        if recovered:
            log(f"Recovered {len(recovered)} orphaned session(s)")

        # Register document event handlers
        doc_events = app.documentOpened
        opened_handler = DocumentOpenedHandler()
        doc_events.add(opened_handler)
        handlers.append(opened_handler)

        activated_handler = DocumentActivatedHandler()
        app.documentActivated.add(activated_handler)
        handlers.append(activated_handler)

        closing_handler = DocumentClosingHandler()
        app.documentClosing.add(closing_handler)
        handlers.append(closing_handler)

        # NOTE: Fusion 360 does not expose applicationActivated/Deactivated events.
        # Focus detection is handled via polling in idle_detector.is_fusion_foreground().

        # Set up polling for idle detection
        poll_event = app.registerCustomEvent(POLL_EVENT_ID)
        poll_handler = PollEventHandler()
        poll_event.add(poll_handler)
        handlers.append(poll_handler)

        # Start polling
        schedule_poll()

        # Create UI
        create_ui()

        # Check if there's already an active document
        try:
            if app.activeDocument:
                doc = app.activeDocument
                doc_name = doc.name
                doc_path = get_document_path(doc)

                if is_company_file(doc_path):
                    needs_input = timer_manager.on_document_opened(doc_name, doc_path, None)
                    if needs_input:
                        part_id = show_part_identifier_dialog(doc_name)
                        timer_manager.on_document_opened(doc_name, doc_path, part_id)
        except RuntimeError:
            # No valid document open (InternalValidationError), skip gracefully
            log("No active document at startup (normal)")
        except Exception:
            log(f"Error checking active document: {traceback.format_exc()}")

        log("Add-in started successfully")

    except Exception:
        if ui:
            ui.messageBox(f"Failed to start Programming Timer:\n{traceback.format_exc()}")


def stop(context):
    """Add-in exit point - called when add-in stops."""
    global app, ui, timer_manager, poll_event, poll_handler, handlers

    try:
        log("Stopping Programming Timer")

        # Shutdown timer manager (finalizes all sessions, queues final writes)
        if timer_manager:
            timer_manager.shutdown()

        # Stop IO worker (flushes all queued writes before returning)
        io_worker.stop()

        # Unregister poll event
        if poll_event:
            app.unregisterCustomEvent(POLL_EVENT_ID)
            poll_event = None

        # Remove UI
        destroy_ui()

        # Clear handlers
        handlers.clear()

        log("Add-in stopped")

    except Exception:
        if ui:
            ui.messageBox(f"Error stopping Programming Timer:\n{traceback.format_exc()}")
