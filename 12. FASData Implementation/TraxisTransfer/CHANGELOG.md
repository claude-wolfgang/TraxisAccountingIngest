# Changelog

All notable changes to TraxisTransfer will be documented in this file.

## [0.4.0] - 2026-03-19

### Added
- Full integration: UI wired to transfer service, folder resolver, and status checker
- Background transfer execution with progress callbacks
- Transfer confirmation dialog before sending
- Receive workflow with program number prompt and file save dialog
- Auto-hide progress bar after successful transfer
- Recent transfer log loads on startup

### Fixed
- FOCAS struct tests: use ctypes type-level sizeof instead of instance-level
- Haas SSH test: clear side_effect before setting return_value for exec_command mock

## [0.3.0] - 2026-03-19

### Added
- CustomTkinter dark UI (ISA-101 compliant)
  - Machine panel with status indicators (green/gray dots)
  - File browser with search, sort (name/date/size), file details
  - Transfer confirmation dialog with file/machine/size summary
  - Progress bar with percentage and status text
  - Log viewer (bottom strip, last 10 transfers)
- Smart folder resolver with ProShop active WO lookup
- ProShop GraphQL OAuth client (token caching, 401 retry)
- Folder memory persistence in SQLite

## [0.2.0] - 2026-03-19

### Added
- FOCAS2 ctypes driver (connect, send, receive, list programs, status)
  - Struct definitions: ODBST, PRGDIR2, ODBUP, IODBPSD, ODBSYS
  - EW_REJECT retry (3x with 5s delay for FocasMonitor conflicts)
  - Safety: dwnend3/upend always called in finally blocks
- Haas CHC SSH/SCP driver via Pi Zero bridge
  - Pre-copy/post-copy script execution with nested try/finally
  - SSH connect retry (3x on Pi Zero slow boot)
- SQLite audit log (transfers, folder memory, preferences)
  - WAL mode, busy_timeout=5000
- Haas NGC SMB stub driver
- Serial DNC stub driver
- Transfer service orchestrator (driver selection, timing, logging)
- Background status checker (30s interval, daemon thread)
- 72 unit tests (all passing)

## [0.1.0] - 2026-03-19

### Added
- Project scaffold with directory structure
- Machine configuration (machines.json)
- Base driver ABC (TransferDriver)
- Machine and TransferResult data models
- Constants and config loader
