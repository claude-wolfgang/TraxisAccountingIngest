# ProgrammingTimer Changelog

## v1.2.0 — 2026-03-02 — Cloud API Freeze Fix

Fusion 360 was freezing when opening documents. Root cause: `get_document_path()`
traversed the cloud folder hierarchy via repeated `folder.parentFolder` API calls
on the UI thread. Each call is a synchronous round-trip to Fusion's cloud backend.
Opening a single document triggered this traversal **twice** (documentOpened +
documentActivated events back-to-back).

### Changed: `ProgrammingTimer.py`

- **Eliminated folder traversal** in `get_document_path()` — replaced the
  `while folder: folder.parentFolder` loop (N cloud API calls) with a single
  `doc.dataFile.parentProject.name` call (1 API call max)
- **Added `_doc_path_cache` dict** — path resolution results cached by doc name,
  so even the single API call only happens once per document lifetime
- The company file check only needs `"Traxis Main"` in the path; folder names
  were never needed
- Version bumped to 1.2.0

### Changed: `timer_core.py`

- **Added `_state_dirty` flag** to `TimerManager` — `_save_state()` now skips
  serialization + io_worker queue when nothing has changed
- **Added `_mark_dirty()` method** — called by event handlers that actually
  mutate state (doc open/close/activate, focus change, idle transitions)
- **`poll_activity()` no longer saves every 15 seconds** — only marks dirty on
  actual idle↔active transitions. Routine polls with no state change are free.
- Event-driven methods (`on_document_opened`, `on_document_closed`, etc.) use
  `_save_state(force=True)` to ensure immediate persistence on real events

### Changed: `ProgrammingTimer.manifest`

- Version bumped to 1.2.0

---

## v1.1.0 — 2026-02-16 — Freeze Audit Fixes

Addresses all Critical and High findings from `FREEZE_AUDIT_REPORT.md`.
The main-thread Fusion UI no longer blocks on any file I/O.

### New File: `io_worker.py`
Background I/O worker thread using `queue.Queue`. All file writes (state saves,
session logs, mapping updates) are queued here so the Fusion main thread never
blocks on disk I/O — especially important since files live on Dropbox-synced paths.

- `start()` — launch daemon worker thread
- `stop()` — send sentinel, drain remaining queued items, join thread (5s timeout)
- `submit(func, *args)` — queue a function call for the worker

### Changed: `data_logger.py`

**Mappings cache (fixes C2, C3):**
- Added `_mappings_cache` in-memory dict, loaded once at startup via `init_cache()`
- `get_part_identifier()` now reads from memory (was: read JSON from Dropbox every call)
- `set_part_identifier()` updates cache in memory + queues disk write to io_worker

**Today's total cache (fixes H3):**
- Added `_today_date` / `_today_total` in-memory cache
- `init_cache()` loads today's total from JSONL once at startup
- `log_session()` increments `_today_total` when logging a today-dated session
- `get_today_total_seconds()` returns from cache (was: read and parse entire JSONL file)
- Handles midnight date rollover by resetting cache

**Queued writes (fixes C1, H4, H5):**
- `log_session()` builds entry dict on main thread (fast), queues JSONL append to io_worker
- `save_timer_state()` serializes datetimes on main thread, queues JSON write to io_worker
- `clear_timer_state()` queues file deletion to io_worker
- `save_mappings()` queues write with a dict copy (snapshot for thread safety)

**Unchanged:**
- `load_timer_state()` — still synchronous (one-time startup read, acceptable)
- `recover_orphaned_sessions()` — reads state synchronously at startup, queues writes

### Changed: `ProgrammingTimer.py`

- Version bumped to 1.1.0
- `run()` startup order: `load_config()` -> `io_worker.start()` -> `init_cache()` ->
  `TimerManager()` -> `recover_orphaned_sessions()`
- `stop()` shutdown order: `timer_manager.shutdown()` -> `io_worker.stop()` (flushes queue)
  -> unregister events -> destroy UI

### Changed: `timer_core.py` (Medium fixes)

- `poll_activity()` now accepts optional `fusion_foreground` parameter, passes it
  through to `idle_detector.check_activity()` to avoid redundant Win32 API call

### Changed: `idle_detector.py` (Medium fixes)

- `check_activity()` now accepts optional `fusion_foreground` parameter — when
  provided, skips calling `is_fusion_foreground()` (already computed by poll handler)

### Medium fixes across all files

- **M2**: All 21 bare `except:` clauses in `ProgrammingTimer.py` replaced with
  `except Exception:` to avoid swallowing `SystemExit`/`KeyboardInterrupt`
- **M5**: `PollEventHandler.notify()` now passes its already-computed `is_focused`
  value through `poll_activity()` → `check_activity()`, eliminating a redundant
  `is_fusion_foreground()` Win32 API call per poll cycle

### Findings Addressed

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| C1 | Critical | `_save_state()` writes JSON to Dropbox every 15s on main thread | Queued to io_worker |
| C2 | Critical | `get_part_identifier()` reads JSON on every doc open/switch | Returns from in-memory cache |
| C3 | Critical | `set_part_identifier()` reads+writes JSON on main thread | Updates cache + queues write |
| H3 | High | `get_today_total_seconds()` reads full JSONL on button click | Returns from in-memory cache |
| H4 | High | `log_session()` writes JSONL on main thread during doc close | Queued to io_worker |
| H5 | High | `recover_orphaned_sessions()` multiple file ops at startup | Writes queued to io_worker |
| M2 | Medium | Bare `except:` swallows `SystemExit`/`KeyboardInterrupt` | Replaced with `except Exception:` |
| M5 | Medium | Double `is_fusion_foreground()` Win32 call per poll | Foreground state passed through from poll handler |
| L1 | Low | Orphaned `new 1.py` debug script in add-in folder | Deleted |
