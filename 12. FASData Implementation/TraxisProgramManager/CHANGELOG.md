# TraxisProgramManager Changelog

## v1.6.0 -- 2026-04-02 -- Testable Architecture (tpm/ package)

Extracted all non-Fusion logic into a `tpm/` Python package that pytest can
import and test. The Fusion entry point is now a thin shell (~500 lines of
adsk-dependent code) that wires handlers to the testable package.

### New `tpm/` package (5 modules, ~610 lines)
- `tpm/config.py` -- Dropbox root detection, paths, credential loading
- `tpm/proshop.py` -- OAuth token caching, GraphQL client, customer PN lookup
- `tpm/naming.py` -- OP numbers, versioning, header parsing
- `tpm/fileops.py` -- File discovery, copy, auto-catch, folder lookup
- `tpm/wcs.py` -- WCS formatting (pure string logic)

### New test suite (52 tests across 6 files)
- `test_auto_catch.py` (8 tests) -- All auto-catch scenarios including partial
  failure, ProShop down, self-copy prevention
- `test_naming.py` (15 tests) -- OP formula, program numbers, header parsing,
  version increment logic
- `test_fileops.py` (6 tests) -- Folder lookup, file copy
- `test_proshop.py` (6 tests) -- Token caching/refresh, customer PN lookup
- `test_config.py` (5 tests) -- Dropbox detection, credential loading
- `test_wcs.py` (9 tests) -- Stock/model/selected origins, axis combinations

### Key changes
- `tpm/` modules use `logging.getLogger("tpm.*")` -- Fusion entry point bridges
  to `adsk.core.Application.get().log()` via `_FusionLogHandler`
- `get_next_version()` signature: `setup=None` -> `has_changes=None` (bool)
- `find_part_files_folder()` takes explicit `customer_part_number=None` param
- `auto_catch_posted_files()` takes `search_folders` and `delay` params for testing
- Dropbox-missing error moved from module-level RuntimeError to `run()` messageBox

## v1.5.0 — 2026-03-17 — Native CPS Metadata Headers

Moved NC metadata headers and tool IDs from TPM post-processing into the .cps
post processors themselves. This eliminates fragile file-search-and-inject logic.

- Added `traxisWCS` post property to all 5 .cps posts (Chevalier, Robodrill,
  Doosan, Hyundai, YCM)
- Added `writeTraxisHeader()` to all 5 .cps posts — generates PART, OP, WCS,
  POSTED lines natively during post-processing using `writeln()` (bypasses
  `permittedCommentChars` which excludes colons)
- Added `tool.productId` to tool comment lines in `writeProgramHeader()` for
  the 4 Fanuc mill posts (YCM already had it)
- TPM now sets `traxisWCS` NC Program parameter before posting so the .cps
  can read it via `getProperty("traxisWCS")`
- Simplified background thread to file copy only (no injection, no enhancement,
  no rename)
- Removed `inject_header_into_file()`, `_enhance_tool_lines()`, `_rename_nc_file()`

## v1.4.0 — 2026-03-16 — Customer Part Number & ProShop API

### PART FILES folder lookup fix

PART FILES Traxis folders use the **customer's part number** (e.g. `55200029`), not the
ProShop internal number (e.g. `TRA1-10983`). TPM was searching with the ProShop PN and
never finding a match.

- Added lightweight ProShop GraphQL client (`_load_credentials`, `_get_proshop_token`,
  `_proshop_query`, `lookup_customer_part_number`)
- `find_part_files_folder()` now searches with customer PN first, falls back to ProShop PN
- `get_part_number()` reads `Traxis:CustomerPartNumber` document attribute (set by
  ProShopBridge or cached from a prior API call)
- `apply_naming_to_setups()` saves `Traxis:CustomerPartNumber` to document attributes
  so subsequent runs skip the API call

### Lookup order for PART FILES folder

1. `Traxis:CustomerPartNumber` document attribute (set by ProShopBridge on WO select)
2. ProShop API query for `customerPartNumber` (on fresh documents)
3. Fall back to ProShop part number (original behavior)

## v1.3.0 — 2026-03-13 — Header Injection & Tool IDs

- Inject standardized NC header: PART, OP, VERSION, WCS, POSTED, PROGRAMMER
- Enhance post-processor tool comment lines with ProShop product IDs
- Background thread file processing (Fusion needs main thread to flush file)
- Copy to PART FILES folder after post

## v1.2.0 — 2026-03-06 — WCS & Versioning

- WCS G-code detection (G54, G55, G54.1 Px)
- Machinist-friendly WCS description (X: Center, Y: Near Side, Z: Top of Stock)
- Version auto-detection from NC file headers and legacy filenames
- Toolpath change detection — only increment version on actual changes

## v1.1.0 — 2026-02-28 — Setup Naming & NC Programs

- Setup naming convention: `{PartNumber}:{OP}` (e.g. `NP000674:60`)
- OP numbering: Setup 1→OP60, Setup 2→OP70, etc.
- Program number generation: 4-digit O-number from OP + version
- NC Program entity updates (name, number, comment, output folder)
- Fixture setup auto-skip (soft jaw, workholding, etc.)

## v1.0.0 — 2026-02-20 — Initial Release

- Basic TPM dialog: part number input, setup checkboxes, preview
- Part number detection from document attributes
- Output to `D:\Dropbox\NC Programs\{PartNumber}\`
