# Programming Timer — Test Regime

Use this checklist to verify the timer behaves correctly across all scenarios discussed. Each test describes what to do and what should happen. Mark pass/fail and note any issues.

---

## 1. Company File Detection

### 1.1 Company file triggers dialog
- Open a file from the Traxis hub/folder.
- **Expected:** Part identifier dialog appears with document name pre-filled.

### 1.2 Non-company file is ignored
- Open a personal or test file outside the company folder/hub.
- **Expected:** No dialog, no timer, no log entry. Complete silence.

### 1.3 Previously mapped company file skips dialog
- Open a company file that was already mapped in a prior session.
- **Expected:** No dialog. Toast or log message confirms tracking resumed. Timer starts immediately.

---

## 2. Timer Basics

### 2.1 Timer starts on file open
- Open a company file, complete the dialog.
- Open the status panel.
- **Expected:** Document shows as active with time accumulating.

### 2.2 Timer increments accurately
- Start a timer. Work normally for 5 minutes (mouse movement, orbiting, zooming).
- Check the status panel.
- **Expected:** Approximately 5 minutes recorded. Should not drift significantly from wall clock.

### 2.3 Manual NC work counts
- Open a company file. Spend a few minutes editing toolpaths, orbiting the model, making selections.
- **Expected:** All of this registers as activity. Timer does not pause during normal CAM work.

---

## 3. Document Switching

### 3.1 Switch between two company files
- Open File A (company). Timer starts.
- Open File B (company). Complete its dialog.
- **Expected:** File A shows paused. File B shows active.

### 3.2 Switch back to first file
- From test 3.1, switch back to File A.
- **Expected:** File B pauses. File A resumes. Both show correct accumulated time.

### 3.3 Three documents open simultaneously
- Open three company files. Switch between all three.
- **Expected:** Only the active document's timer runs at any given moment. The other two are paused. All three accumulate time independently.

### 3.4 Switch to non-company file
- Have a company file active and timing.
- Switch to a non-company file.
- **Expected:** Company file timer pauses. No timer starts for the non-company file.

### 3.5 Switch back from non-company file
- From test 3.4, switch back to the company file.
- **Expected:** Company file timer resumes.

---

## 4. Idle Detection

### 4.1 Go idle, return within buffer
- Work on a file. Stop all input for 1 minute. Then resume.
- **Expected:** Timer continues uninterrupted. No gap in the session. The 1-minute pause is counted as active time (within the 2-minute buffer).

### 4.2 Go idle, exceed buffer
- Work on a file. Note the time. Stop all input for 5 minutes. Then resume.
- **Expected:** Timer stopped retroactively at the timestamp of last activity (not 2 minutes after). When you resume, a new session begins. The 5-minute gap is NOT counted.

### 4.3 Verify retroactive stop time
- Work until exactly a known clock time (e.g., 10:15:00). Stop all input. Wait 5 minutes.
- Check the JSONL log for the completed session.
- **Expected:** Session `end_time` is approximately 10:15:00, not 10:17:00 (buffer expiry) or 10:20:00 (resume time).

### 4.4 Idle across all documents
- Have two company files open. Go idle for 5 minutes.
- **Expected:** Only the active document's timer was running, so only that one gets a session end. The paused document is unaffected.

### 4.5 Thinking vs. idle
- Sit and stare at the model without touching mouse or keyboard for 1 minute 50 seconds. Then move the mouse.
- **Expected:** Timer never paused. The activity just barely kept you within the buffer. No session break.

---

## 5. Background / Foreground

### 5.1 Alt-tab away from Fusion
- Have a company file active and timing.
- Alt-tab to Chrome (or any other application).
- **Expected:** Timer pauses immediately (or within one poll interval).

### 5.2 Return to Fusion
- From test 5.1, alt-tab back to Fusion.
- **Expected:** Timer resumes for the active document.

### 5.3 Extended time away from Fusion
- Alt-tab away for 10 minutes.
- **Expected:** No time accumulated during the 10 minutes away. Timer resumes cleanly on return.

### 5.4 Alt-tab during idle buffer
- Stop input. After 1 minute of idle, alt-tab away. Wait 5 minutes. Return.
- **Expected:** Timer should have stopped. The combination of idle + background should not create any weird double-counting or missed session ends.

### 5.5 Multiple monitor workflow
- Have Fusion on one screen and a PDF/browser on another. Click on the other screen.
- **Expected:** Fusion loses focus. Timer pauses. Click back to Fusion — timer resumes.

---

## 6. Session Management

### 6.1 Clean document close
- Work on a file for a few minutes. Close the document.
- Check the JSONL log.
- **Expected:** A complete session entry with correct start time, end time, and duration.

### 6.2 Clean Fusion close
- Work on two files. Close Fusion entirely.
- Check the JSONL log.
- **Expected:** Both documents have finalized session entries. No orphaned state in `timer_state.json`.

### 6.3 Overnight gap — new session
- Work on a file. Close Fusion. Next morning, open the same file.
- **Expected:** A new session starts. Yesterday's session is separate in the log. The two are NOT merged.

### 6.4 Short break gap
- Work on a file. Go idle for 35 minutes (exceeds 30-minute gap threshold). Resume.
- **Expected:** First session ended at last activity. New session starts on resume. Two separate entries in the log.

### 6.5 Break just under threshold
- Work on a file. Go idle for 25 minutes. Resume.
- **Expected:** Depends on idle buffer behavior. The 2-minute idle buffer would have already ended the first session at the 2-minute mark. Resuming after 25 minutes creates a new session. Verify the gap between sessions is correctly represented.

---

## 7. Crash Recovery

### 7.1 Simulate Fusion crash
- Work on a file for a few minutes. Kill Fusion via Task Manager (do not close normally).
- Restart Fusion. Open the same file.
- **Expected:** On restart, the add-in detects the orphaned session in `timer_state.json`. It finalizes it with `end_time` set to `last_activity`. The JSONL log gets the completed entry. A new session begins for the reopened file.

### 7.2 Verify orphaned session data
- After test 7.1, check the JSONL log.
- **Expected:** The orphaned session has reasonable `end_time` and `duration_seconds`. It does not include time from the crash to the restart.

### 7.3 Crash with multiple files open
- Have three files open and timing. Kill Fusion.
- Restart and reopen.
- **Expected:** All three orphaned sessions are recovered with correct last-activity timestamps.

---

## 8. Data Integrity

### 8.1 JSONL format
- After several sessions, open `programming_time_log.jsonl`.
- **Expected:** Each line is valid JSON. One object per line. Fields match the spec: `document_name`, `part_identifier`, `date`, `start_time`, `end_time`, `duration_seconds`, `programmer`, `seat`, `version`.

### 8.2 Duration accuracy
- Work on a file for a known duration (use a stopwatch). Close the document.
- **Expected:** `duration_seconds` in the log is within ~30 seconds of the stopwatch time (accounting for poll interval precision).

### 8.3 Multiple sessions same day
- Open and close the same file three times in one day, working briefly each time.
- **Expected:** Three separate session entries in the log, all with the same `date` and `part_identifier` but different `start_time`/`end_time`.

### 8.4 Document mapping persistence
- Map a document to a part identifier. Close Fusion. Reopen Fusion and the same document.
- **Expected:** `document_mappings.json` contains the mapping. No dialog appears. The correct `part_identifier` is used in the new session log entry.

### 8.5 Concurrent seats (Dropbox sync)
- Have two machines writing to the same JSONL file via Dropbox.
- Run timers on both simultaneously on different files.
- **Expected:** Both machines' sessions appear in the log. No corrupted lines. Dropbox may create a conflict file in rare cases — note if this happens but it's acceptable.

---

## 9. UI / Notifications

### 9.1 Status panel shows correct state
- Open two company files. Switch between them.
- Open the status panel at various points.
- **Expected:** Active document shows ● with running time. Paused document shows ○ with frozen time. "Today total" reflects sum of all active time today.

### 9.2 Toast/log on resume
- Open a previously mapped file.
- **Expected:** A toast notification or Text Commands log entry confirms tracking has started, including the part identifier.

### 9.3 First-open dialog defaults
- Open a new company file.
- **Expected:** Dialog shows document name in the text field. Programmer can accept the default or edit it. No cancel/close option that would skip tracking.

### 9.4 Status panel with no active files
- Close all company files. Open the status panel.
- **Expected:** Panel shows no active timers. May show today's total from completed sessions, or "No active timers."

---

## 10. Edge Cases

### 10.1 Very short session
- Open a company file. Close it after 10 seconds.
- **Expected:** A session is logged with ~10 seconds duration. It's not filtered out — we're capturing everything for now.

### 10.2 Open same file twice (if possible)
- Try to open the same Fusion document in two windows or tabs if Fusion allows it.
- **Expected:** Only one timer runs. No duplicate tracking.

### 10.3 Rename document while tracking
- Start tracking a document. Rename it (Save As with new name).
- **Expected:** Timer handles this gracefully. Session should finalize under the old name or transfer to the new name — document the actual behavior either way.

### 10.4 Network loss (Dropbox offline)
- Disconnect from the network while a session is running. Close the document.
- **Expected:** Session writes to the local JSONL file. Dropbox syncs it when reconnected. No data loss.

### 10.5 Rapid switching
- Switch between three open company files rapidly (every 2-3 seconds) for 30 seconds.
- **Expected:** No crashes, no errors in Text Commands. Each document accumulates a small amount of time. Total across all three roughly equals 30 seconds.

### 10.6 Add-in stop/restart
- While tracking, go to Add-Ins dialog and stop ProgrammingTimer. Then restart it.
- **Expected:** Stop finalizes all active sessions. Restart picks up cleanly. Reopening the same files starts new sessions.
