"""
Test script for readiness lights + tool-aware scheduling changes.

Run from the scheduler directory:
    cd "19. Shop Scheduler"
    python test_readiness.py

Each test is independent. If one fails, the rest still run.
Nothing writes back to ProShop -- all changes are local DB only.
"""

import sys
import os
import json
import sqlite3
import traceback

# Fix Windows terminal encoding
os.environ["PYTHONIOENCODING"] = "utf-8"

# -- Setup --------------------------------------------------------------------

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import config

# Check secret before anything else
if not config.PROSHOP_CLIENT_SECRET:
    print("ERROR: PROSHOP_CLIENT_SECRET not set.")
    print("  set PROSHOP_CLIENT_SECRET=<your secret>")
    sys.exit(1)

from proshop_client import ProShopClient
from database import get_db, init_db

passed = 0
failed = 0
skipped = 0


def run_test(name, fn):
    global passed, failed, skipped
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    try:
        result = fn()
        if result == "SKIP":
            print(f"  >> SKIPPED")
            skipped += 1
        else:
            print(f"  >> PASSED")
            passed += 1
    except Exception as e:
        print(f"  >> FAILED: {e}")
        traceback.print_exc()
        failed += 1


# -- Helpers ------------------------------------------------------------------

def get_client():
    return ProShopClient(
        config.PROSHOP_GRAPHQL_URL,
        config.PROSHOP_TOKEN_URL,
        config.PROSHOP_CLIENT_ID,
        config.PROSHOP_CLIENT_SECRET,
        config.PROSHOP_SCOPE,
    )


# -- Test 1: Schema migration -- new tables exist -----------------------------

def test_schema():
    """Verify the 3 new tables can be created without breaking existing DB."""
    init_db()
    conn = get_db()

    # Check tables exist
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t["name"] for t in tables]
    print(f"  Tables in DB: {table_names}")

    for required in ["readiness", "machine_pockets", "operation_tools"]:
        assert required in table_names, f"Missing table: {required}"
        print(f"  [OK] {required} table exists")

    # Check readiness columns
    cols = conn.execute("PRAGMA table_info(readiness)").fetchall()
    col_names = [c["name"] for c in cols]
    print(f"  readiness columns: {col_names}")
    for c in ["operation_id", "program_ready", "material_ready", "tools_ready", "machine_ready"]:
        assert c in col_names, f"Missing column: {c}"

    # Check machine_pockets columns
    cols = conn.execute("PRAGMA table_info(machine_pockets)").fetchall()
    col_names = [c["name"] for c in cols]
    print(f"  machine_pockets columns: {col_names}")
    for c in ["machine_id", "pocket_number", "tool_number", "out_of_holder"]:
        assert c in col_names, f"Missing column: {c}"

    # Check operation_tools columns
    cols = conn.execute("PRAGMA table_info(operation_tools)").fetchall()
    col_names = [c["name"] for c in cols]
    print(f"  operation_tools columns: {col_names}")
    for c in ["operation_id", "tool_number", "tool_description", "out_of_holder"]:
        assert c in col_names, f"Missing column: {c}"

    conn.close()

run_test("Schema -- new tables created", test_schema)


# -- Test 2: API -- vendorPOs query works -------------------------------------

def test_vendor_pos():
    """Query vendorPOs from ProShop. Verify structure, check WO linkage."""
    client = get_client()
    result = client.get_outstanding_vpos(page_size=50)
    total = result.get("totalRecords", 0)
    records = result.get("records", [])
    print(f"  Total material VPOs: {total}")
    print(f"  Records returned: {len(records)}")

    if not records:
        print("  No material VPOs found -- this is valid if no outstanding POs")
        return

    # Check structure of first PO
    po = records[0]
    print(f"  First PO: type={po.get('poType')}")

    items = (po.get("poItems") or {}).get("records", [])
    print(f"  Line items on first PO: {len(items)}")

    # Show WO linkage
    wo_linked = 0
    wo_unlinked = 0
    for r in records:
        for item in (r.get("poItems") or {}).get("records", []):
            wo_text = (item.get("workOrderPlainText") or "").strip()
            received = item.get("receivedDate")
            if wo_text:
                wo_linked += 1
                if wo_linked <= 5:
                    print(f"    WO={wo_text}  received={received or 'NO'}")
            else:
                wo_unlinked += 1

    print(f"  PO items linked to a WO: {wo_linked}")
    print(f"  PO items with no WO: {wo_unlinked}")
    assert wo_linked + wo_unlinked > 0, "No PO items found at all"

run_test("API -- vendorPOs query", test_vendor_pos)


# -- Test 3: API -- work cell pockets query works -----------------------------

def test_pockets():
    """Query Mill-2 pockets from ProShop. Verify tool data present."""
    client = get_client()
    wc = client.get_work_cell_pockets("Mill-2")

    if wc is None:
        print("  WARNING: workCell(potId:'Mill-2') returned null")
        print("  This could mean the potId doesn't match or scope issue")
        return "SKIP"

    print(f"  Machine: {wc.get('potId')}  pockets: {wc.get('numberOfPockets')}")
    pockets = (wc.get("pockets") or {}).get("records", [])
    print(f"  Pocket records returned: {len(pockets)}")

    populated = 0
    for p in pockets[:5]:
        tool = (p.get("toolPlainText") or "").strip()
        ooh = p.get("outOfHolder")
        holder = (p.get("holder") or "").strip()
        pocket_num = p.get("legacyId", "?")
        if tool:
            populated += 1
        print(f"    Pocket {pocket_num}: tool='{tool}' stickout={ooh} holder='{holder}'")

    total_populated = sum(1 for p in pockets if (p.get("toolPlainText") or "").strip())
    print(f"  Pockets with tools: {total_populated}/{len(pockets)}")
    assert len(pockets) > 0, "No pockets returned"

run_test("API -- Mill-2 pockets", test_pockets)


# -- Test 4: API -- operation tools query works --------------------------------

def test_operation_tools():
    """Query op tools for a known WO. Verify partOperation.tools populated."""
    client = get_client()

    # First get an active WO
    wos = client.get_work_orders(status="active", page_size=10)
    records = wos.get("records", [])
    if not records:
        print("  No active WOs to test with")
        return "SKIP"

    # Try a few WOs until we find one with tools
    found = False
    for wo in records[:5]:
        wo_num = wo.get("workOrderNumber")
        tools_by_op = client.get_operation_tools(wo_num)
        if tools_by_op:
            print(f"  WO {wo_num}: {len(tools_by_op)} ops have tool data")
            for op_num, tools in list(tools_by_op.items())[:3]:
                print(f"    Op {op_num}: {len(tools)} tools")
                for t in tools[:3]:
                    tool_info = t.get("tool") or {}
                    holder = (t.get("holder") or "") or ""
                    print(f"      T#{tool_info.get('toolNumber')} {(tool_info.get('description') or '')[:40]}  "
                          f"stickout={t.get('outOfHolder')}  holder={holder[:20]}")
            found = True
            break
        else:
            print(f"  WO {wo_num}: no tool data")

    if not found:
        print("  WARNING: No WOs with tool data found in first 5 active WOs")
        print("  This is normal if partOperation.tools isn't populated yet")

run_test("API -- operation tools", test_operation_tools)


# -- Test 5: Program readiness logic (offline) --------------------------------

def test_program_readiness_logic():
    """Test program readiness computation with mock data -- no API calls."""
    from sync import _compute_program_readiness

    conn = get_db()

    # Make sure we have a test WO + ops to work with
    conn.execute("INSERT OR IGNORE INTO work_orders (wo_number, part_number, status) VALUES ('TEST-PR', 'TEST-PART', 'active')")
    conn.execute("INSERT OR IGNORE INTO operations (id, wo_number, op_number, op_name, work_center) VALUES ('TEST-PR-10', 'TEST-PR', 10, 'Programming', 'Programming')")
    conn.execute("INSERT OR IGNORE INTO operations (id, wo_number, op_number, op_name, work_center) VALUES ('TEST-PR-20', 'TEST-PR', 20, 'Mill Op 1', 'Mill-2')")
    conn.execute("INSERT OR IGNORE INTO operations (id, wo_number, op_number, op_name, work_center) VALUES ('TEST-PR-30', 'TEST-PR', 30, 'Mill Op 2', 'MILL-X')")
    conn.commit()

    # Case 1: Programming NOT complete
    mock_ops = [
        {"operationNumber": 10, "operationType": "Programming", "isOpComplete": False, "workCenterPlainText": "Programming"},
        {"operationNumber": 20, "operationType": "Manufacturing", "isOpComplete": False, "workCenterPlainText": "Mill-2"},
        {"operationNumber": 30, "operationType": "Manufacturing", "isOpComplete": False, "workCenterPlainText": "MILL-X"},
    ]
    _compute_program_readiness(conn, "TEST-PR", mock_ops)

    r20 = conn.execute("SELECT program_ready FROM readiness WHERE operation_id='TEST-PR-20'").fetchone()
    r30 = conn.execute("SELECT program_ready FROM readiness WHERE operation_id='TEST-PR-30'").fetchone()
    assert r20 and r20[0] == 0, f"Expected program_ready=0 for op 20, got {r20}"
    assert r30 and r30[0] == 0, f"Expected program_ready=0 for op 30, got {r30}"
    print("  [OK] Programming NOT complete -> mfg ops program_ready=0")

    # Case 2: Programming IS complete
    mock_ops[0]["isOpComplete"] = True
    _compute_program_readiness(conn, "TEST-PR", mock_ops)

    r20 = conn.execute("SELECT program_ready FROM readiness WHERE operation_id='TEST-PR-20'").fetchone()
    r30 = conn.execute("SELECT program_ready FROM readiness WHERE operation_id='TEST-PR-30'").fetchone()
    assert r20 and r20[0] == 1, f"Expected program_ready=1 for op 20, got {r20}"
    assert r30 and r30[0] == 1, f"Expected program_ready=1 for op 30, got {r30}"
    print("  [OK] Programming complete -> mfg ops program_ready=1")

    # Case 3: No programming op at all -> should be ready
    mock_ops_no_prog = [
        {"operationNumber": 20, "operationType": "Manufacturing", "isOpComplete": False, "workCenterPlainText": "Mill-2"},
    ]
    conn.execute("DELETE FROM readiness WHERE operation_id='TEST-PR-20'")
    conn.commit()
    _compute_program_readiness(conn, "TEST-PR", mock_ops_no_prog)

    r20 = conn.execute("SELECT program_ready FROM readiness WHERE operation_id='TEST-PR-20'").fetchone()
    assert r20 and r20[0] == 1, f"Expected program_ready=1 when no prog op, got {r20}"
    print("  [OK] No programming op -> program_ready=1")

    # Cleanup
    conn.execute("DELETE FROM readiness WHERE operation_id LIKE 'TEST-PR%'")
    conn.execute("DELETE FROM operations WHERE wo_number='TEST-PR'")
    conn.execute("DELETE FROM work_orders WHERE wo_number='TEST-PR'")
    conn.commit()
    conn.close()

run_test("Program readiness logic (offline)", test_program_readiness_logic)


# -- Test 6: Tool overlap scoring (offline) -----------------------------------

def test_tool_overlap():
    """Test _tool_overlap_score with synthetic pocket + op tool data."""
    from suggest import _tool_overlap_score

    conn = get_db()

    # Temporarily disable FK checks for test data (test-mill is not in machines table)
    conn.execute("PRAGMA foreign_keys=OFF")

    # Insert fake machine pockets
    conn.execute("DELETE FROM machine_pockets WHERE machine_id='test-mill'")
    test_pockets = [
        ("test-mill", 1, "T001", 2.5, "ER32"),
        ("test-mill", 2, "T002", 3.0, "ER32"),
        ("test-mill", 3, "T003", 1.5, "BT30"),
        ("test-mill", 4, "T004", 2.0, None),
    ]
    conn.executemany(
        "INSERT INTO machine_pockets (machine_id, pocket_number, tool_number, out_of_holder, holder) VALUES (?,?,?,?,?)",
        test_pockets
    )

    # Insert fake operation tools
    conn.execute("DELETE FROM operation_tools WHERE operation_id='TEST-OVL-20'")
    test_op_tools = [
        ("TEST-OVL-20", "T001", "End Mill", None, 2.5, 1),   # matches pocket 1 exactly
        ("TEST-OVL-20", "T002", "Drill", None, 3.1, 2),      # T002 exists but stickout off by 0.1 -- match
        ("TEST-OVL-20", "T005", "Reamer", None, 1.0, 3),     # not in machine
    ]
    conn.executemany(
        "INSERT INTO operation_tools (operation_id, tool_number, tool_description, holder, out_of_holder, sequence_number) VALUES (?,?,?,?,?,?)",
        test_op_tools
    )
    conn.commit()

    matched, total, ratio = _tool_overlap_score(conn, "TEST-OVL-20", "test-mill")
    print(f"  Score: {matched}/{total} = {ratio:.2f}")
    assert total == 3, f"Expected 3 total tools, got {total}"
    assert matched == 2, f"Expected 2 matched (T001 exact, T002 within tolerance), got {matched}"
    assert abs(ratio - 2/3) < 0.01, f"Expected ratio ~0.67, got {ratio}"
    print(f"  [OK] 2/3 tools matched (T001 exact, T002 within 0.1 tolerance, T005 missing)")

    # Test with no op tools -> (0,0,0.0)
    m, t, r = _tool_overlap_score(conn, "NONEXISTENT-OP", "test-mill")
    assert t == 0 and r == 0.0, f"Expected (0,0,0.0) for missing op, got ({m},{t},{r})"
    print(f"  [OK] Missing op -> (0,0,0.0)")

    # Cleanup
    conn.execute("DELETE FROM machine_pockets WHERE machine_id='test-mill'")
    conn.execute("DELETE FROM operation_tools WHERE operation_id='TEST-OVL-20'")
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    conn.close()

run_test("Tool overlap scoring (offline)", test_tool_overlap)


# -- Test 7: Renumber engine (offline, no Fusion) -----------------------------

def test_renumber_engine():
    """Test the renumbering logic from Phase 4 -- pure Python, no Fusion needed."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                     "1. Proshop Automations", "ToolRenumber"))
    from renumber_engine import compute_renumbering, format_preview

    # Simulate: machine has T001 in pocket 3, T002 in pocket 7
    pocket_map = {
        3: {"tool_number": "T001", "out_of_holder": 2.5, "holder": "ER32"},
        7: {"tool_number": "T002", "out_of_holder": 3.0, "holder": "ER32"},
        12: {"tool_number": "T010", "out_of_holder": 1.0, "holder": "BT30"},
    }

    # CAM has T1=T001, T2=T002, T3=T099 (not in machine)
    cam_tools = [
        {"tool_number": 1, "product_id": "T001", "description": "1/2 End Mill"},
        {"tool_number": 2, "product_id": "T002", "description": "3/8 Drill"},
        {"tool_number": 3, "product_id": "T099", "description": "Chamfer Mill"},
    ]

    assignments = compute_renumbering(cam_tools, pocket_map)
    print(f"  Assignments: {len(assignments)}")
    for a in assignments:
        print(f"    T{a['tool_number_old']} -> T{a['tool_number_new']}  ({a['reason']})")

    # T001 should go to pocket 3
    a1 = next(a for a in assignments if a["product_id"] == "T001")
    assert a1["tool_number_new"] == 3, f"T001 should map to pocket 3, got {a1['tool_number_new']}"

    # T002 should go to pocket 7
    a2 = next(a for a in assignments if a["product_id"] == "T002")
    assert a2["tool_number_new"] == 7, f"T002 should map to pocket 7, got {a2['tool_number_new']}"

    # T099 should get an empty pocket (not 3, 7, or 12)
    a3 = next(a for a in assignments if a["product_id"] == "T099")
    assert a3["tool_number_new"] not in (3, 7, 12), f"T099 should get empty pocket, got {a3['tool_number_new']}"
    print(f"  [OK] T001->pocket 3, T002->pocket 7, T099->pocket {a3['tool_number_new']} (empty)")

    preview = format_preview(assignments)
    print(f"\n  Preview output:\n")
    for line in preview.split("\n"):
        print(f"    {line}")

run_test("Renumber engine logic (offline)", test_renumber_engine)


# -- Test 8: Full sync with readiness -----------------------------------------

def test_full_sync():
    """Run a full sync and check that readiness table gets populated.
    This actually calls ProShop but only READS -- no mutations."""
    from sync import SyncEngine

    client = get_client()
    engine = SyncEngine(client)

    print("  Running full sync (this may take 30-60 seconds)...")
    result = engine.full_sync()
    print(f"  Sync result: {result}")

    conn = get_db()

    # Check readiness table
    readiness_count = conn.execute("SELECT COUNT(*) FROM readiness").fetchone()[0]
    print(f"  Readiness rows: {readiness_count}")

    prog_ready = conn.execute("SELECT COUNT(*) FROM readiness WHERE program_ready=1").fetchone()[0]
    prog_not = conn.execute("SELECT COUNT(*) FROM readiness WHERE program_ready=0").fetchone()[0]
    print(f"  Program ready: {prog_ready} yes, {prog_not} no")

    mat_ready = conn.execute("SELECT COUNT(*) FROM readiness WHERE material_ready=1").fetchone()[0]
    mat_not = conn.execute("SELECT COUNT(*) FROM readiness WHERE material_ready=0").fetchone()[0]
    print(f"  Material ready: {mat_ready} yes, {mat_not} no")

    # Check machine_pockets
    pocket_count = conn.execute("SELECT COUNT(*) FROM machine_pockets").fetchone()[0]
    pocket_with_tools = conn.execute("SELECT COUNT(*) FROM machine_pockets WHERE tool_number IS NOT NULL").fetchone()[0]
    machines_with_pockets = conn.execute("SELECT COUNT(DISTINCT machine_id) FROM machine_pockets").fetchone()[0]
    print(f"  Machine pockets: {pocket_count} total, {pocket_with_tools} with tools, across {machines_with_pockets} machines")

    # Check operation_tools
    op_tools_count = conn.execute("SELECT COUNT(*) FROM operation_tools").fetchone()[0]
    ops_with_tools = conn.execute("SELECT COUNT(DISTINCT operation_id) FROM operation_tools").fetchone()[0]
    print(f"  Operation tools: {op_tools_count} total tool records, across {ops_with_tools} operations")

    # Spot-check: pick a readiness row and display it
    sample = conn.execute(
        "SELECT r.*, o.op_name, o.wo_number FROM readiness r JOIN operations o ON r.operation_id=o.id LIMIT 5"
    ).fetchall()
    if sample:
        print(f"\n  Sample readiness rows:")
        for s in sample:
            print(f"    {s['wo_number']} {s['operation_id']}: prog={s['program_ready']} mat={s['material_ready']} "
                  f"tools={s['tools_ready']} machine={s['machine_ready']}")

    conn.close()
    assert readiness_count > 0, "No readiness rows created"

run_test("Full sync with readiness (live API, read-only)", test_full_sync)


# -- Test 9: API endpoints return readiness data ------------------------------

def test_api_endpoints():
    """Start a test Flask client and verify readiness in API responses."""
    # Use Flask's test client -- no actual server needed
    from app import app

    with app.test_client() as tc:
        # Test /api/operations
        resp = tc.get("/api/operations?unscheduled=true&schedulable=true")
        assert resp.status_code == 200, f"operations returned {resp.status_code}"
        ops = resp.get_json()
        print(f"  /api/operations: {len(ops)} ops returned")
        if ops:
            op = ops[0]
            assert "readiness" in op, "Missing 'readiness' key in operation"
            r = op["readiness"]
            assert all(k in r for k in ["program_ready", "material_ready", "tools_ready", "machine_ready"]), \
                f"Missing readiness keys: {r}"
            print(f"  [OK] First op readiness: {r}")

        # Test /api/blocks
        resp = tc.get("/api/blocks")
        assert resp.status_code == 200, f"blocks returned {resp.status_code}"
        blocks = resp.get_json()
        print(f"  /api/blocks: {len(blocks)} blocks returned")
        if blocks:
            b = blocks[0]
            r = b.get("extendedProps", {}).get("readiness")
            assert r is not None, "Missing 'readiness' in block extendedProps"
            print(f"  [OK] First block readiness: {r}")

        # Test tools-ready toggle
        if ops:
            op_id = ops[0]["id"]
            resp = tc.post(f"/api/operations/{op_id}/tools-ready",
                           content_type="application/json")
            assert resp.status_code == 200, f"tools-ready toggle returned {resp.status_code}"
            data = resp.get_json()
            print(f"  [OK] Tools toggle for {op_id}: tools_ready={data.get('tools_ready')}")

            # Toggle back
            resp = tc.post(f"/api/operations/{op_id}/tools-ready",
                           content_type="application/json")
            data = resp.get_json()
            print(f"  [OK] Toggle back: tools_ready={data.get('tools_ready')}")

run_test("API endpoints return readiness data", test_api_endpoints)


# -- Test 10: Suggestions include tool data -----------------------------------

def test_suggestions():
    """Verify suggestions endpoint includes tool_match/tool_total."""
    from app import app

    with app.test_client() as tc:
        resp = tc.get("/api/suggestions")
        assert resp.status_code == 200
        data = resp.get_json()
        suggestions = data.get("suggestions", [])
        skipped_ops = data.get("skipped", [])
        print(f"  Suggestions: {len(suggestions)}, Skipped: {len(skipped_ops)}")

        if suggestions:
            s = suggestions[0]
            print(f"  First suggestion: {s['op_id']} -> {s['machine_name']}")
            assert "tool_match" in s, "Missing tool_match in suggestion"
            assert "tool_total" in s, "Missing tool_total in suggestion"
            print(f"  [OK] tool_match={s['tool_match']}, tool_total={s['tool_total']}")

            # Show a few with tool data
            with_tools = [s for s in suggestions if s.get("tool_total", 0) > 0]
            print(f"  Suggestions with tool data: {len(with_tools)}/{len(suggestions)}")
            for s in with_tools[:5]:
                print(f"    {s['op_id']} -> {s['machine_name']}: {s['tool_match']}/{s['tool_total']} tools")

run_test("Suggestions include tool overlap data", test_suggestions)


# -- Summary ------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*60}")

if failed > 0:
    print("\nFailed tests need investigation before going live.")
    sys.exit(1)
else:
    print("\nAll tests passed! Safe to start the scheduler and check the UI.")
    sys.exit(0)
