"""
Tool Frequency Analysis - ProShop Sequence Detail Mining
Analyzes which ProShop tools appear most often in part file sequence details,
weighted by work order volume over the past 2 years.

Output: tool_frequency_report.txt in project 22
"""

import requests
import time
import json
import os
from datetime import datetime
from collections import defaultdict, Counter
from pathlib import Path

# --- Config ---
BASE_URL = "https://traxismfg.adionsystems.com"
TOKEN_URL = f"{BASE_URL}/home/member/oauth/accesstoken"
GRAPHQL_URL = f"{BASE_URL}/api/graphql"

OUTPUT_DIR = Path(__file__).parent

# Load credentials from .traxis.env
ENV_PATH = Path(r"C:\Users\AbsoluteArm\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")


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
        print(f"  GraphQL errors: {result['errors']}")
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
      createdTime
      part {
        partNumber
        partName
      }
    }
  }
}
"""

# Query part operations and their sequence detail (tool lists)
PART_TOOLS_QUERY = """
query($partNumbers: [String!]!) {
  parts(filter: { partNumber: $partNumbers }, pageSize: 100) {
    totalRecords
    records {
      partNumber
      partDescription
      operations {
        totalRecords
        records {
          opNumber
          operationDescription
          tools {
            totalRecords
            records {
              toolPlainText
              outOfHolder
              holder
              originalSortPosition
              tool { toolNumber description toolGroupLetter }
            }
          }
        }
      }
    }
  }
}
"""

# Also fetch tool master data for descriptions
TOOLS_MASTER_QUERY = """
{
  tools(pageSize: 500) {
    totalRecords
    records {
      toolNumber
      description
      toolGroupLetter
      ansiCatalogNumber
      bodyDiameter
    }
  }
}
"""


def main():
    print("=" * 70)
    print("TOOL FREQUENCY ANALYSIS - ProShop Sequence Detail Mining")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Analysis window: March 2024 - March 2026 (past 2 years)")
    print("=" * 70)

    creds = load_env()
    session = requests.Session()
    token = get_token(session, creds)
    print("\nAuthenticated with ProShop API")

    # --- Step 1: Get work orders from past 2 years ---
    print("\n--- Fetching Work Orders (2024, 2025, 2026) ---")
    all_wos = []
    for year in ["2024", "2025", "2026"]:
        data = graphql(session, token, WO_QUERY, {"year": year})
        if data and "workOrders" in data:
            records = data["workOrders"].get("records", [])
            total = data["workOrders"].get("totalRecords", 0)
            print(f"  {year}: {len(records)} fetched / {total} total")
            all_wos.extend(records)
        else:
            print(f"  {year}: no data")
        time.sleep(0.5)

    # Index WOs by part number, sum quantities
    part_wo_data = defaultdict(lambda: {"qty_total": 0, "wo_count": 0, "wos": [], "part_name": ""})
    for wo in all_wos:
        part = wo.get("part") or {}
        pn = part.get("partNumber", "")
        if not pn:
            continue
        qty = wo.get("quantityOrdered", 0) or 0
        if isinstance(qty, str):
            try:
                qty = int(qty)
            except:
                qty = 0
        part_wo_data[pn]["qty_total"] += qty
        part_wo_data[pn]["wo_count"] += 1
        part_wo_data[pn]["wos"].append(wo.get("workOrderNumber", ""))
        part_wo_data[pn]["part_name"] = part.get("partName", "")

    print(f"\nTotal WOs: {len(all_wos)}")
    print(f"Unique parts with WOs: {len(part_wo_data)}")

    # --- Step 2: Fetch tool master data ---
    print("\n--- Fetching Tool Master Data ---")
    tool_master = {}
    data = graphql(session, token, TOOLS_MASTER_QUERY)
    if data and "tools" in data:
        total = data["tools"].get("totalRecords", 0)
        records = data["tools"].get("records", [])
        print(f"  Tools: {len(records)} fetched / {total} total")
        for t in records:
            tn = t.get("toolNumber", "")
            if tn:
                tool_master[tn] = {
                    "description": t.get("description", ""),
                    "group": t.get("toolGroupLetter", ""),
                    "diameter": t.get("bodyDiameter", ""),
                    "catalog": t.get("ansiCatalogNumber", ""),
                }
    else:
        print("  No tool master data")

    # If more than 500 tools, try a second page (workaround)
    if data and data["tools"].get("totalRecords", 0) > 500:
        print(f"  Warning: {data['tools']['totalRecords']} total tools, only got first 500")

    # --- Step 3: Fetch sequence details for all parts with WOs ---
    print("\n--- Fetching Part Sequence Details ---")
    part_numbers = list(part_wo_data.keys())

    # Query in batches of 50
    all_parts_data = []
    batch_size = 50
    for i in range(0, len(part_numbers), batch_size):
        batch = part_numbers[i:i + batch_size]
        print(f"  Batch {i // batch_size + 1}/{(len(part_numbers) + batch_size - 1) // batch_size}: "
              f"querying {len(batch)} parts...")
        data = graphql(session, token, PART_TOOLS_QUERY, {"partNumbers": batch})
        if data and "parts" in data:
            records = data["parts"].get("records", [])
            all_parts_data.extend(records)
            print(f"    Got {len(records)} parts with data")
        time.sleep(0.3)

    print(f"\nTotal parts with sequence data: {len(all_parts_data)}")

    # --- Step 4: Analyze tool frequency ---
    print("\n--- Analyzing Tool Frequency ---")

    # Count tools: unweighted (# of parts using it) and weighted (by WO qty)
    tool_part_count = defaultdict(set)      # tool -> set of part numbers
    tool_wo_weighted = defaultdict(int)      # tool -> sum of WO quantities
    tool_wo_count = defaultdict(int)         # tool -> number of WOs using this tool
    tool_appearances = Counter()             # tool -> total sequence appearances
    tool_ops = defaultdict(set)              # tool -> set of operation descriptions
    tool_holders = defaultdict(set)          # tool -> set of holders used

    parts_with_tools = 0
    parts_without_tools = 0

    for part_rec in all_parts_data:
        pn = part_rec.get("partNumber", "")
        ops = part_rec.get("operations", {}).get("records", [])

        part_tools_found = set()
        for op in ops:
            op_desc = op.get("operationDescription", "")
            tools_data = op.get("tools")
            if not tools_data:
                continue
            seq_tools = tools_data.get("records", [])
            for seq in seq_tools:
                tool_id = (seq.get("toolPlainText") or "").strip()
                if not tool_id:
                    # Try nested tool object
                    tool_obj = seq.get("tool")
                    if tool_obj:
                        tool_id = (tool_obj.get("toolNumber") or "").strip()
                if not tool_id:
                    continue
                # Normalize: use canonical case from tool master, else uppercase
                tool_id_upper = tool_id.upper()
                # Find canonical form from tool master
                if tool_id in tool_master:
                    pass  # already canonical
                elif tool_id_upper in tool_master:
                    tool_id = tool_id_upper
                else:
                    # Check case-insensitive match in master
                    matched = False
                    for mk in tool_master:
                        if mk.upper() == tool_id_upper:
                            tool_id = mk
                            matched = True
                            break
                    if not matched:
                        tool_id = tool_id_upper  # default to uppercase
                part_tools_found.add(tool_id)
                tool_appearances[tool_id] += 1
                tool_ops[tool_id].add(op_desc)
                holder = (seq.get("holder") or "").strip()
                if holder:
                    tool_holders[tool_id].add(holder)
                # Capture description from tool object if not in master
                tool_obj = seq.get("tool")
                if tool_obj and tool_id not in tool_master:
                    desc = tool_obj.get("description", "")
                    group = tool_obj.get("toolGroupLetter", "")
                    if desc:
                        tool_master[tool_id] = {
                            "description": desc,
                            "group": group,
                            "diameter": "",
                            "catalog": "",
                        }

        if part_tools_found:
            parts_with_tools += 1
        else:
            parts_without_tools += 1

        # Weight by WO volume
        wo_info = part_wo_data.get(pn, {})
        qty = wo_info.get("qty_total", 0)
        wo_cnt = wo_info.get("wo_count", 0)

        for tool_id in part_tools_found:
            tool_part_count[tool_id].add(pn)
            tool_wo_weighted[tool_id] += qty
            tool_wo_count[tool_id] += wo_cnt

    print(f"Parts with sequence tools: {parts_with_tools}")
    print(f"Parts without sequence tools: {parts_without_tools}")
    print(f"Unique tools found: {len(tool_appearances)}")

    # --- Step 5: Build ranked results ---
    # Sort by WO-weighted count (descending), then by part count
    ranked_tools = sorted(
        tool_appearances.keys(),
        key=lambda t: (tool_wo_weighted.get(t, 0), len(tool_part_count.get(t, set())), tool_appearances[t]),
        reverse=True
    )

    # --- Step 6: Output report ---
    report_lines = []
    report_lines.append("=" * 90)
    report_lines.append("TOOL FREQUENCY ANALYSIS REPORT")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"Analysis Period: March 2024 - March 2026 (past 2 years)")
    report_lines.append(f"Data Source: ProShop API - Part File Sequence Details")
    report_lines.append("=" * 90)

    report_lines.append(f"\nSUMMARY")
    report_lines.append(f"  Total Work Orders analyzed: {len(all_wos)}")
    report_lines.append(f"  Unique parts with WOs: {len(part_wo_data)}")
    report_lines.append(f"  Parts with sequence tool data: {parts_with_tools}")
    report_lines.append(f"  Parts without sequence tool data: {parts_without_tools}")
    report_lines.append(f"  Unique tools found in sequences: {len(tool_appearances)}")
    report_lines.append(f"  Tool master records: {len(tool_master)}")

    report_lines.append(f"\n{'=' * 90}")
    report_lines.append(f"TOP TOOLS RANKED BY WORK ORDER VOLUME")
    report_lines.append(f"(WO-Weighted = sum of ordered qty across all WOs using this tool)")
    report_lines.append(f"{'=' * 90}")
    report_lines.append("")
    report_lines.append(f"{'Rank':<5} {'Tool #':<12} {'Parts':<6} {'WOs':<5} {'WO Qty':<8} {'Seq':<5} {'Description':<45}")
    report_lines.append(f"{'-' * 5} {'-' * 12} {'-' * 6} {'-' * 5} {'-' * 8} {'-' * 5} {'-' * 45}")

    for rank, tool_id in enumerate(ranked_tools, 1):
        desc = tool_master.get(tool_id, {}).get("description", "")
        if not desc:
            desc = "(not in tool master)"
        n_parts = len(tool_part_count.get(tool_id, set()))
        n_wos = tool_wo_count.get(tool_id, 0)
        n_qty = tool_wo_weighted.get(tool_id, 0)
        n_seq = tool_appearances.get(tool_id, 0)
        report_lines.append(f"{rank:<5} {tool_id:<12} {n_parts:<6} {n_wos:<5} {n_qty:<8} {n_seq:<5} {desc[:45]}")

    report_lines.append(f"\n{'=' * 90}")
    report_lines.append(f"DETAILED TOOL BREAKDOWN")
    report_lines.append(f"{'=' * 90}")

    for rank, tool_id in enumerate(ranked_tools[:50], 1):
        desc = tool_master.get(tool_id, {}).get("description", "")
        group = tool_master.get(tool_id, {}).get("group", "")
        diameter = tool_master.get(tool_id, {}).get("diameter", "")
        catalog = tool_master.get(tool_id, {}).get("catalog", "")
        n_parts = len(tool_part_count[tool_id])
        n_qty = tool_wo_weighted[tool_id]
        n_wos = tool_wo_count[tool_id]

        report_lines.append(f"\n--- #{rank}: {tool_id} ---")
        report_lines.append(f"  Description:    {desc}")
        if group:
            report_lines.append(f"  Tool Group:     {group}")
        if diameter:
            report_lines.append(f"  Body Diameter:  {diameter}")
        if catalog:
            report_lines.append(f"  Catalog #:      {catalog}")
        report_lines.append(f"  Used in parts:  {n_parts}")
        report_lines.append(f"  Work orders:    {n_wos}")
        report_lines.append(f"  Total WO qty:   {n_qty}")
        report_lines.append(f"  Seq appearances:{tool_appearances[tool_id]}")

        # List the parts using this tool
        parts_using = sorted(tool_part_count[tool_id])
        report_lines.append(f"  Parts:")
        for pn in parts_using:
            pname = part_wo_data[pn]["part_name"]
            pqty = part_wo_data[pn]["qty_total"]
            pwos = part_wo_data[pn]["wo_count"]
            report_lines.append(f"    {pn:40s} ({pname}) - {pwos} WOs, {pqty} pcs")

        # List operations
        ops_list = sorted(x for x in tool_ops.get(tool_id, set()) if x)
        if ops_list:
            report_lines.append(f"  Operations: {', '.join(ops_list[:10])}")

        # List holders
        holders = sorted(x for x in tool_holders.get(tool_id, set()) if x)
        if holders:
            report_lines.append(f"  Holders: {', '.join(holders)}")

    # --- Top parts by WO volume (for context) ---
    report_lines.append(f"\n{'=' * 90}")
    report_lines.append(f"TOP 30 PARTS BY WORK ORDER VOLUME (for context)")
    report_lines.append(f"{'=' * 90}")
    sorted_parts = sorted(part_wo_data.items(), key=lambda x: x[1]["qty_total"], reverse=True)
    report_lines.append(f"\n{'Rank':<5} {'Part Number':<40} {'WOs':<5} {'Total Qty':<10} {'Part Name'}")
    report_lines.append(f"{'-' * 5} {'-' * 40} {'-' * 5} {'-' * 10} {'-' * 30}")
    for rank, (pn, info) in enumerate(sorted_parts[:30], 1):
        report_lines.append(f"{rank:<5} {pn:<40} {info['wo_count']:<5} {info['qty_total']:<10} {info['part_name']}")

    report_text = "\n".join(report_lines)

    # Write report
    report_path = OUTPUT_DIR / "tool_frequency_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport written to: {report_path}")

    # Also save raw data as JSON for further analysis
    raw_data = {
        "generated": datetime.now().isoformat(),
        "analysis_period": "2024-03 to 2026-03",
        "summary": {
            "total_wos": len(all_wos),
            "unique_parts": len(part_wo_data),
            "parts_with_tools": parts_with_tools,
            "parts_without_tools": parts_without_tools,
            "unique_tools": len(tool_appearances),
        },
        "tool_ranking": [
            {
                "rank": rank,
                "tool_number": tool_id,
                "description": tool_master.get(tool_id, {}).get("description", ""),
                "group": tool_master.get(tool_id, {}).get("group", ""),
                "part_count": len(tool_part_count.get(tool_id, set())),
                "wo_count": tool_wo_count.get(tool_id, 0),
                "wo_qty_weighted": tool_wo_weighted.get(tool_id, 0),
                "sequence_appearances": tool_appearances.get(tool_id, 0),
                "parts": sorted(list(tool_part_count.get(tool_id, set()))),
                "holders": sorted(list(tool_holders.get(tool_id, set()))),
            }
            for rank, tool_id in enumerate(ranked_tools, 1)
        ],
        "part_wo_summary": {
            pn: {
                "part_name": info["part_name"],
                "wo_count": info["wo_count"],
                "qty_total": info["qty_total"],
            }
            for pn, info in sorted_parts
        },
    }

    json_path = OUTPUT_DIR / "tool_frequency_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2)
    print(f"Raw data written to: {json_path}")

    # Print top 20 summary to console
    def safe(s):
        return s.encode("ascii", errors="replace").decode("ascii")

    print(f"\n{'=' * 70}")
    print(f"TOP 20 TOOLS BY WO VOLUME")
    print(f"{'=' * 70}")
    print(f"{'Rank':<5} {'Tool #':<12} {'Parts':<6} {'WOs':<5} {'WO Qty':<8} {'Description'}")
    print(f"{'-' * 5} {'-' * 12} {'-' * 6} {'-' * 5} {'-' * 8} {'-' * 40}")
    for rank, tool_id in enumerate(ranked_tools[:20], 1):
        desc = tool_master.get(tool_id, {}).get("description", "(not in master)")
        n_parts = len(tool_part_count.get(tool_id, set()))
        n_wos = tool_wo_count.get(tool_id, 0)
        n_qty = tool_wo_weighted.get(tool_id, 0)
        print(f"{rank:<5} {tool_id:<12} {n_parts:<6} {n_wos:<5} {n_qty:<8} {safe(desc[:40])}")

    print(f"\nDone! Full report: {report_path}")


if __name__ == "__main__":
    main()
