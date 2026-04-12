# TraxisProgramManager — Fusion 360 Add-in

## Business Context
- **Company:** Traxis Manufacturing, Austin TX, ~5 people
- **Owner:** Wolfgang | **Programmers:** Garrett, Thomas
- **ERP:** ProShop (GraphQL API, OAuth 2.0) | **CAM:** Fusion 360
- **Machines:** 8 mills + 2 lathes, 5 FOCAS-connected (M2, M3, M6, M8, T2)

## What This Is
Fusion 360 add-in that manages the full NC program lifecycle: setup naming,
program versioning, WCS metadata, and file management. Click TPM in CAM toolbar,
enter part number, post normally — everything is pre-filled and files are
auto-copied to Dropbox NC Programs and PART FILES folders.

## Architecture (v1.6.0 — 2026-04-02)

Testable `tpm/` package extracted from the monolith. Fusion entry point is a
thin shell that wires adsk handlers to the package.

```
TraxisProgramManager.py    # Fusion entry point (915 lines, adsk-dependent)
TraxisProgramManager.manifest
resources/                 # Toolbar icons
tpm/                       # Testable package (NO adsk imports)
  __init__.py
  config.py                # Dropbox root, paths, credential loading
  proshop.py               # OAuth token, GraphQL client, customer PN lookup
  naming.py                # OP numbers, versioning, header parsing
  fileops.py               # File discovery, copy, auto-catch, folder lookup
  wcs.py                   # WCS formatting (pure string logic)
tests/                     # 52 tests, all passing
  conftest.py              # mock_dropbox, mock_proshop, sample_nc_file fixtures
  test_config.py           # 5 tests
  test_proshop.py          # 6 tests
  test_naming.py           # 15 tests
  test_fileops.py          # 6 tests
  test_auto_catch.py       # 8 tests (highest priority — new feature)
  test_wcs.py              # 9 tests
pyproject.toml             # pytest config
CHANGELOG.md               # Full version history
```

## Running Tests
```bash
pip install pytest           # One-time setup
python -m pytest tests/ -v   # Run from this directory
```

## Naming Convention
```
Setup 1 -> OP60    Setup 4 -> OP90
Setup 2 -> OP70    Setup 5 -> OP100
Setup 3 -> OP80    Setup 6 -> OP110
Formula: OP = 60 + (SetupNumber - 1) * 10
Program number: OP + version, zero-padded to 4 digits (OP60 v1 -> "0061")
```

## Key Design Decisions
- `tpm/` modules use `logging.getLogger("tpm.*")` — Fusion entry point bridges
  to `adsk.core.Application.get().log()` via `_FusionLogHandler` in `run()`
- `get_next_version()` takes `has_changes=None` (bool) not `setup` (adsk object).
  Caller does: `naming.get_next_version(..., has_changes=setup_has_changes(setup))`
- `find_part_files_folder()` takes explicit `customer_part_number=None` param
  (removes global `_customer_part_number` dependency from tpm/)
- `auto_catch_posted_files()` takes `search_folders=` and `delay=` params for testing
- `DROPBOX_ROOT` defaults to `None` in config; `run()` shows messageBox if missing

## Auto-Catch Feature (v1.5.0+)
When programmer posts without clicking TPM dialog first, the PostCompletedHandler
detects `IronPostProcess` with empty `_naming_state`, reads part number from
document attributes, and spawns a background thread that:
1. Scans Fusion default output folders for .nc files modified in last 60 seconds
2. Copies them to `NC Programs/{part_number}/`
3. Also copies to PART FILES if folder found (via customer PN lookup)

## Data Sources
- **ProShop API:** `https://traxismfg.adionsystems.com/api/graphql`
  - Credentials in `~/.traxis.env` or `~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env`
  - OAuth client_credentials flow, scope `parts:r`
- **Dropbox:** NC Programs + PART FILES Traxis (auto-detected via `%LOCALAPPDATA%/Dropbox/info.json`)

## ProShop API Gotchas
- Part number lookups are case-sensitive
- No server-side filtering — must fetch all, filter client-side
- Pagination broken beyond page 1 — use pageSize up to 500

## Git
- Repo initialized in this directory, 3 commits on `main`
- Identity: Wolfgang <wolf@traxismfg.com>
- Rollback to pre-refactor: `git checkout c680d5f -- TraxisProgramManager.py`

## Phase 4 TODO (Fusion Verification)
1. In Fusion: open CAM doc, click TPM, verify dialog populates and naming works
2. In Fusion: post without TPM -> check `[AUTO]` messages in Fusion console
3. `python -m pytest tests/ -v` — confirm still green
4. From P25: `python run_audit.py` -> NC program match rate unchanged

## Interfaces
Produces: NC files in `D:\Dropbox\NC Programs\{PartNumber}\`, copies to `D:\Dropbox\PART FILES Traxis\{Customer}\{CustomerPN}\`, Fusion document attributes (Traxis:PartNumber, Traxis:CustomerPartNumber)
Consumes: ProShop GraphQL API (parts:r scope, customer PN lookup), Dropbox info.json (root detection), ~/.traxis.env (OAuth credentials), Fusion CAM document (setups, operations, parameters)
Contracts: NC filename format `{PartNumber}_OP{OpNumber}.nc`, NC header format `(PART:) (OP:) (VERSION:) (WCS:) (POSTED:)`, OP formula `60 + (setup-1)*10`, .cps post processors must define `traxisWCS` property and call `writeTraxisHeader()`

## Known Issues
- **sys.path fix required** — Fusion doesn't add add-in directory to sys.path; the `tpm/` subpackage import needs explicit path insertion (added 2026-04-12)
- **NC Program naming** — `_update_nc_programs()` can't rename NC Programs that don't exist yet (created during posting). `_rename_nc_programs()` in PostCompletedHandler handles post-creation rename as fallback.
- **File name field** — Post dialog "File name" shows O-code instead of descriptive name. Requires paired TPM + .cps change (see session log 2026-04-12 Session 5).

## Related Projects
- **P25 (Agent Exploration):** Data quality agent, audit engine, Telegram bot
- **P12 (FASData):** FOCAS monitoring, TraxisTransfer, NC program traceability
- **P26 (SMT Post Processor):** .cps files that must handle TPM's naming convention
- **Master session log:** `../../main_session_log.md` (Dropbox-synced across machines)
