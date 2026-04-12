"""
Tool Inventory Sync -- Push kiosk cabinet counts to ProShop
===========================================================
Reads physical inventory counts from tooling.db (recorded via kiosk
inventory sessions), queries RTA tool assignments from ProShop, and
pushes corrected quantities to ProShop via the GraphQL API.

Ground truth = cabinet count (kiosk DB) + RTA count (ProShop query).
ProShop's own totals inflate over time because tools are rarely retired
but purchases auto-add. This script corrects that drift.

Qty mapping:
  - qtyInBin      = cabinet blue + green (usable tools in cabinet)
  - quantity       = cabinet (all colors) + tools in RTAs (total in shop)
  - purchasingNotes = yellow/red condition counts with date

Runs during off-hours only (18:00-05:00 weekdays, all day weekends).

Usage:
  python inventory_sync.py                  (single run)
  python inventory_sync.py --dry-run        (log only, no ProShop writes)
  python inventory_sync.py --loop 3600      (loop every 3600s)
  python inventory_sync.py --loop 3600 --dry-run
"""

import sqlite3
import re
import time
import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

# -- Configuration ------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPT_DIR))

# -- Load .traxis.env credentials ---------------------------------------------
_projects_dir = _SCRIPT_DIR.parent.parent
_home = Path.home()
_env_paths = [
    _home / ".traxis.env",
    _projects_dir / "1. Proshop Automations" / ".traxis.env",
    _projects_dir / "Keys" / ".traxis.env",
]
for _sub in [
    os.path.join("MACHINE COMM Traxis", "Proshop Automation and Claude Projects", "1. Proshop Automations"),
    os.path.join("MACHINE COMM Traxis", "Keys"),
]:
    _env_paths.append(_home / "Dropbox" / _sub / ".traxis.env")
    for _drive in "CDEFG":
        _env_paths.append(Path(f"{_drive}:\\Dropbox") / _sub / ".traxis.env")
for _ep in _env_paths:
    if _ep.exists():
        with open(_ep) as _f:
            for _line in _f:
                _line = _line.strip()
                if "=" in _line and not _line.startswith("#"):
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
        break

import config
from proshop_client import ProShopClient

TOOLING_DB = config.TOOLING_DB_PATH
DRY_RUN = "--dry-run" in sys.argv

BH_START = (5, 15)   # Business hours start (matches Overseer)
BH_END = (18, 0)     # Business hours end

# -- Logging -------------------------------------------------------------------

_log_dir = _SCRIPT_DIR / "data" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
LOG_FILE = str(_log_dir / "inventory_sync.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("inventory_sync")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- Off-hours Gate ------------------------------------------------------------

def _is_off_hours():
    """Return True if current local time is outside business hours or weekend."""
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 6=Sun
    if weekday >= 5:
        return True
    hour_min = (now.hour, now.minute)
    return hour_min >= BH_END or hour_min < BH_START


# -- Sync Log Table ------------------------------------------------------------

def _get_conn():
    conn = sqlite3.connect(TOOLING_DB, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_sync_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sync_log (
            tool_number       TEXT PRIMARY KEY,
            qty_pushed        INTEGER NOT NULL,
            pushed_at         TEXT NOT NULL,
            source_counted_at TEXT NOT NULL
        )
    """)
    conn.commit()


def get_sync_log(conn):
    """Load sync state as dict: tool_number -> {qty_pushed, pushed_at, source_counted_at}."""
    rows = conn.execute("SELECT * FROM inventory_sync_log").fetchall()
    return {r["tool_number"]: dict(r) for r in rows}


def upsert_sync_log(conn, tool_number, qty, counted_at):
    now = _now()
    conn.execute("""
        INSERT INTO inventory_sync_log (tool_number, qty_pushed, pushed_at, source_counted_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(tool_number) DO UPDATE SET
            qty_pushed = excluded.qty_pushed,
            pushed_at = excluded.pushed_at,
            source_counted_at = excluded.source_counted_at
    """, (tool_number, qty, now, counted_at))
    conn.commit()


# -- In-Use Tool Queries -------------------------------------------------------

def fetch_rta_tool_counts(client):
    """Query all RTAs from ProShop and count tools by tool number.

    Each RTA holds one cutting tool. Returns a Counter: tool_number -> count.
    """
    result = client._execute("""
        query {
            rtas(pageSize: 500) {
                records {
                    rtaNumber
                    tool { toolNumber }
                }
                totalRecords
            }
        }
    """)
    records = result.get("data", {}).get("rtas", {}).get("records", [])
    total = result.get("data", {}).get("rtas", {}).get("totalRecords", 0)

    rta_counts = Counter()
    for rta in records:
        tool = rta.get("tool")
        if tool and tool.get("toolNumber"):
            rta_counts[tool["toolNumber"]] += 1

    log.info("RTAs: %d fetched (%d total), %d unique tool numbers",
             len(records), total, len(rta_counts))
    return rta_counts


def fetch_work_cell_tool_counts(client):
    """Query all work cell pockets and count tools by tool number.

    Some tools are loaded directly in machine pockets without an RTA
    (e.g., taps, drills). Returns a Counter: tool_number -> count.
    """
    # Get all work cells
    result = client._execute("""
        query {
            workCells(pageSize: 50) {
                records { potId numberOfPockets }
            }
        }
    """)
    work_cells = result.get("data", {}).get("workCells", {}).get("records", [])
    # Only query machines that have pockets
    machines = [wc for wc in work_cells if (wc.get("numberOfPockets") or 0) > 0]

    wc_counts = Counter()
    errors = 0
    for wc in machines:
        pid = wc["potId"]
        try:
            data = client.get_work_cell_pockets(pid)
            if data and data.get("pockets"):
                for p in data["pockets"].get("records", []):
                    tn = (p.get("toolPlainText") or "").strip()
                    if tn:
                        wc_counts[tn] += 1
        except Exception as e:
            errors += 1
            log.debug("Work cell %s pocket query failed: %s", pid, e)

    log.info("Work cells: %d queried (%d errors), %d tools, %d unique",
             len(machines), errors, sum(wc_counts.values()), len(wc_counts))
    return wc_counts


def fetch_in_use_counts(client):
    """Get total in-use count per tool by combining RTAs and work cell pockets.

    Uses max(rta_count, wc_count) per tool to avoid double-counting:
    - Tool in RTA that's in a work cell: appears in both -> max = correct
    - Tool in RTA on shelf (not in machine): appears in RTA only -> correct
    - Tool directly in work cell (no RTA): appears in WC only -> correct
    """
    rta_counts = fetch_rta_tool_counts(client)
    wc_counts = fetch_work_cell_tool_counts(client)

    all_tools = set(rta_counts.keys()) | set(wc_counts.keys())
    in_use = Counter()
    for tn in all_tools:
        in_use[tn] = max(rta_counts.get(tn, 0), wc_counts.get(tn, 0))

    log.info("Combined in-use: %d tools across %d unique numbers",
             sum(in_use.values()), len(in_use))
    return in_use


# -- Notes Handling ------------------------------------------------------------

_KIOSK_LINE_RE = re.compile(r"\[Kiosk [^\]]*\].*", re.IGNORECASE)


def build_notes(existing_notes, yellow, red, count_date):
    """Build updated purchasingNotes with kiosk condition data.

    Replaces any prior [Kiosk ...] line. Preserves other notes content.
    Returns None if no change needed (no yellow/red and no prior kiosk line).
    """
    existing = (existing_notes or "").strip()

    parts = []
    if yellow > 0:
        parts.append(f"{yellow} worn")
    if red > 0:
        parts.append(f"{red} replace")
    kiosk_line = f"[Kiosk {count_date}] {', '.join(parts)}" if parts else ""

    cleaned = _KIOSK_LINE_RE.sub("", existing).strip()

    if not kiosk_line and not cleaned:
        return None
    if not kiosk_line:
        if existing != cleaned:
            return cleaned
        return None
    if cleaned:
        return f"{cleaned}\n{kiosk_line}"
    return kiosk_line


# -- Main Sync ----------------------------------------------------------------

def sync_inventory():
    """Run one sync cycle: read kiosk DB + RTAs, compute truth, push to ProShop."""
    if not _is_off_hours():
        log.info("Business hours -- skipping sync")
        return

    if DRY_RUN:
        log.info("=== DRY RUN MODE -- no ProShop updates will be made ===")

    conn = _get_conn()
    init_sync_table(conn)

    # 1. Load all cabinet inventory from kiosk DB
    from database import list_inventory
    items = list_inventory(conn)
    sync_log = get_sync_log(conn)

    # 2. Filter to items needing evaluation (new counts since last sync)
    candidates = []
    for item in items:
        counted_at = item.get("last_counted_at")
        if not counted_at:
            continue
        prev = sync_log.get(item["tool_number"])
        if prev and prev["source_counted_at"] >= counted_at:
            continue
        candidates.append(item)

    if not candidates:
        log.info("No new counts to sync")
        conn.close()
        return

    log.info("%d items need sync evaluation", len(candidates))

    # 3. Connect to ProShop
    client = ProShopClient(
        graphql_url=config.PROSHOP_GRAPHQL_URL,
        token_url=config.PROSHOP_TOKEN_URL,
        client_id=config.PROSHOP_CLIENT_ID,
        client_secret=config.PROSHOP_CLIENT_SECRET,
        scope=config.PROSHOP_SCOPE,
    )

    # 4. Fetch ProShop tool library (qty + notes)
    #    Use longer timeout — ProShop can be slow with 900+ tools
    import requests as _requests
    _orig_timeout = 30
    try:
        result = client._execute("""
            query ($pageSize: Int!) {
                tools(pageSize: $pageSize) {
                    records { toolNumber quantity qtyAvailable purchasingNotes }
                    totalRecords
                }
            }
        """, {"pageSize": 2000})
    except _requests.exceptions.ReadTimeout:
        log.warning("ProShop tool fetch timed out -- retrying with longer timeout")
        # Monkey-patch timeout for retry (proshop_client uses 30s default)
        _orig_post = _requests.post
        def _patched_post(*a, **kw):
            kw["timeout"] = 90
            return _orig_post(*a, **kw)
        _requests.post = _patched_post
        try:
            result = client._execute("""
                query ($pageSize: Int!) {
                    tools(pageSize: $pageSize) {
                        records { toolNumber quantity qtyAvailable purchasingNotes }
                        totalRecords
                    }
                }
            """, {"pageSize": 2000})
        finally:
            _requests.post = _orig_post

    ps_records = result.get("data", {}).get("tools", {}).get("records", [])
    ps_lookup = {t["toolNumber"]: t for t in ps_records}
    log.info("Fetched %d tools from ProShop", len(ps_lookup))

    # 5. Fetch in-use tool counts (RTAs + work cell pockets)
    in_use_counts = fetch_in_use_counts(client)

    # 6. Evaluate and push
    updated = 0
    skipped = 0
    errors = 0
    not_in_proshop = 0
    notes_updated = 0

    for item in candidates:
        tn = item["tool_number"]
        cabinet_available = item["qty_available"]   # blue + green (usable)
        cabinet_total = item["qty_total"]           # all colors in cabinet
        yellow = item["qty_yellow"]
        red = item["qty_red"]
        counted_at = item["last_counted_at"]
        count_date = counted_at[:10] if counted_at else ""

        ps_tool = ps_lookup.get(tn)
        if not ps_tool:
            not_in_proshop += 1
            log.debug("Tool %s not found in ProShop -- skipping", tn)
            if not DRY_RUN:
                upsert_sync_log(conn, tn, cabinet_available, counted_at)
            continue

        # Current ProShop values
        ps_quantity = ps_tool.get("quantity") or 0
        try:
            ps_quantity = int(float(ps_quantity))
        except (ValueError, TypeError):
            ps_quantity = 0

        # Ground truth: cabinet (all colors) + in-use (RTAs/work cells) = actual total
        in_use = in_use_counts.get(tn, 0)
        true_total = cabinet_total + in_use
        true_bin = cabinet_available  # usable tools in the cabinet

        # Build update payload -- always push the corrected values
        update_data = {}
        action_parts = []

        # Update qtyInBin if it differs (we can't read it, so always set it)
        update_data["qtyInBin"] = str(true_bin)
        action_parts.append(f"bin={true_bin}")

        # Update quantity (total in shop) if it differs from truth
        if true_total != ps_quantity:
            update_data["quantity"] = float(true_total)
            action_parts.append(f"total {ps_quantity} -> {true_total}")
            if in_use:
                action_parts.append(f"(cab={cabinet_total}+use={in_use})")

        # Handle notes (yellow/red condition data)
        existing_notes = ps_tool.get("purchasingNotes") or ""
        new_notes = build_notes(existing_notes, yellow, red, count_date)
        if new_notes is not None and new_notes != existing_notes:
            update_data["purchasingNotes"] = new_notes
            action_parts.append("notes")
            notes_updated += 1

        if DRY_RUN:
            log.info("DRY RUN  %s: %s", tn, ", ".join(action_parts))
            updated += 1
        else:
            try:
                client.update_tool(tn, update_data)
                upsert_sync_log(conn, tn, true_bin, counted_at)
                log.info("UPDATED  %s: %s", tn, ", ".join(action_parts))
                updated += 1
                time.sleep(0.1)  # Throttle API calls
            except Exception as e:
                log.error("FAILED   %s: %s", tn, e)
                errors += 1

    conn.close()
    log.info("Sync complete: %d updated, %d skipped, %d notes, "
             "%d not in ProShop, %d errors",
             updated, skipped, notes_updated, not_in_proshop, errors)


# -- Entry Point ---------------------------------------------------------------

def main():
    log.info("Tooling DB: %s", TOOLING_DB)
    log.info("Dry run: %s", DRY_RUN)

    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 3600
        log.info("Running in loop mode, interval=%ds", interval)
        while True:
            try:
                sync_inventory()
            except Exception as e:
                log.error("Sync cycle failed: %s", e, exc_info=True)
            time.sleep(interval)
    else:
        sync_inventory()


if __name__ == "__main__":
    main()
