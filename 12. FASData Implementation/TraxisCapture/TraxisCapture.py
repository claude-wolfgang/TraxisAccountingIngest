"""
TraxisCapture — Fusion 360 Add-In
Version: 1.0.0

Logs programmer changes between CAM-generated toolpaths and final
posted programs. Runs in the background with no UI.

Event flow:
  1. DocumentOpened  -> detect origin, tag document, take Snapshot A
  2. CommandTerminated (post) -> take Snapshot B, inject CAPTURE tags into NC
  3. DocumentClosing -> compute diff, write JSONL

Follows the same patterns as ProgrammingTimer:
  - Event handler classes prevent garbage collection
  - io_worker for background file I/O
  - sys.path manipulation for local imports
"""

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import os
import sys

# Add the add-in folder to the path for local imports
ADDIN_FOLDER = os.path.dirname(os.path.abspath(__file__))
if ADDIN_FOLDER not in sys.path:
    sys.path.insert(0, ADDIN_FOLDER)

import tc_io_worker as io_worker
from tc_config import load_config
import capture_core

# Global references (prevent garbage collection)
app = None
ui = None
handlers = []


def log(msg):
    """Log to Fusion's text commands panel."""
    try:
        if app:
            app.log(f"[TraxisCapture] {msg}")
        else:
            print(f"[TraxisCapture] {msg}")
    except Exception:
        print(f"[TraxisCapture] {msg}")


# ===========================================================================
# Event Handlers
# ===========================================================================

class DocumentOpenedHandler(adsk.core.DocumentEventHandler):
    """Handle document opened — detect origin, take Snapshot A."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.DocumentEventArgs.cast(args)
            doc = event_args.document
            if doc is None:
                return

            log(f"Document opened: {doc.name}")
            capture_core.on_document_opened(doc)

        except Exception:
            log(f"DocumentOpened error: {traceback.format_exc()}")


class DocumentActivatedHandler(adsk.core.DocumentEventHandler):
    """Handle document activation (switching between docs)."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.DocumentEventArgs.cast(args)
            doc = event_args.document
            if doc is None:
                return

            # If switching to a doc with no active session, start one
            session = capture_core.get_current_session()
            if session is None or session.document_name != doc.name:
                log(f"Document activated: {doc.name}")
                capture_core.on_document_opened(doc)

        except Exception:
            log(f"DocumentActivated error: {traceback.format_exc()}")


class DocumentClosingHandler(adsk.core.DocumentEventHandler):
    """Handle document closing — compute diff, write JSONL."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.DocumentEventArgs.cast(args)
            doc = event_args.document
            if doc is None:
                return

            log(f"Document closing: {doc.name}")
            capture_core.on_document_closing(doc)

        except Exception:
            log(f"DocumentClosing error: {traceback.format_exc()}")


class CommandTerminatedHandler(adsk.core.ApplicationCommandEventHandler):
    """Detect post-processor completion.

    Listens for CommandTerminated events for Fusion 360's actual post
    command IDs: IronPostProcess (post dialog) and IronNcProgram
    (NC program viewer). Only IronPostProcess indicates that NC output
    has been written.
    """

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.ApplicationCommandEventArgs.cast(args)
            cmd_id = event_args.commandId

            # Fusion 360's actual post-processor command IDs
            if cmd_id not in ('IronPostProcess', 'IronNcProgram'):
                return

            # IronNcProgram is the NC program viewer, not a post action
            if cmd_id == 'IronNcProgram':
                return

            # Ignore if the command was cancelled (2 = CompletedSuccessfully)
            if event_args.terminationReason != 2:
                return

            log(f"Post completed (cmd: {cmd_id})")

            try:
                doc = app.activeDocument
                capture_core.on_post_completed(doc)
            except RuntimeError:
                log("No active document after post")

        except Exception:
            log(f"CommandTerminated error: {traceback.format_exc()}")


# ===========================================================================
# Add-in Lifecycle
# ===========================================================================

def run(context):
    """Add-in entry point — called when add-in starts."""
    global app, ui

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        log("Starting TraxisCapture v1.0.0")

        # Load configuration
        load_config()

        # Start background I/O worker
        io_worker.start()

        # Register document event handlers
        opened_handler = DocumentOpenedHandler()
        app.documentOpened.add(opened_handler)
        handlers.append(opened_handler)

        activated_handler = DocumentActivatedHandler()
        app.documentActivated.add(activated_handler)
        handlers.append(activated_handler)

        closing_handler = DocumentClosingHandler()
        app.documentClosing.add(closing_handler)
        handlers.append(closing_handler)

        # Register command terminated handler (for post detection)
        terminated_handler = CommandTerminatedHandler()
        ui.commandTerminated.add(terminated_handler)
        handlers.append(terminated_handler)

        # Check if there's already an active document with CAM
        try:
            if app.activeDocument:
                doc = app.activeDocument
                log(f"Active document at startup: {doc.name}")
                capture_core.on_document_opened(doc)
        except RuntimeError:
            pass  # No valid document open (normal at startup)

        log("Add-in started successfully")

    except Exception:
        log(f"Startup error: {traceback.format_exc()}")


def stop(context):
    """Add-in exit point — called when add-in stops."""
    global app, ui, handlers

    try:
        log("Stopping TraxisCapture")

        # Finalize any open session
        try:
            if app and app.activeDocument:
                capture_core.on_document_closing(app.activeDocument)
        except (RuntimeError, Exception):
            pass

        # Stop IO worker (flushes all queued writes)
        io_worker.stop()

        # Clear handler references
        handlers.clear()

        log("Add-in stopped")

    except Exception:
        log(f"Stop error: {traceback.format_exc()}")
