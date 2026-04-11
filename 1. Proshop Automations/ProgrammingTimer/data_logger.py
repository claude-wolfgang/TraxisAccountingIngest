"""
Data logging and state persistence for Programming Timer add-in.
Handles JSONL session logs and document-to-part mappings.

All file writes are routed through io_worker so the Fusion main thread
never blocks on disk I/O. Document mappings are cached in memory.
"""

import json
import os
from datetime import datetime
from config import get_log_folder, get_programmer_name, get_seat_name
import io_worker

VERSION = "1.0.0"

# In-memory cache for document-to-part mappings (avoids disk reads on main thread)
_mappings_cache = None

# In-memory cache for today's logged total (avoids reading full JSONL on button click)
_today_date = None
_today_total = 0


def get_log_file_path():
    """Return path to the main JSONL log file."""
    return os.path.join(get_log_folder(), "programming_time_log.jsonl")


def get_mappings_file_path():
    """Return path to the document-to-part mappings file."""
    return os.path.join(get_log_folder(), "document_mappings.json")


def get_state_file_path():
    """Return path to the timer state file for crash recovery."""
    return os.path.join(get_log_folder(), "timer_state.json")


# ===========================================================================
# Initialization
# ===========================================================================

def init_cache():
    """Load mappings and today's total into memory. Call once at startup."""
    global _mappings_cache, _today_date, _today_total
    _mappings_cache = _load_mappings_from_disk()
    print(f"[Timer] Mappings cache loaded: {len(_mappings_cache)} entries")

    # Load today's logged total from disk (one-time synchronous read)
    _today_date = datetime.now().strftime("%Y-%m-%d")
    _today_total = _read_today_total_from_disk(_today_date)
    print(f"[Timer] Today's logged total: {_today_total}s")


# ===========================================================================
# Session Logging
# ===========================================================================

def log_session(session_data):
    """
    Append a completed session to the JSONL log file.
    Builds the entry on the main thread (fast), queues the disk write.

    session_data should contain:
    - document_name
    - document_path
    - part_identifier
    - start_time (datetime)
    - end_time (datetime)
    - duration_seconds
    - idle_timeout_count
    """
    # Build the log entry (in-memory, fast)
    entry = {
        "document_name": session_data.get("document_name", ""),
        "document_path": session_data.get("document_path", ""),
        "part_identifier": session_data.get("part_identifier", ""),
        "date": session_data.get("start_time", datetime.now()).strftime("%Y-%m-%d"),
        "start_time": _format_datetime(session_data.get("start_time")),
        "end_time": _format_datetime(session_data.get("end_time")),
        "duration_seconds": session_data.get("duration_seconds", 0),
        "programmer": get_programmer_name(),
        "seat": get_seat_name(),
        "idle_timeout_count": session_data.get("idle_timeout_count", 0),
        "version": VERSION
    }

    # Update today's cached total if this session is from today
    global _today_date, _today_total
    today = datetime.now().strftime("%Y-%m-%d")
    if _today_date != today:
        # Date rolled over — reset cache
        _today_date = today
        _today_total = 0
    if entry["date"] == today:
        _today_total += entry.get("duration_seconds", 0)

    # Queue the disk write for the background thread
    io_worker.submit(_write_session_to_disk, entry)


def _write_session_to_disk(entry):
    """Append entry to JSONL file. Runs on IO worker thread."""
    log_path = get_log_file_path()
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[Timer] Session logged: {entry['part_identifier']} - {entry['duration_seconds']}s")
    except Exception as e:
        print(f"[Timer] Error logging session: {e}")


def _format_datetime(dt):
    """Format a datetime object to ISO 8601 string."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# ===========================================================================
# Document-to-Part Mappings (cached in memory)
# ===========================================================================

def _load_mappings_from_disk():
    """Read mappings JSON from disk. Called once at startup."""
    mappings_path = get_mappings_file_path()
    if os.path.exists(mappings_path):
        try:
            with open(mappings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Timer] Warning: Could not load mappings: {e}")
    return {}


def load_mappings():
    """Return the in-memory mappings cache."""
    global _mappings_cache
    if _mappings_cache is None:
        _mappings_cache = _load_mappings_from_disk()
    return _mappings_cache


def save_mappings(mappings):
    """Queue mappings write to background thread."""
    # Copy the dict so the worker thread has its own snapshot
    io_worker.submit(_write_mappings_to_disk, dict(mappings))


def _write_mappings_to_disk(mappings):
    """Write mappings JSON to disk. Runs on IO worker thread."""
    mappings_path = get_mappings_file_path()
    try:
        os.makedirs(os.path.dirname(mappings_path), exist_ok=True)
        with open(mappings_path, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, indent=2)
    except Exception as e:
        print(f"[Timer] Error saving mappings: {e}")


def get_part_identifier(document_name):
    """Get the part identifier for a document from the in-memory cache."""
    return load_mappings().get(document_name)


def set_part_identifier(document_name, part_identifier):
    """Update the in-memory cache and queue a disk write."""
    mappings = load_mappings()
    mappings[document_name] = part_identifier
    save_mappings(mappings)


# ===========================================================================
# State Persistence for Crash Recovery
# ===========================================================================

def save_timer_state(active_sessions):
    """
    Serialize timer state on main thread (fast), queue disk write.

    active_sessions is a dict keyed by document_name with datetime values.
    """
    # Convert datetimes to strings on main thread (fast, in-memory)
    state = {"active_sessions": {}}
    for doc_name, session in active_sessions.items():
        state["active_sessions"][doc_name] = {
            "part_identifier": session.get("part_identifier", ""),
            "document_path": session.get("document_path", ""),
            "session_start": _format_datetime(session.get("session_start")),
            "last_activity": _format_datetime(session.get("last_activity")),
            "accumulated_seconds": session.get("accumulated_seconds", 0),
            "idle_timeout_count": session.get("idle_timeout_count", 0)
        }

    # Queue the disk write for the background thread
    io_worker.submit(_write_state_to_disk, state)


def _write_state_to_disk(state):
    """Write state JSON to disk. Runs on IO worker thread."""
    state_path = get_state_file_path()
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[Timer] Error saving state: {e}")


def load_timer_state():
    """
    Load timer state from crash recovery file (synchronous).
    Only called once at startup, so blocking is acceptable.
    """
    state_path = get_state_file_path()
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return state.get("active_sessions", {})
        except Exception as e:
            print(f"[Timer] Warning: Could not load state: {e}")
    return {}


def clear_timer_state():
    """Queue state file deletion to background thread."""
    io_worker.submit(_delete_state_file)


def _delete_state_file():
    """Delete state file. Runs on IO worker thread."""
    state_path = get_state_file_path()
    if os.path.exists(state_path):
        try:
            os.remove(state_path)
        except Exception as e:
            print(f"[Timer] Warning: Could not clear state: {e}")


def recover_orphaned_sessions():
    """
    Check for orphaned sessions from a previous crash and finalize them.
    Returns list of recovered session data for logging.

    Reads state file synchronously (one-time at startup), then queues
    log writes and state deletion to the IO worker.
    """
    orphaned = load_timer_state()
    recovered = []

    for doc_name, session in orphaned.items():
        # Parse the last_activity time
        last_activity_str = session.get("last_activity", "")
        if last_activity_str:
            try:
                end_time = datetime.fromisoformat(last_activity_str)
            except ValueError:
                end_time = datetime.now()
        else:
            end_time = datetime.now()

        # Parse session start
        start_str = session.get("session_start", "")
        if start_str:
            try:
                start_time = datetime.fromisoformat(start_str)
            except ValueError:
                start_time = end_time
        else:
            start_time = end_time

        # Build session data
        session_data = {
            "document_name": doc_name,
            "document_path": session.get("document_path", ""),
            "part_identifier": session.get("part_identifier", doc_name),
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": session.get("accumulated_seconds", 0),
            "idle_timeout_count": session.get("idle_timeout_count", 0)
        }

        # Only log if there's meaningful duration
        if session_data["duration_seconds"] > 0:
            log_session(session_data)  # queued to IO worker
            recovered.append(doc_name)
            print(f"[Timer] Recovered orphaned session: {doc_name}")

    # Clear the state file after recovery (queued to IO worker)
    clear_timer_state()

    return recovered


def get_today_total_seconds():
    """
    Return today's total logged seconds from the in-memory cache.
    No disk I/O — the cache is loaded at startup and incremented by log_session().
    """
    global _today_date, _today_total
    today = datetime.now().strftime("%Y-%m-%d")
    if _today_date != today:
        # Date rolled over — reset cache
        _today_date = today
        _today_total = 0
    return _today_total


def _read_today_total_from_disk(today_str):
    """Read today's total from the JSONL log. Called once at startup."""
    log_path = get_log_file_path()
    total = 0
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("date") == today_str:
                            total += entry.get("duration_seconds", 0)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[Timer] Error reading log for today total: {e}")
    return total
