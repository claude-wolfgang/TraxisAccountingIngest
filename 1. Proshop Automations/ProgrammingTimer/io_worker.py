"""
Background I/O worker thread for Programming Timer add-in.

All file writes (state saves, session logs, mapping updates) are queued
here so the Fusion 360 main thread never blocks on disk I/O.
"""

import threading
import queue

_io_queue = queue.Queue()
_io_thread = None


def start():
    """Start the background I/O worker thread."""
    global _io_thread
    _io_thread = threading.Thread(target=_loop, daemon=True, name="TimerIOWorker")
    _io_thread.start()


def stop():
    """Stop the I/O worker, flushing all remaining queued items first."""
    _io_queue.put(None)  # sentinel to exit loop
    if _io_thread and _io_thread.is_alive():
        _io_thread.join(timeout=5)


def submit(func, *args):
    """Queue a function call for the I/O worker thread."""
    _io_queue.put((func, args))


def _loop():
    """Worker loop — process queued I/O until sentinel received."""
    while True:
        item = _io_queue.get()
        if item is None:
            # Drain any remaining items before exiting
            while not _io_queue.empty():
                try:
                    remaining = _io_queue.get_nowait()
                    if remaining is not None:
                        func, args = remaining
                        func(*args)
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"[Timer] IO worker drain error: {e}")
            break
        func, args = item
        try:
            func(*args)
        except Exception as e:
            print(f"[Timer] IO worker error: {e}")
