"""
Machine-Specific Tool Frequency Analysis
Extends the global tool frequency analysis by breaking down tool usage per work center (machine).

For each mill, answers: "Which tools appear most often, and how many resident tools
would you need to cover X% of jobs?"

Output:
  machine_tool_frequency_report.txt  — Human-readable per-machine breakdown
  machine_tool_frequency_data.json   — Raw data for further analysis

Requires: requests (pip install requests)
"""

import requests
import time
import json
import os
from datetime import datetime
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# --- Config ---
BASE_URL = "https://traxismfg.adionsystems.com"
TOKEN_URL = f"{BASE_URL}/home/member/oauth/accesstoken"
GRAPHQL_URL = f"{BASE_URL}/api/graphql"

OUTPUT_DIR = Path(__file__).parent

ENV_PATH = Path(r"C:\Users\AbsoluteArm\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")

# Mills to analyze (ProShop work center names)
MILL_NAMES = {"Mill-1", "Mill-2", "Mill-3", "Mill-4", "Mill-5", "Mill-6", "Mill-7", "Mill-8"}
# Also capture lathe for completeness
LATHE_NAMES = {"T2"}
ALL_MACHINES = MILL_NAMES | LATHE_NAMES


def load_env():
    creds = {}
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                creds[key.strip()] = value.strip()
    return creds


def get_token(session, creds):
    resp = session.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": creds["PROSHOP_CLIENT_ID"],
        "client_secret": creds["PROSHOP_CLIENT_SECRET"],
        "scope": creds["PROSHOP_SCOPE"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def graphql(session, token, query, variables=None):
    resp = session.post(GRAPHQL_URL, json={
        "query": query,
        "variables": variables or {}
    }, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    if "errors" in result:
        errs = result["errors"]
        # Only print if no data returned (partial results are OK)
        if not result.get("data"):
            print(f"  GraphQL errors: {errs}")
    return result.get("data")


# --- Queries ---

WO_QUERY = """
query($year: String!) {
  workOrders(filter: { year: $year }, pageSize: 500) {
    totalRecords
    records {
      workOrderNumber
      status
      quantityOrdered
      dueDate
      part {
        partNumber
        partName
      }
    }
  }
}
"""

# Per-WO query: get ops with work center + tools from part operation
WO_OPS_TOOLS_QUERY = """
query ($woNum: String!) {
  workOrder(workOrderNumber: $woNum) {
    workOrderNumber
    quantityOrdered
    part { partNumber partName }
    ops {
      records {
        operationNumber
        operationDescription
        workCenterPlainText
        partOperation {
          tools(pageSize: 50) {
            records {
              toolPlainText
              holder
              outOfHolder
              tool { toolNumber description toolGroupLetter }
            }
          }
        }
      }
    }
  }
}
"""

# Machine pocket layout
POCKETS_QUERY = """
query ($potId: String!) {
  workCell(potId: $potId) {
    potId
    commonName
    numberOfPockets
    pockets(pageSize: 100) {
      records {
        legacyId
        toolPlainText
        outOfHolder
        holder
      }
    }
  }
}
"""

WORK_CELLS_QUERY = """
query {
  workCells(pageSize: 50) {
    records {
      commonName potId potType isScheduledResource numberOfPockets
    }
  }
}
"""

# Tool master for descriptions
TOOLS_MASTER_QUERY = """
{
  tools(pageSize: 500) {
    totalRecords
    records {
      toolNumber description toolGroupLetter bodyDiameter ansiCatalogNumber
    }
  }
}
"""


def fetch_wo_ops_tools(session, token, wo_number):
    """Fetch operations + tools for a single WO. Returns parsed data or None."""
    try:
        data = graphql(session, token, WO_OPS_TOOLS_QUERY, {"woNum": wo_number})
        if data and data.get("workOrder"):
            return data["workOrder"]
    except Exception as e:
        print(f"  Error fetching {wo_number}: {e}")
    return None


def dehyphenate(tool_id):
    """Remove hyphens from tool IDs like A-1 → A1, B-267 → B267, O-17 → O17.
    Also strips 'CRIB ' prefix (e.g. 'CRIB A-61' → 'A61')."""
    import re
    s = tool_id.strip()
    # Strip "CRIB " prefix
    if s.upper().startswith("CRIB "):
        s = s[5:].strip()
    # Remove hyphen between letter(s) and digits: A-1 → A1, TO-310 → TO310
    s = re.sub(r'^([A-Za-z]+)-(\d+.*)$', r'\1\2', s)
    return s


def normalize_tool_id(raw_id, tool_master):
    """Normalize a tool ID to its canonical form using the tool master."""
    raw_id = raw_id.strip()
    if not raw_id:
        return None

    # First try as-is
    if raw_id in tool_master:
        return raw_id

    # Dehyphenate: A-1 → A1, CRIB L-18 → L18
    dehyph = dehyphenate(raw_id)

    # Try dehyphenated form
    if dehyph in tool_master:
        return dehyph
    dehyph_upper = dehyph.upper()
    if dehyph_upper in tool_master:
        return dehyph_upper

    # Case-insensitive search against master
    for mk in tool_master:
        if mk.upper() == dehyph_upper:
            return mk

    # Not in master — return dehyphenated uppercase
    return dehyph_upper if dehyph_upper != raw_id else raw_id.upper()


def main():
    print("=" * 80)
    print("MACHINE-SPECIFIC TOOL FREQUENCY ANALYSIS")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Analysis window: 2024-2026 (past 2+ years)")
    print("=" * 80)

    creds = load_env()
    session = requests.Session()
    token = get_token(session, creds)
    print("Authenticated with ProShop API")

    # --- Step 1: Fetch tool master ---
    print("\n--- Fetching Tool Master ---")
    tool_master = {}
    data = graphql(session, token, TOOLS_MASTER_QUERY)
    if data and "tools" in data:
        for t in data["tools"].get("records", []):
            tn = t.get("toolNumber", "")
            if tn:
                tool_master[tn] = {
                    "description": t.get("description", ""),
                    "group": t.get("toolGroupLetter", ""),
                    "diameter": t.get("bodyDiameter", ""),
                    "catalog": t.get("ansiCatalogNumber", ""),
                }
        print(f"  {len(tool_master)} tools in master")

    # --- Step 2: Fetch work cells + pocket layouts ---
    print("\n--- Fetching Work Cells & Pocket Layouts ---")
    data = graphql(session, token, WORK_CELLS_QUERY)
    work_cells = {}
    if data and "workCells" in data:
        for wc in data["workCells"].get("records", []):
            pot_id = wc.get("potId", "")
            if pot_id in ALL_MACHINES:
                work_cells[pot_id] = {
                    "potId": pot_id,
                    "commonName": wc.get("commonName", ""),
                    "numberOfPockets": wc.get("numberOfPockets", 0),
                    "type": wc.get("potType", ""),
                }
    print(f"  Found {len(work_cells)} active machines: {sorted(work_cells.keys())}")

    # Fetch pocket layouts for each machine
    pocket_layouts = {}
    for name, wc in work_cells.items():
        pot_id = wc["potId"]
        if not pot_id:
            continue
        data = graphql(session, token, POCKETS_QUERY, {"potId": pot_id})
        if data and data.get("workCell"):
            wc_data = data["workCell"]
            pockets = wc_data.get("pockets", {}).get("records", [])
            loaded = []
            for p in pockets:
                tool_text = (p.get("toolPlainText") or "").strip()
                if tool_text:
                    loaded.append({
                        "pocket": p.get("legacyId"),
                        "tool": tool_text,
                        "holder": (p.get("holder") or "").strip(),
                        "ooh": p.get("outOfHolder"),
                    })
            pocket_layouts[name] = {
                "total_pockets": wc_data.get("numberOfPockets", 0),
                "loaded_count": len(loaded),
                "tools": loaded,
            }
            print(f"  {name}: {len(loaded)} tools loaded / {wc_data.get('numberOfPockets', '?')} pockets")
        time.sleep(0.2)

    # --- Step 3: Fetch all WOs ---
    print("\n--- Fetching Work Orders (2024-2026) ---")
    all_wos = []
    for year in ["2024", "2025", "2026"]:
        data = graphql(session, token, WO_QUERY, {"year": year})
        if data and "workOrders" in data:
            records = data["workOrders"].get("records", [])
            total = data["workOrders"].get("totalRecords", 0)
            print(f"  {year}: {len(records)} fetched / {total} total")
            all_wos.extend(records)
        time.sleep(0.3)

    # Build WO index
    wo_numbers = [wo["workOrderNumber"] for wo in all_wos if wo.get("workOrderNumber")]
    print(f"  Total: {len(wo_numbers)} work orders")

    # --- Step 4: Fetch ops+tools per WO (threaded) ---
    print(f"\n--- Fetching Operations & Tools for {len(wo_numbers)} WOs (threaded) ---")

    wo_details = {}
    errors = 0
    completed = 0

    def fetch_one(wo_num):
        return wo_num, fetch_wo_ops_tools(session, token, wo_num)

    # Use 5 threads to avoid hammering the API
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_one, wn): wn for wn in wo_numbers}
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"  Progress: {completed}/{len(wo_numbers)} WOs fetched...")
            try:
                wo_num, detail = future.result()
                if detail:
                    wo_details[wo_num] = detail
                else:
                    errors += 1
            except Exception as e:
                errors += 1

    print(f"  Fetched {len(wo_details)} WOs successfully, {errors} errors")

    # --- Step 5: Analyze per-machine tool frequency ---
    print("\n--- Analyzing Per-Machine Tool Frequency ---")

    # Structure: machine -> tool_id -> {parts, wos, qty, appearances, ops, holders}
    machine_tools = defaultdict(lambda: defaultdict(lambda: {
        "parts": set(),
        "wos": set(),
        "qty": 0,
        "appearances": 0,
        "ops": set(),
        "holders": set(),
    }))

    # Also track per-machine WO counts for coverage calculation
    machine_wo_count = Counter()    # machine -> total WOs assigned to it
    machine_part_count = defaultdict(set)  # machine -> set of part numbers

    # Track tools found via WO ops (for the tool master enrichment)
    skipped_non_machine = 0
    ops_with_tools = 0
    ops_without_tools = 0

    for wo_num, detail in wo_details.items():
        part = detail.get("part") or {}
        part_num = part.get("partNumber", "")
        qty = detail.get("quantityOrdered", 0) or 0
        if isinstance(qty, str):
            try:
                qty = int(qty)
            except ValueError:
                qty = 0

        ops = (detail.get("ops") or {}).get("records", [])
        for op in ops:
            wc = (op.get("workCenterPlainText") or "").strip()
            if wc not in ALL_MACHINES:
                skipped_non_machine += 1
                continue

            machine_wo_count[wc] += 1  # count each op as an "assignment"
            if part_num:
                machine_part_count[wc].add(part_num)

            # Get tools from partOperation
            part_op = op.get("partOperation") or {}
            tools_data = part_op.get("tools")
            if not tools_data:
                ops_without_tools += 1
                continue

            tool_records = tools_data.get("records", [])
            if not tool_records:
                ops_without_tools += 1
                continue

            ops_with_tools += 1
            op_desc = (op.get("operationDescription") or "").strip()

            for trec in tool_records:
                # Extract tool ID
                tool_id = (trec.get("toolPlainText") or "").strip()
                if not tool_id:
                    tool_obj = trec.get("tool")
                    if tool_obj:
                        tool_id = (tool_obj.get("toolNumber") or "").strip()
                if not tool_id:
                    continue

                tool_id = normalize_tool_id(tool_id, tool_master)
                if not tool_id:
                    continue

                # Enrich tool master from nested tool object
                tool_obj = trec.get("tool")
                if tool_obj and tool_id not in tool_master:
                    desc = tool_obj.get("description", "")
                    if desc:
                        tool_master[tool_id] = {
                            "description": desc,
                            "group": tool_obj.get("toolGroupLetter", ""),
                            "diameter": "",
                            "catalog": "",
                        }

                entry = machine_tools[wc][tool_id]
                if part_num:
                    entry["parts"].add(part_num)
                entry["wos"].add(wo_num)
                entry["qty"] += qty
                entry["appearances"] += 1
                if op_desc:
                    entry["ops"].add(op_desc)
                holder = (trec.get("holder") or "").strip()
                if holder:
                    entry["holders"].add(holder)

    print(f"  Ops on machines with tools: {ops_with_tools}")
    print(f"  Ops on machines without tools: {ops_without_tools}")
    print(f"  Ops on non-machine work centers (skipped): {skipped_non_machine}")
    print(f"  Machines with data: {sorted(machine_tools.keys())}")

    # --- Step 6: Build per-machine rankings + Pareto ---
    machine_rankings = {}
    for machine in sorted(machine_tools.keys()):
        tools = machine_tools[machine]
        ranked = sorted(
            tools.keys(),
            key=lambda t: (len(tools[t]["parts"]), len(tools[t]["wos"]), tools[t]["appearances"]),
            reverse=True
        )
        total_wos_on_machine = len(set().union(*(tools[t]["wos"] for t in tools)))
        total_parts_on_machine = len(set().union(*(tools[t]["parts"] for t in tools)))

        # Build Pareto: how many tools to cover X% of WOs?
        # A WO is "covered" if ALL its tools are in the resident set
        # But simpler metric: what % of WOs use this tool?
        pareto = []
        wos_covered = set()
        for i, tool_id in enumerate(ranked, 1):
            wos_covered |= tools[tool_id]["wos"]
            coverage = len(wos_covered) / total_wos_on_machine * 100 if total_wos_on_machine else 0
            pareto.append({
                "rank": i,
                "tool_id": tool_id,
                "description": tool_master.get(tool_id, {}).get("description", ""),
                "part_count": len(tools[tool_id]["parts"]),
                "wo_count": len(tools[tool_id]["wos"]),
                "wo_qty": tools[tool_id]["qty"],
                "appearances": tools[tool_id]["appearances"],
                "cumulative_wo_coverage_pct": round(coverage, 1),
            })

        machine_rankings[machine] = {
            "total_unique_tools": len(tools),
            "total_wos": total_wos_on_machine,
            "total_parts": total_parts_on_machine,
            "ranking": pareto,
        }

    # --- Step 7: Generate report ---
    print("\n--- Generating Report ---")
    lines = []
    lines.append("=" * 100)
    lines.append("MACHINE-SPECIFIC TOOL FREQUENCY ANALYSIS")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Analysis Period: 2024 - 2026")
    lines.append(f"Data Source: ProShop API — WO Operations + Part Sequence Details")
    lines.append("=" * 100)

    lines.append(f"\nOVERALL SUMMARY")
    lines.append(f"  Work Orders analyzed: {len(wo_details)}")
    lines.append(f"  Machines found: {len(machine_rankings)}")
    lines.append(f"  Tool master records: {len(tool_master)}")

    lines.append(f"\nMACHINE OVERVIEW")
    lines.append(f"  {'Machine':<12} {'Pockets':<9} {'Loaded':<8} {'WOs':<7} {'Parts':<7} {'Unique Tools':<13} {'Top5 Cover%'}")
    lines.append(f"  {'-'*12} {'-'*9} {'-'*8} {'-'*7} {'-'*7} {'-'*13} {'-'*12}")
    for machine in sorted(machine_rankings.keys()):
        mr = machine_rankings[machine]
        pl = pocket_layouts.get(machine, {})
        top5_cov = ""
        if mr["ranking"] and len(mr["ranking"]) >= 5:
            top5_cov = f"{mr['ranking'][4]['cumulative_wo_coverage_pct']}%"
        elif mr["ranking"]:
            top5_cov = f"{mr['ranking'][-1]['cumulative_wo_coverage_pct']}%"
        lines.append(
            f"  {machine:<12} {pl.get('total_pockets', '?'):<9} "
            f"{pl.get('loaded_count', '?'):<8} {mr['total_wos']:<7} "
            f"{mr['total_parts']:<7} {mr['total_unique_tools']:<13} {top5_cov}"
        )

    # Per-machine detailed sections
    for machine in sorted(machine_rankings.keys()):
        mr = machine_rankings[machine]
        pl = pocket_layouts.get(machine, {})

        lines.append(f"\n{'=' * 100}")
        lines.append(f"  {machine}")
        lines.append(f"  Pockets: {pl.get('total_pockets', '?')} total, {pl.get('loaded_count', '?')} currently loaded")
        lines.append(f"  WOs: {mr['total_wos']}  |  Parts: {mr['total_parts']}  |  Unique tools: {mr['total_unique_tools']}")
        lines.append(f"{'=' * 100}")

        # Current pocket contents
        if pl.get("tools"):
            lines.append(f"\n  CURRENT POCKET CONTENTS:")
            lines.append(f"  {'Pocket':<8} {'Tool ID':<15} {'Holder':<15} {'OOH'}")
            lines.append(f"  {'-'*8} {'-'*15} {'-'*15} {'-'*8}")
            for p in sorted(pl["tools"], key=lambda x: x.get("pocket") or 0):
                lines.append(
                    f"  {str(p.get('pocket', '?')):<8} {p['tool']:<15} "
                    f"{p.get('holder', ''):<15} {p.get('ooh', '')}"
                )

        # Tool frequency ranking
        lines.append(f"\n  TOOL FREQUENCY RANKING (by # of parts using tool on this machine):")
        lines.append(f"  {'Rank':<5} {'Tool #':<16} {'Parts':<7} {'WOs':<7} {'Cum%':<7} {'Description'}")
        lines.append(f"  {'-'*5} {'-'*16} {'-'*7} {'-'*7} {'-'*7} {'-'*45}")

        for entry in mr["ranking"][:60]:  # Top 60 per machine
            desc = entry["description"] or "(not in master)"
            lines.append(
                f"  {entry['rank']:<5} {entry['tool_id']:<16} "
                f"{entry['part_count']:<7} {entry['wo_count']:<7} "
                f"{entry['cumulative_wo_coverage_pct']:<7} {desc[:45]}"
            )

        # Pareto milestones
        lines.append(f"\n  PARETO MILESTONES:")
        milestones = [50, 70, 80, 90, 95, 100]
        for target in milestones:
            for entry in mr["ranking"]:
                if entry["cumulative_wo_coverage_pct"] >= target:
                    lines.append(f"    {target}% WO coverage: {entry['rank']} tools")
                    break

        # Resident recommendations
        total_pockets = pl.get("total_pockets", 0)
        if total_pockets and mr["ranking"]:
            lines.append(f"\n  RESIDENT TOOL RECOMMENDATION (budget: {total_pockets} pockets):")
            # Reserve 30% of pockets for job-specific tools
            resident_budget = int(total_pockets * 0.7)
            lines.append(f"    Resident budget (70% of pockets): {resident_budget}")
            lines.append(f"    Job-specific reserve (30%): {total_pockets - resident_budget}")

            # Which tools to make resident? Top N by part count, where N = budget
            resident_candidates = mr["ranking"][:resident_budget]
            if resident_candidates:
                cov = resident_candidates[-1]["cumulative_wo_coverage_pct"]
                lines.append(f"    Top {len(resident_candidates)} tools cover {cov}% of WOs on this machine")

            # Cross-reference with what's currently loaded
            current_tools = {p["tool"] for p in pl.get("tools", [])}
            recommended = {e["tool_id"] for e in resident_candidates}
            already_loaded = recommended & current_tools
            need_to_add = recommended - current_tools
            should_remove = current_tools - recommended

            lines.append(f"\n    Already loaded & recommended: {len(already_loaded)}")
            if already_loaded:
                for t in sorted(already_loaded):
                    desc = tool_master.get(t, {}).get("description", "")
                    lines.append(f"      {t:<16} {desc[:50]}")

            lines.append(f"    Recommended but NOT loaded: {len(need_to_add)}")
            if need_to_add:
                for t in sorted(need_to_add):
                    desc = tool_master.get(t, {}).get("description", "")
                    lines.append(f"      {t:<16} {desc[:50]}")

            lines.append(f"    Currently loaded but NOT in top {resident_budget}: {len(should_remove)}")
            if should_remove:
                for t in sorted(should_remove):
                    desc = tool_master.get(t, {}).get("description", "")
                    lines.append(f"      {t:<16} {desc[:50]}")

    # --- Global cross-machine summary ---
    lines.append(f"\n{'=' * 100}")
    lines.append(f"CROSS-MACHINE ANALYSIS: TOOLS THAT APPEAR ON MULTIPLE MACHINES")
    lines.append(f"{'=' * 100}")

    # Find tools used on multiple machines
    tool_machines = defaultdict(set)
    for machine, tools in machine_tools.items():
        for tool_id in tools:
            tool_machines[tool_id].add(machine)

    multi_machine_tools = {t: ms for t, ms in tool_machines.items() if len(ms) > 1}
    sorted_multi = sorted(multi_machine_tools.items(), key=lambda x: len(x[1]), reverse=True)

    lines.append(f"\n  {len(multi_machine_tools)} tools appear on 2+ machines\n")
    lines.append(f"  {'Tool #':<16} {'Machines':<5} {'Description':<45} {'Machine List'}")
    lines.append(f"  {'-'*16} {'-'*5} {'-'*45} {'-'*30}")
    for tool_id, machines in sorted_multi[:80]:
        desc = tool_master.get(tool_id, {}).get("description", "")[:45]
        machine_list = ", ".join(sorted(machines))
        lines.append(f"  {tool_id:<16} {len(machines):<5} {desc:<45} {machine_list}")

    report_text = "\n".join(lines)

    # Write report
    report_path = OUTPUT_DIR / "machine_tool_frequency_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport: {report_path}")

    # Write JSON data
    json_data = {
        "generated": datetime.now().isoformat(),
        "analysis_period": "2024-2026",
        "summary": {
            "total_wos_analyzed": len(wo_details),
            "machines_analyzed": len(machine_rankings),
            "tool_master_records": len(tool_master),
        },
        "machines": {},
    }
    for machine in sorted(machine_rankings.keys()):
        mr = machine_rankings[machine]
        pl = pocket_layouts.get(machine, {})
        json_data["machines"][machine] = {
            "total_pockets": pl.get("total_pockets", 0),
            "loaded_tools": pl.get("tools", []),
            "total_wos": mr["total_wos"],
            "total_parts": mr["total_parts"],
            "unique_tools": mr["total_unique_tools"],
            "ranking": [
                {
                    **entry,
                    # Convert sets to lists aren't in ranking (already processed)
                }
                for entry in mr["ranking"]
            ],
        }

    json_path = OUTPUT_DIR / "machine_tool_frequency_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    print(f"JSON:   {json_path}")

    # Print summary to console
    print(f"\n{'=' * 80}")
    print(f"SUMMARY BY MACHINE")
    print(f"{'=' * 80}")
    print(f"{'Machine':<12} {'Pockets':<9} {'Loaded':<8} {'WOs':<7} {'Parts':<7} {'Tools':<7} {'Top5 WO%'}")
    print(f"{'-'*12} {'-'*9} {'-'*8} {'-'*7} {'-'*7} {'-'*7} {'-'*8}")
    for machine in sorted(machine_rankings.keys()):
        mr = machine_rankings[machine]
        pl = pocket_layouts.get(machine, {})
        top5 = ""
        if len(mr["ranking"]) >= 5:
            top5 = f"{mr['ranking'][4]['cumulative_wo_coverage_pct']}%"
        elif mr["ranking"]:
            top5 = f"{mr['ranking'][-1]['cumulative_wo_coverage_pct']}%"
        print(
            f"{machine:<12} {pl.get('total_pockets', '?'):<9} "
            f"{pl.get('loaded_count', '?'):<8} {mr['total_wos']:<7} "
            f"{mr['total_parts']:<7} {mr['total_unique_tools']:<7} {top5}"
        )

    # Pareto highlights
    print(f"\nPARETO HIGHLIGHTS (tools needed for X% WO coverage):")
    print(f"{'Machine':<12} {'50%':<7} {'70%':<7} {'80%':<7} {'90%':<7} {'95%':<7}")
    print(f"{'-'*12} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for machine in sorted(machine_rankings.keys()):
        mr = machine_rankings[machine]
        pareto_vals = {}
        for target in [50, 70, 80, 90, 95]:
            for entry in mr["ranking"]:
                if entry["cumulative_wo_coverage_pct"] >= target:
                    pareto_vals[target] = entry["rank"]
                    break
        row = f"{machine:<12}"
        for target in [50, 70, 80, 90, 95]:
            val = pareto_vals.get(target, "-")
            row += f" {str(val):<7}"
        print(row)

    print(f"\nDone! Full report: {report_path}")


if __name__ == "__main__":
    main()
