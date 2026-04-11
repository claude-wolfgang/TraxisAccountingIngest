"""
Core timer logic and session management for Programming Timer add-in.
"""

from datetime import datetime
from idle_detector import IdleDetector
from data_logger import (
    log_session, save_timer_state, clear_timer_state,
    get_part_identifier, set_part_identifier
)
from config import get_idle_timeout, get_gap_threshold


class DocumentTimer:
    """
    Tracks time for a single document.
    """

    def __init__(self, document_name, document_path, part_identifier):
        self.document_name = document_name
        self.document_path = document_path
        self.part_identifier = part_identifier

        self.session_start = datetime.now()
        self.last_activity = datetime.now()
        self.accumulated_seconds = 0
        self.is_active = False
        self.is_paused = False
        self.idle_timeout_count = 0

        # Track when the current active segment started
        self._segment_start = None

    def start(self):
        """Start or resume timing."""
        if not self.is_active:
            self.is_active = True
            self.is_paused = False
            self._segment_start = datetime.now()
            self.last_activity = datetime.now()
            print(f"[Timer] Started: {self.document_name}")

    def pause(self):
        """Pause timing (document no longer active)."""
        if self.is_active and not self.is_paused:
            self._finalize_segment()
            self.is_paused = True
            print(f"[Timer] Paused: {self.document_name}")

    def resume(self):
        """Resume timing after pause."""
        if self.is_paused:
            self.is_paused = False
            self._segment_start = datetime.now()
            self.last_activity = datetime.now()
            print(f"[Timer] Resumed: {self.document_name}")

    def record_activity(self):
        """Record that user activity was detected."""
        self.last_activity = datetime.now()

    def handle_idle_timeout(self, last_activity_time):
        """
        Handle idle timeout. The timer should stop at last_activity_time,
        not at the current time.
        """
        if self.is_active and self._segment_start:
            # Calculate time up to last activity, not current time
            segment_seconds = (last_activity_time - self._segment_start).total_seconds()
            if segment_seconds > 0:
                self.accumulated_seconds += segment_seconds
            self._segment_start = None
            self.is_active = False
            self.idle_timeout_count += 1
            print(f"[Timer] Idle timeout: {self.document_name} (stopped at {last_activity_time})")

    def _finalize_segment(self):
        """Finalize the current timing segment."""
        if self._segment_start:
            segment_seconds = (datetime.now() - self._segment_start).total_seconds()
            self.accumulated_seconds += segment_seconds
            self._segment_start = None

    def stop(self):
        """Stop timing completely and return session data."""
        self._finalize_segment()
        self.is_active = False
        self.is_paused = False

        session_data = {
            "document_name": self.document_name,
            "document_path": self.document_path,
            "part_identifier": self.part_identifier,
            "start_time": self.session_start,
            "end_time": self.last_activity,
            "duration_seconds": int(self.accumulated_seconds),
            "idle_timeout_count": self.idle_timeout_count
        }

        print(f"[Timer] Stopped: {self.document_name} - {int(self.accumulated_seconds)}s total")
        return session_data

    def get_current_duration(self):
        """Get the current total duration including active segment."""
        total = self.accumulated_seconds
        if self.is_active and self._segment_start and not self.is_paused:
            total += (datetime.now() - self._segment_start).total_seconds()
        return int(total)

    def to_state_dict(self):
        """Convert to dict for state persistence."""
        return {
            "part_identifier": self.part_identifier,
            "document_path": self.document_path,
            "session_start": self.session_start,
            "last_activity": self.last_activity,
            "accumulated_seconds": self.get_current_duration(),
            "idle_timeout_count": self.idle_timeout_count
        }


class TimerManager:
    """
    Manages all document timers and handles events.
    """

    def __init__(self):
        self.timers = {}  # keyed by document_name
        self.active_document = None
        self.idle_detector = IdleDetector(get_idle_timeout())
        self.is_fusion_focused = True
        self._poll_callback = None
        self._state_dirty = False

    def on_document_opened(self, document_name, document_path, part_identifier=None):
        """
        Handle document opened event.
        Returns True if this is a new document needing part identifier input.
        """
        # Check if we have a stored mapping
        stored_part = get_part_identifier(document_name)
        if stored_part:
            part_identifier = stored_part

        # Check for gap threshold - should we start a new session?
        if document_name in self.timers:
            timer = self.timers[document_name]
            gap = (datetime.now() - timer.last_activity).total_seconds()
            if gap > get_gap_threshold():
                # Large gap - finalize old session and start new one
                session_data = timer.stop()
                if session_data["duration_seconds"] > 0:
                    log_session(session_data)
                del self.timers[document_name]
                print(f"[Timer] New session after {int(gap)}s gap: {document_name}")

        # Create new timer if needed
        if document_name not in self.timers:
            if part_identifier is None:
                # Need to ask user for part identifier
                return True

            timer = DocumentTimer(document_name, document_path, part_identifier)
            self.timers[document_name] = timer

            # Save the mapping for future use
            set_part_identifier(document_name, part_identifier)

        # Start/resume the timer
        self.timers[document_name].start()
        self.active_document = document_name
        self._mark_dirty()
        self._save_state(force=True)

        return False

    def on_document_activated(self, document_name, document_path):
        """Handle switching to a different document."""
        # Pause the previous document
        if self.active_document and self.active_document in self.timers:
            self.timers[self.active_document].pause()

        # Resume or start the new document
        if document_name in self.timers:
            self.timers[document_name].resume()
            self.active_document = document_name
        else:
            # Document not tracked yet - might need to check if company file
            self.active_document = document_name

        self._mark_dirty()
        self._save_state(force=True)

    def on_document_closed(self, document_name):
        """Handle document closed event."""
        if document_name in self.timers:
            session_data = self.timers[document_name].stop()
            if session_data["duration_seconds"] > 0:
                log_session(session_data)
            del self.timers[document_name]

            if self.active_document == document_name:
                self.active_document = None

            self._mark_dirty()
            self._save_state(force=True)

    def on_fusion_focus_changed(self, has_focus):
        """Handle Fusion 360 gaining/losing focus."""
        self.is_fusion_focused = has_focus

        if has_focus:
            # Resume active document timer
            if self.active_document and self.active_document in self.timers:
                self.timers[self.active_document].resume()
                self.idle_detector.update_activity()
        else:
            # Pause all timers
            for timer in self.timers.values():
                if timer.is_active:
                    timer.pause()

        self._mark_dirty()
        self._save_state(force=True)

    def poll_activity(self, fusion_foreground=None):
        """
        Called periodically to check for idle state.
        Should be called every poll_interval_seconds.

        Only triggers a state save when a meaningful transition occurs
        (idle→active or active→idle), not on every poll tick.

        Args:
            fusion_foreground: Pre-computed foreground state to avoid
                redundant Win32 API calls. If None, check_activity checks itself.
        """
        if not self.is_fusion_focused:
            return

        is_active, last_activity = self.idle_detector.check_activity(fusion_foreground=fusion_foreground)

        if is_active:
            # User is active - record activity on the active timer
            if self.active_document and self.active_document in self.timers:
                timer = self.timers[self.active_document]
                timer.record_activity()
                if not timer.is_active or timer.is_paused:
                    # Transition: idle/paused → active
                    timer.start()
                    self._mark_dirty()
        else:
            # User is idle - handle timeout
            if self.active_document and self.active_document in self.timers:
                timer = self.timers[self.active_document]
                if timer.is_active:
                    # Transition: active → idle
                    timer.handle_idle_timeout(last_activity)
                    self._mark_dirty()

        # Only save if something actually changed
        self._save_state()

    def on_activity_resumed(self):
        """Called when user activity resumes after idle."""
        self.idle_detector.update_activity()

        if self.active_document and self.active_document in self.timers:
            timer = self.timers[self.active_document]
            # Start a new segment
            timer.session_start = datetime.now()  # New session after idle
            timer.start()
            self._mark_dirty()
            self._save_state(force=True)

    def shutdown(self):
        """Clean shutdown - finalize all sessions."""
        for doc_name in list(self.timers.keys()):
            session_data = self.timers[doc_name].stop()
            if session_data["duration_seconds"] > 0:
                log_session(session_data)

        self.timers.clear()
        self.active_document = None
        clear_timer_state()
        print("[Timer] Shutdown complete - all sessions finalized")

    def _mark_dirty(self):
        """Mark state as needing a save."""
        self._state_dirty = True

    def _save_state(self, force=False):
        """Save current state for crash recovery. Skips if nothing changed."""
        if not force and not self._state_dirty:
            return
        self._state_dirty = False
        state = {}
        for doc_name, timer in self.timers.items():
            state[doc_name] = timer.to_state_dict()
        save_timer_state(state)

    def get_status(self):
        """
        Get current status for display.
        Returns list of (document_name, duration_seconds, is_active)
        """
        status = []
        for doc_name, timer in self.timers.items():
            is_active = (doc_name == self.active_document and
                        timer.is_active and
                        not timer.is_paused and
                        self.is_fusion_focused)
            status.append({
                "document_name": doc_name,
                "part_identifier": timer.part_identifier,
                "duration_seconds": timer.get_current_duration(),
                "is_active": is_active
            })
        return status

    def get_today_total(self):
        """Get total time tracked today (including current sessions)."""
        from data_logger import get_today_total_seconds
        total = get_today_total_seconds()

        # Add current session times
        for timer in self.timers.values():
            total += timer.get_current_duration()

        return total
