"""
Idle and focus detection for Programming Timer add-in.
Uses Windows API to detect user activity and Fusion 360 foreground state.
"""

import ctypes
from ctypes import wintypes
from datetime import datetime

# Windows API structures and functions
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('dwTime', wintypes.DWORD),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_idle_duration_ms():
    """
    Get the number of milliseconds since the last user input (system-wide).
    This includes mouse movement, keyboard, touch, etc.
    """
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        current_tick = kernel32.GetTickCount()
        # Handle tick count wraparound
        if current_tick < lii.dwTime:
            elapsed = (0xFFFFFFFF - lii.dwTime) + current_tick
        else:
            elapsed = current_tick - lii.dwTime
        return elapsed
    return 0


def get_idle_duration_seconds():
    """Get the number of seconds since the last user input."""
    return get_idle_duration_ms() / 1000.0


def get_foreground_window():
    """Get the handle of the currently active foreground window."""
    return user32.GetForegroundWindow()


def get_window_title(hwnd):
    """Get the title of a window by its handle."""
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd) + 1
    buffer = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, buffer, length)
    return buffer.value


def is_fusion_foreground():
    """
    Check if Fusion 360 is the foreground application.
    Returns True if Fusion 360 is in the foreground.
    """
    hwnd = get_foreground_window()
    if not hwnd:
        return False

    title = get_window_title(hwnd).lower()

    # Check for Fusion 360 in the window title
    # Fusion titles typically contain "Fusion 360" or "Autodesk Fusion"
    if "fusion 360" in title or "autodesk fusion" in title:
        return True

    # Also check the process name for more reliability
    try:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))

        # Get process handle
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
        if process:
            try:
                # Get process name
                buffer = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size))
                process_path = buffer.value.lower()
                if "fusion360" in process_path or "fusion 360" in process_path:
                    return True
            finally:
                kernel32.CloseHandle(process)
    except Exception:
        pass

    return False


def get_cursor_position():
    """Get the current cursor position."""
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (point.x, point.y)


class IdleDetector:
    """
    Detects user idle state for the Programming Timer.

    Uses a combination of:
    - System-wide last input time (most reliable)
    - Fusion 360 foreground state

    Idle is defined as: no input AND Fusion in foreground,
    OR Fusion not in foreground at all.
    """

    def __init__(self, idle_timeout_seconds=120):
        self.idle_timeout_seconds = idle_timeout_seconds
        self.last_activity_time = datetime.now()
        self.was_idle = False
        self.last_cursor_pos = get_cursor_position()

    def update_activity(self):
        """Mark that activity has been detected."""
        self.last_activity_time = datetime.now()
        self.was_idle = False

    def check_activity(self, fusion_foreground=None):
        """
        Check for user activity.
        Returns (is_active, activity_timestamp)

        is_active: True if user is currently active in Fusion
        activity_timestamp: The last time activity was detected

        Args:
            fusion_foreground: Pre-computed foreground state to avoid
                redundant Win32 API calls. If None, checks automatically.
        """
        # Use pre-computed value or check now
        if fusion_foreground is None:
            fusion_foreground = is_fusion_foreground()

        if not fusion_foreground:
            # Fusion not in foreground = not active (but don't update last_activity)
            self.was_idle = True
            return (False, self.last_activity_time)

        # Check system-wide idle time
        idle_seconds = get_idle_duration_seconds()

        if idle_seconds < 1:
            # Recent activity detected
            self.last_activity_time = datetime.now()
            self.was_idle = False
            return (True, self.last_activity_time)

        # Also check cursor movement as backup
        current_pos = get_cursor_position()
        if current_pos != self.last_cursor_pos:
            self.last_cursor_pos = current_pos
            self.last_activity_time = datetime.now()
            self.was_idle = False
            return (True, self.last_activity_time)

        # Check if we've exceeded idle timeout
        if idle_seconds >= self.idle_timeout_seconds:
            if not self.was_idle:
                # First detection of idle state
                self.was_idle = True
            return (False, self.last_activity_time)

        # Active but no recent input (within timeout window)
        return (True, self.last_activity_time)

    def is_idle(self):
        """Simple check if currently idle."""
        is_active, _ = self.check_activity()
        return not is_active

    def get_last_activity_time(self):
        """Return the timestamp of last detected activity."""
        return self.last_activity_time

    def set_idle_timeout(self, seconds):
        """Update the idle timeout value."""
        self.idle_timeout_seconds = seconds
