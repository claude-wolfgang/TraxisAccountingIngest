"""
Capture Core — document origin detection, session management, diff writing.

Manages the lifecycle of a capture session:
  1. Document opened -> detect origin, tag attributes, take Snapshot A
  2. Post completes  -> take Snapshot B, inject CAPTURE tags
  3. Document closing -> compute diff, write JSONL via io_worker
"""

import adsk.core
import adsk.cam
import os
import json
import secrets
from datetime import datetime

from tc_config import get_output_dir, get_nc_programs_root
from snapshot import take_snapshot
from naming_enforcer import enforce_naming, get_part_number_from_doc
from nc_injector import inject_capture_tags, find_recent_nc_files
import tc_io_worker as io_worker


def _log(msg):
    try:
        adsk.core.Application.get().log(f"[TraxisCapture:Core] {msg}")
    except Exception:
        pass


# Active session state
_current_session = None


class CaptureSession:
    """Tracks state for a single document capture session."""

    def __init__(self, session_id, document_name, origin):
        self.session_id = session_id
        self.document_name = document_name
        self.origin = origin
        self.snapshot_a = None
        self.snapshot_b = None
        self.naming_corrections = []
        self.nc_files_injected = []
        self.started_at = datetime.now()

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "document_name": self.document_name,
            "origin": self.origin,
            "started_at": self.started_at.isoformat(timespec="seconds"),
        }


def generate_session_id():
    """Generate a session ID: YYYY-MM-DD_{random_hex}."""
    date = datetime.now().strftime("%Y-%m-%d")
    rand = secrets.token_hex(3)  # 6 hex chars
    return f"{date}_{rand}"


def detect_origin(document):
    """Detect document origin and tag it via attributes.

    Returns: "toolpath", "prior_program", or "fresh"
    """
    if document is None:
        return "fresh"

    # Check if already tagged
    try:
        attr = document.attributes.itemByName('TraxisCapture', 'origin')
        if attr and attr.value:
            return attr.value
    except Exception:
        pass

    # Check for Toolpath import markers
    origin = _detect_origin_type(document)

    # Tag the document
    try:
        document.attributes.add('TraxisCapture', 'origin', origin)
        ts = datetime.now().isoformat(timespec="seconds")
        if origin == "toolpath":
            document.attributes.add(
                'TraxisCapture', 'toolpath_import_ts', ts)
        elif origin == "prior_program":
            try:
                ver = str(getattr(document, 'version', ''))
                document.attributes.add(
                    'TraxisCapture', 'prior_version', ver)
            except Exception:
                pass
    except Exception as e:
        _log(f"Could not tag origin: {e}")

    return origin


def _detect_origin_type(document):
    """Determine if doc is from toolpath, prior program, or fresh."""
    try:
        cam = adsk.cam.CAM.cast(
            document.products.itemByProductType('CAMProductType'))
        if cam is None or cam.setups.count == 0:
            return "fresh"  # No CAM content

        # Check for Toolpath-specific markers
        # Toolpath imports typically have specific attributes or naming
        try:
            attr = document.attributes.itemByName('Toolpath', 'source')
            if attr:
                return "toolpath"
        except Exception:
            pass

        # Check for generation metadata that Toolpath adds
        try:
            attr = document.attributes.itemByName('Toolpath', 'generated')
            if attr:
                return "toolpath"
        except Exception:
            pass

        # Has CAM content but no Toolpath markers — prior program
        return "prior_program"

    except Exception:
        return "fresh"


def on_document_opened(document):
    """Handle document opened — detect origin, take Snapshot A.

    Called from DocumentOpenedHandler.
    """
    global _current_session

    if document is None:
        return

    # Check for CAM content
    try:
        cam = adsk.cam.CAM.cast(
            document.products.itemByProductType('CAMProductType'))
        if cam is None:
            _log(f"No CAM in '{document.name}' — skipping capture")
            return
    except Exception:
        return

    # Create session
    session_id = generate_session_id()
    origin = detect_origin(document)

    _current_session = CaptureSession(session_id, document.name, origin)
    _log(f"Session started: {session_id} origin={origin} doc={document.name}")

    # Tag session on document
    try:
        document.attributes.add(
            'TraxisCapture', 'session_id', session_id)
    except Exception:
        pass

    # Naming enforcement moved to TraxisPostProcessor (v1.2.0)
    # TraxisCapture no longer renames setups — it only observes.

    # Take Snapshot A (baseline)
    snapshot_a = take_snapshot(session_id, origin)
    if snapshot_a:
        _current_session.snapshot_a = snapshot_a
        _log(f"Snapshot A taken: {len(snapshot_a.get('setups', []))} setups")
    else:
        _log("Snapshot A: no CAM data captured")


def on_post_completed(document):
    """Handle post completion — take Snapshot B, inject CAPTURE tags.

    Called from CommandTerminatedHandler when a post command completes.
    """
    global _current_session

    if _current_session is None:
        _log("Post completed but no active session")
        return
    if document is None:
        return

    session_id = _current_session.session_id

    # Take Snapshot B (post-completion state)
    snapshot_b = take_snapshot(session_id, _current_session.origin)
    if snapshot_b:
        _current_session.snapshot_b = snapshot_b
        _log(f"Snapshot B taken: {len(snapshot_b.get('setups', []))} setups")
    else:
        _log("Snapshot B: no CAM data captured")

    # Find and inject CAPTURE tags into recently posted NC files
    _inject_tags_into_nc_output(session_id, snapshot_b)


def _inject_tags_into_nc_output(session_id, snapshot_b):
    """Locate recent NC output files and inject CAPTURE tags."""
    # Check multiple possible output locations
    search_dirs = set()

    # NC Programs root
    nc_root = get_nc_programs_root()
    if os.path.isdir(nc_root):
        search_dirs.add(nc_root)
        # Also check part-specific subdirectories
        if _current_session:
            try:
                app = adsk.core.Application.get()
                doc = app.activeDocument
                part = get_part_number_from_doc(doc)
                if part:
                    part_dir = os.path.join(nc_root, part)
                    if os.path.isdir(part_dir):
                        search_dirs.add(part_dir)
            except Exception:
                pass

    # Search for recent NC files
    for search_dir in search_dirs:
        recent = find_recent_nc_files(search_dir, max_age_seconds=120)
        for nc_path in recent:
            count = inject_capture_tags(nc_path, session_id, snapshot_b)
            if count > 0 and _current_session:
                _current_session.nc_files_injected.append(nc_path)


def on_document_closing(document):
    """Handle document closing — compute diff, write JSONL.

    Called from DocumentClosingHandler.
    """
    global _current_session

    if _current_session is None:
        return
    if document is None or document.name != _current_session.document_name:
        return

    session = _current_session
    _current_session = None

    # Only write diff if we have at least one snapshot
    if session.snapshot_a is None and session.snapshot_b is None:
        _log("No snapshots captured — skipping diff write")
        return

    # Queue diff writing to background thread
    io_worker.submit(_write_diff_record, session)
    _log(f"Session {session.session_id} queued for diff write")


def _write_diff_record(session):
    """Write the diff record to JSONL file (runs on IO worker thread)."""
    try:
        # Import diff engine here (may not be available yet in Phase 2)
        try:
            from diff_engine import compute_diff
            diff = compute_diff(
                session.snapshot_a, session.snapshot_b, session.origin)
        except ImportError:
            # Diff engine not yet implemented — write raw snapshots
            diff = _build_basic_diff(session)

        output_dir = get_output_dir()
        filename = f"{session.session_id}_diff.jsonl"
        filepath = os.path.join(output_dir, filename)

        record = {
            "session_id": session.session_id,
            "document": session.document_name,
            "origin": session.origin,
            "started_at": session.started_at.isoformat(timespec="seconds"),
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "naming_corrections": session.naming_corrections,
            "nc_files_injected": session.nc_files_injected,
            "diff": diff,
            "snapshot_a": session.snapshot_a,
            "snapshot_b": session.snapshot_b,
        }

        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str) + "\n")

        _log(f"Diff written: {filepath}")

        # Trigger pattern accumulator (if available)
        try:
            from pattern_accumulator import accumulate_patterns
            accumulate_patterns()
        except ImportError:
            pass  # Pattern accumulator not yet implemented

    except Exception as e:
        _log(f"Error writing diff record: {e}")


def _build_basic_diff(session):
    """Build a basic diff when diff_engine is not yet available."""
    a = session.snapshot_a
    b = session.snapshot_b

    if a is None and b is None:
        return {"status": "no_data"}
    if a is None:
        return {"status": "snapshot_b_only", "type": "new_baseline"}
    if b is None:
        return {"status": "snapshot_a_only", "type": "no_post"}

    # Basic comparison
    a_ops = set()
    b_ops = set()
    for setup in a.get("setups", []):
        for op in setup.get("operations", []):
            a_ops.add(op.get("name", ""))
    for setup in b.get("setups", []):
        for op in setup.get("operations", []):
            b_ops.add(op.get("name", ""))

    return {
        "status": "basic",
        "operations_in_a": len(a_ops),
        "operations_in_b": len(b_ops),
        "operations_added": list(b_ops - a_ops),
        "operations_removed": list(a_ops - b_ops),
        "operations_common": list(a_ops & b_ops),
    }


def get_current_session():
    """Return the current active session, or None."""
    return _current_session
