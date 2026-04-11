# Fix RuntimeError in ProgrammingTimer Fusion 360 Add-in

## File Location

`C:\Users\AbsoluteArm\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\ProgrammingTimer\ProgrammingTimer.py`

## Bug

At line 448, `app.activeDocument` throws `RuntimeError: 2 : InternalValidationError : document` when no valid document is open in Fusion 360 (e.g., start screen, between document transitions).

## Fix

Wrap the `if app.activeDocument:` check (and any related block that accesses `app.activeDocument`) in a try/except that catches `RuntimeError`. When caught, treat it the same as if there's no active document — skip the logic gracefully and continue.

### Example pattern

```python
try:
    if app.activeDocument:
        # existing logic...
except RuntimeError:
    # No valid document open, skip
    pass
```

## Important

- Search the entire file for **ALL** instances of `app.activeDocument` — there may be more than just line 448 that need the same guard
- Don't change any other behavior — just prevent the crash when no document is open
- Keep existing logging if present so skipped states are visible in the log
