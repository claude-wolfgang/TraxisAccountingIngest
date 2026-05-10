# Lathe Program Review (T2 / YCM NTC1600LY)

**Audience:** Garrett, Thomas
**Goal:** Tell the data system which ProShop part each O-number on T2 is for. Once labeled, the audit can cross-reference FOCAS run data to ProShop work orders automatically.

---

## What you're filling in

Open this file in any text editor (Notepad++ works fine):

```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\25. Agent Exploration\lathe_programs.json
```

It has 38 entries — every O-number FOCAS has seen run on T2 between 2026-02-02 and 2026-05-01. They're sorted with the most-used programs first, so you can stop at any point and still cover the highest-impact programs.

Each entry looks like this:

```json
{
  "o_number": "O0680",
  "part_number": "",
  "description": "FOCAS bootstrap: 2337 samples over 7 day(s), 2026-02-02 to 2026-02-23. Replace with part name + op.",
  "op_number": null
}
```

You change three things:

| Field | What to put |
|---|---|
| `part_number` | The ProShop part number this program runs (e.g. `"10042"` or `"TRA1-0042"`). Case-sensitive. |
| `description` | A short note so anyone can identify it (e.g. `"Housing-DL Op60 1st side"`). Replaces the FOCAS bootstrap text. |
| `op_number` | Optional: the ProShop operation number (e.g. `60`). Use `null` if you don't know or it doesn't apply. |

Leave `o_number` exactly as it is.

If you don't know what a program is, leave `part_number` empty and add a note in `description` like `"Unknown — needs investigation"`. Empty entries are still tracked, they just don't auto-cross-reference.

---

## Two entries already have FOCAS suggestions — verify these first

When the bootstrap ran, FOCAS had captured the actual comment header for two programs. They have an extra `suggested_part_number` field. Verify in ProShop, then move the value into `part_number` (or correct it) and delete the `suggested_part_number` field.

| O-number | What FOCAS captured | Suggested part_number |
|---|---|---|
| **O2004** | `(10-2004 SIDE 1) (POST PROCESSOR YCM NTC1600LY ...)` | `10-2004` |
| **O4256** | `(PROGRAM NAME - OP50 AND OP60 10042 AND 10164) (MATERIAL - STEEL INCH - 1030)` | `10042` or `10164` (this program runs ops 50/60 of two parts — pick the primary, note the dual-use in description) |

---

## When you don't know what a program is

FOCAS may have captured comment text from inside the program while it was running. To see what it captured for any O-number:

```
python inspect_programs.py --o O0680
```

Run that on **.71** (the collector PC), or on any workstation if Dropbox has synced the database. The output shows every `(comment)` line FOCAS recorded for that program — sometimes that's the part description; sometimes it's just tool-by-tool notes.

To see all comments for all T2 programs at once:

```
python inspect_programs.py T2
```

If the output is empty for a program, FOCAS never caught a comment line — you'll need to read it off the YCM CRT or ask whoever wrote it.

To find the program on the YCM:
1. **MDI > PROG > DIR** lists every program in machine memory with its size and first comment line
2. Cursor to the O-number, hit **OPRT** → cursor reveals the program comment

---

## Looking up the part in ProShop

Quickest path: search ProShop's part list by partial part number. The customer prefix matters (some parts are `10042`, others `TRA1-0042`). Use exactly what shows in the part record.

If the program is for an old/discontinued part that no longer exists in ProShop, leave `part_number` empty and put a note in `description` (e.g. `"Legacy — customer cancelled 2024"`). Don't invent part numbers.

---

## When you're done

Just save the file. No commit, no reload, no service restart needed — the audit picks it up next time it runs. Future audits will start cross-referencing T2 FOCAS samples to ProShop WOs automatically using your mappings.

If a programmer adds a brand-new program on T2, you can add a new entry to the `programs` array following the same shape. The next FOCAS slow-poll cycle will register it once `program_directory` polling is fully working (verifying Tue 2026-05-05).

---

## Quick checklist

- [ ] Verify O2004 is `10-2004` in ProShop, update entry
- [ ] Verify O4256 is `10042` or `10164` in ProShop, update entry, note dual-use
- [ ] Walk top-of-file entries (most active programs) first
- [ ] Save file (no further action needed)
- [ ] Tell Wolfgang when done so he can run the audit and confirm cross-references work
