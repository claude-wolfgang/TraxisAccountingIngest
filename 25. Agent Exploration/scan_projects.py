"""
Nightly project index scanner.

Reads CLAUDE.md / README.md from each project folder, uses Claude Haiku
to extract current status and blockers, and updates project_index.json.

Runs via Task Scheduler at midnight.

Usage:
    python scan_projects.py              # Full scan, update index
    python scan_projects.py --dry-run    # Scan but don't write
    python scan_projects.py --project 12 # Scan one project only
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

import config

# -- Paths -------------------------------------------------------------------

PROJECTS_ROOT = Path(__file__).parent.parent  # .../Proshop Automation and Claude Projects/
INDEX_PATH = Path(__file__).parent / "project_index.json"

# Project folders in order (number -> folder name pattern)
# We discover them dynamically from the filesystem.


MASTER_SESSION_LOG = PROJECTS_ROOT / "main_session_log.md"
ECOSYSTEM_PATH = PROJECTS_ROOT / "TRAXIS_ECOSYSTEM.md"
# Claude Code memory can be on C: or D: (collector machine uses D:)
CLAUDE_MEMORY_ROOTS = [
    Path.home() / ".claude" / "projects",
    Path("D:/Users") / os.environ.get("USERNAME", "") / ".claude" / "projects",
]


def find_project_folders():
    """Find all numbered project folders (e.g. '1. Proshop Automations')."""
    folders = {}
    for entry in PROJECTS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        # Match "N. Name" or "NN. Name" pattern
        parts = name.split(". ", 1)
        if len(parts) == 2:
            try:
                num = int(parts[0])
                folders[num] = entry
            except ValueError:
                continue
    return dict(sorted(folders.items()))


def get_latest_session_entries(project_id):
    """Extract the most recent session log entries for a project from the master log."""
    if not MASTER_SESSION_LOG.exists():
        return None
    try:
        text = MASTER_SESSION_LOG.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Find sections mentioning this project (e.g. "Project 12:" or "Project 12 ")
    marker = f"Project {project_id}"
    lines = text.split("\n")
    entries = []
    current_entry = []
    capturing = False
    current_date = ""

    for line in lines:
        # Track date headers
        if line.startswith("## 20"):
            current_date = line.strip("# ").strip()

        # Start capturing when we find a section for this project
        if marker in line and line.startswith("###"):
            if current_entry:
                entries.append("\n".join(current_entry))
            current_entry = [f"[{current_date}] {line}"]
            capturing = True
        elif capturing:
            # Stop at the next section header
            if line.startswith("### ") or line.startswith("## 20"):
                entries.append("\n".join(current_entry))
                current_entry = []
                capturing = False
            else:
                current_entry.append(line)

    if current_entry:
        entries.append("\n".join(current_entry))

    if not entries:
        return None

    # Return the last 2 entries (most recent activity), capped at 2000 chars
    recent = "\n\n---\n\n".join(entries[-2:])
    if len(recent) > 2000:
        recent = recent[:2000] + "\n... (truncated)"
    return recent


def get_claude_memory(project_id, folder_name):
    """Read Claude Code MEMORY.md for a project if it exists."""
    target = folder_name.replace(" ", "-")
    for root in CLAUDE_MEMORY_ROOTS:
        if not root.exists():
            continue
        for d in root.iterdir():
            if not d.is_dir():
                continue
            if target.lower() in d.name.lower() or f"-{project_id}--" in d.name:
                memory_file = d / "memory" / "MEMORY.md"
                if memory_file.exists():
                    try:
                        text = memory_file.read_text(encoding="utf-8", errors="replace")
                        if len(text) > 2000:
                            text = text[:2000] + "\n... (truncated)"
                        return text
                    except Exception:
                        continue
    return None


def _read_capped(path, cap=4000):
    """Read a file, capped at N chars."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > cap:
        text = text[:cap] + "\n... (truncated)"
    return text


def parse_interface_block(folder):
    """Parse ## Interfaces section from a project's CLAUDE.md.

    Returns dict with 'produces', 'consumes', 'contracts' lists,
    or None if no CLAUDE.md or no ## Interfaces section.
    """
    claude_md = folder / "CLAUDE.md"
    if not claude_md.exists():
        return None
    try:
        text = claude_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Find ## Interfaces section
    lines = text.split("\n")
    in_section = False
    interfaces = {"produces": [], "consumes": [], "contracts": []}

    for line in lines:
        stripped = line.strip()
        # Detect start of Interfaces section
        if stripped.startswith("## Interfaces"):
            in_section = True
            continue
        # Stop at the next ## heading
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        # Parse Produces/Consumes/Contracts lines
        low = stripped.lower()
        for field in ("produces", "consumes", "contracts"):
            if low.startswith(f"{field}:"):
                value = stripped[len(field) + 1:].strip()
                if value:
                    interfaces[field] = [v.strip() for v in value.split(",")]
                break

    if not any(interfaces.values()):
        return None
    return interfaces


def read_project_docs(folder, project_id=None):
    """Read key documentation files from a project folder. Returns combined text."""
    docs = []

    # 1. Primary docs: CLAUDE.md, README.md
    for name in ["CLAUDE.md", "README.md"]:
        path = folder / name
        if path.exists():
            try:
                docs.append(f"=== {name} ===\n{_read_capped(path)}")
            except Exception:
                continue

    # If no CLAUDE.md or README.md, check for any .md file
    if not docs:
        for md in sorted(folder.glob("*.md"))[:2]:
            try:
                docs.append(f"=== {md.name} ===\n{_read_capped(md)}")
            except Exception:
                continue

    # 2. RETIRED.md
    retired_path = folder / "RETIRED.md"
    if retired_path.exists():
        docs.append("=== RETIRED.md exists ===")

    # 3. Session logs (per-project) -- search recursively
    for sl in sorted(folder.rglob("session_log.md"))[:2]:
        try:
            docs.append(f"=== {sl.relative_to(folder)} (session log) ===\n{_read_capped(sl, 2000)}")
        except Exception:
            continue

    # 4. Master session log -- latest entries for this project
    if project_id is not None:
        session_text = get_latest_session_entries(project_id)
        if session_text:
            docs.append(f"=== Master SESSION_LOG.md (recent entries) ===\n{session_text}")

    # 5. Claude Code memory
    if project_id is not None:
        memory_text = get_claude_memory(project_id, folder.name)
        if memory_text:
            docs.append(f"=== Claude Code MEMORY.md ===\n{memory_text}")

    # 6. Recent file activity
    try:
        newest = max(
            (f.stat().st_mtime for f in folder.rglob("*.py") if f.is_file()),
            default=0,
        )
        if newest > 0:
            age_days = (time.time() - newest) / 86400
            docs.append(f"=== Most recent .py file modified {age_days:.0f} days ago ===")
    except Exception:
        pass

    return "\n\n".join(docs) if docs else None


def extract_status_with_haiku(client, project_id, project_name, doc_text):
    """Use Claude Haiku to extract structured status from project docs."""
    prompt = f"""Extract the current status of this software project from its documentation.
Return ONLY a JSON object with these fields (no other text):

{{
  "status": "active" or "complete" or "stalled" or "retired" or "investigation",
  "short": "One sentence describing what this project does",
  "waiting_on": "What's currently blocking progress (null if nothing)",
  "needs_from_user": "What the project owner needs to do (null if nothing)"
}}

Rules:
- "active" = being worked on or running in production
- "complete" = finished, no more work planned
- "stalled" = started but paused, waiting on something
- "retired" = replaced or abandoned
- "investigation" = research/planning phase, no code yet
- Keep "short" to ONE sentence, max 20 words
- "waiting_on" should be specific technical blockers
- "needs_from_user" should be physical actions only the owner can take (purchases, phone calls, decisions, hardware tasks)
- If RETIRED.md exists, status is "retired"

Project {project_id}: {project_name}

{doc_text}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  [WARN] P{project_id}: Could not parse Haiku response: {text[:100]}")
        return None


def scan_all(dry_run=False, single_project=None):
    """Scan all projects and update the index."""
    print(f"Traxis Project Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Projects root: {PROJECTS_ROOT}")

    # Load existing index
    if INDEX_PATH.exists():
        with open(INDEX_PATH) as f:
            index = json.load(f)
    else:
        print("ERROR: project_index.json not found. Run initial survey first.")
        sys.exit(1)

    # Build lookup of existing projects
    existing = {p["id"]: p for p in index.get("projects", [])}

    # Find project folders
    folders = find_project_folders()
    print(f"Found {len(folders)} project folders\n")

    # Init Claude client
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    updated = 0
    errors = 0

    for pid, folder in folders.items():
        if single_project is not None and pid != single_project:
            continue

        print(f"P{pid}: {folder.name}")

        doc_text = read_project_docs(folder, project_id=pid)
        if not doc_text:
            print("  [SKIP] No documentation found")
            continue

        try:
            result = extract_status_with_haiku(client, pid, folder.name, doc_text)
        except Exception as e:
            print(f"  [ERROR] Haiku call failed: {e}")
            errors += 1
            continue

        if not result:
            errors += 1
            continue

        # Parse interface block (no Haiku needed — direct text parsing)
        ifaces = parse_interface_block(folder)
        if ifaces:
            result["interfaces"] = ifaces
            print(f"  [IFACE] Parsed: {sum(len(v) for v in ifaces.values())} items")

        # Update existing project entry (preserve static fields, update dynamic)
        if pid in existing:
            proj = existing[pid]
            changed = []

            if result.get("status") and result["status"] != proj.get("status"):
                changed.append(f"status: {proj.get('status')} -> {result['status']}")
                proj["status"] = result["status"]

            if result.get("short") and result["short"] != proj.get("short"):
                changed.append("short description updated")
                proj["short"] = result["short"]

            # Only update waiting_on/needs_from_user if Haiku found something
            # (don't overwrite manually curated values with null)
            if result.get("waiting_on"):
                if result["waiting_on"] != proj.get("waiting_on"):
                    changed.append("waiting_on updated")
                    proj["waiting_on"] = result["waiting_on"]

            if result.get("needs_from_user"):
                if result["needs_from_user"] != proj.get("needs_from_user"):
                    changed.append("needs_from_user updated")
                    proj["needs_from_user"] = result["needs_from_user"]

            # Update interfaces if parsed
            if result.get("interfaces"):
                proj["interfaces"] = result["interfaces"]
                if "interfaces" not in [c.split(":")[0] for c in changed]:
                    changed.append("interfaces updated")

            if changed:
                print(f"  [UPDATED] {', '.join(changed)}")
                updated += 1
            else:
                print(f"  [OK] No changes")
        else:
            # New project not in index -- add it
            new_entry = {
                "id": pid,
                "name": folder.name.split(". ", 1)[1] if ". " in folder.name else folder.name,
                "short": result.get("short", ""),
                "status": result.get("status", "active"),
                "affects": [],
                "waiting_on": result.get("waiting_on"),
                "needs_from_user": result.get("needs_from_user"),
            }
            if result.get("interfaces"):
                new_entry["interfaces"] = result["interfaces"]
            index["projects"].append(new_entry)
            index["projects"].sort(key=lambda p: p["id"])
            print(f"  [NEW] Added to index")
            updated += 1

        # Rate limit: ~1 req/sec to be polite
        time.sleep(0.5)

    # Rebuild action items from updated projects
    action_items = []
    for p in index.get("projects", []):
        if p.get("needs_from_user") and p.get("status") not in ("complete", "retired"):
            action_items.append({
                "project": p["id"],
                "action": p["needs_from_user"],
                "effort": "",
                "impact": "",
            })
    index["action_items_for_wolfgang"] = action_items

    # Update metadata
    index["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")

    print(f"\nSummary: {updated} updated, {errors} errors, {len(folders)} total")

    if dry_run:
        print("[DRY RUN] Not writing changes.")
    else:
        with open(INDEX_PATH, "w") as f:
            json.dump(index, f, indent=2, default=str)
        print(f"Written to {INDEX_PATH}")

        # Render ecosystem constellation file
        render_ecosystem_file(index)

    return updated, errors


def render_ecosystem_file(index):
    """Generate TRAXIS_ECOSYSTEM.md from the project index.

    This is a read artifact — loaded as primer at session start, read by
    the Telegram bot for the daily digest. Never hand-edited.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Traxis Ecosystem Constellation",
        "",
        f"*Auto-generated by scan_projects.py on {now}. Do not hand-edit.*",
        "",
    ]

    projects = index.get("projects", [])
    active = [p for p in projects if p.get("status") not in ("retired", "complete")]
    complete = [p for p in projects if p.get("status") == "complete"]
    retired = [p for p in projects if p.get("status") == "retired"]

    # -- Project Status Overview --
    lines.append("## Project Status")
    lines.append("")
    lines.append(f"**{len(active)} active** | {len(complete)} complete | {len(retired)} retired")
    lines.append("")
    for p in projects:
        status = p.get("status", "?")
        short = p.get("short", "")
        marker = {"active": "+", "complete": "=", "stalled": "~", "retired": "-", "investigation": "?"}.get(status, " ")
        lines.append(f"- [{marker}] **P{p['id']}: {p.get('name', '')}** — {short}")
    lines.append("")

    # -- Interface Table --
    has_ifaces = [p for p in projects if p.get("interfaces")]
    if has_ifaces:
        lines.append("## Interface Map")
        lines.append("")
        lines.append("| Project | Produces | Consumes |")
        lines.append("|---------|----------|----------|")
        for p in has_ifaces:
            ifaces = p["interfaces"]
            produces = ", ".join(ifaces.get("produces", [])) or "—"
            consumes = ", ".join(ifaces.get("consumes", [])) or "—"
            lines.append(f"| P{p['id']}: {p.get('name', '')} | {produces} | {consumes} |")
        lines.append("")

    # -- Critical Seams (Contracts) --
    contracts = []
    for p in projects:
        ifaces = p.get("interfaces", {})
        for c in ifaces.get("contracts", []):
            contracts.append((p["id"], p.get("name", ""), c))

    if contracts:
        lines.append("## Critical Seams")
        lines.append("")
        lines.append("Cross-project contracts — breaking these silently breaks a downstream project.")
        lines.append("")
        for pid, pname, contract in contracts:
            lines.append(f"- **P{pid} ({pname}):** {contract}")
        lines.append("")

    # -- Open Items Requiring Wolfgang --
    action_items = index.get("action_items_for_wolfgang", [])
    if action_items:
        lines.append("## Open Items Requiring Wolfgang")
        lines.append("")
        for item in action_items:
            pid = item.get("project", "?")
            action = item.get("action", "")
            # Find project name
            pname = next((p.get("name", "") for p in projects if p["id"] == pid), "")
            lines.append(f"- **P{pid} ({pname}):** {action}")
        lines.append("")

    text = "\n".join(lines)
    try:
        ECOSYSTEM_PATH.write_text(text, encoding="utf-8")
        print(f"Rendered {ECOSYSTEM_PATH}")
    except Exception as e:
        print(f"[ERROR] Failed to write ecosystem file: {e}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    single = None
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        if idx + 1 < len(sys.argv):
            single = int(sys.argv[idx + 1])

    scan_all(dry_run=dry_run, single_project=single)
