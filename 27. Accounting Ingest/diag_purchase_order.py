"""Diagnose addPurchaseOrder failure on the Accounting OAuth client.

Tests:
  1. Token acquisition — does the scope string get accepted?
  2. Schema introspection — what fields does AddPurchaseOrderInput actually require?
  3. Read-only probe — can the token read purchaseOrders at all?
  4. Minimal mutation — send the smallest valid payload and capture the exact error.
  5. Compare with main client — does PROSHOP_CLIENT_ID fare any differently?
"""
import json, time, requests
from pathlib import Path

# ── Load env ──────────────────────────────────────────────────────────────────
env = {}
env_path = Path(
    r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects"
    r"\1. Proshop Automations\.traxis.env"
)
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GQL_URL = "https://traxismfg.adionsystems.com/api/graphql"


def get_token(client_id, client_secret, scope):
    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    })
    r.raise_for_status()
    return r.json()["access_token"]


def gql(token, query, variables=None):
    r = requests.post(
        GQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    return r.status_code, r.json()


def type_name(t):
    if not t:
        return "?"
    if t.get("name"):
        return t["name"]
    kind = t.get("kind", "")
    inner = t.get("ofType")
    if kind == "NON_NULL":
        return type_name(inner) + "!"
    if kind == "LIST":
        return "[" + type_name(inner) + "]"
    return "?"


# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("  PURCHASE ORDER DIAGNOSTIC")
print("=" * 70)

# ── 1. Token acquisition ─────────────────────────────────────────────────────
print("\n[1] Token acquisition — Accounting client (344C-F647-B9BC)")
try:
    acct_token = get_token(
        env["ACCOUNTING_CLIENT_ID"],
        env["ACCOUNTING_CLIENT_SECRET"],
        env["ACCOUNTING_SCOPE"],
    )
    print(f"    OK — token acquired (first 20 chars: {acct_token[:20]}...)")
    print(f"    Requested scope: {env['ACCOUNTING_SCOPE']}")
except Exception as e:
    print(f"    FAILED — {e}")
    acct_token = None

# ── 2. Introspect AddPurchaseOrderInput ───────────────────────────────────────
print("\n[2] Introspect AddPurchaseOrderInput schema")
if acct_token:
    introspect_q = """
    query($name: String!) {
      __type(name: $name) {
        kind
        inputFields {
          name
          type { name kind ofType { name kind ofType { name kind ofType { name } } } }
        }
      }
    }"""
    for input_type in ["AddPurchaseOrderInput", "AddPurchaseOrderPoItemInput"]:
        status, data = gql(acct_token, introspect_q, {"name": input_type})
        t = (data.get("data") or {}).get("__type")
        if not t:
            print(f"    {input_type}: NOT FOUND (type doesn't exist or not visible)")
        else:
            print(f"    {input_type} ({t['kind']}):")
            for f in (t.get("inputFields") or []):
                tn = type_name(f["type"])
                req = " *** REQUIRED" if tn.endswith("!") else ""
                print(f"      {f['name']:>30}  {tn}{req}")

# ── 3. Read probe — can the token read purchaseOrders? ────────────────────────
print("\n[3] Read probe — query purchaseOrders with Accounting token")
if acct_token:
    read_q = "{ purchaseOrders(pageSize: 1) { totalRecords records { purchaseOrderId } } }"
    status, data = gql(acct_token, read_q)
    if "errors" in data:
        print(f"    BLOCKED — {data['errors'][0]['message']}")
    else:
        total = (data.get("data") or {}).get("purchaseOrders", {}).get("totalRecords", "?")
        print(f"    OK — can read purchaseOrders ({total} total records)")

# ── 4. Minimal mutation — addPurchaseOrder ────────────────────────────────────
print("\n[4] Minimal mutation — addPurchaseOrder with Accounting token")
if acct_token:
    mutation = """
    mutation AddPurchaseOrder($data: AddPurchaseOrderInput!) {
      addPurchaseOrder(data: $data) { id proshopUrl }
    }"""
    # Absolute minimum payload
    minimal_payload = {
        "poType": "Standard",
        "year": "2026",
    }
    print(f"    Payload: {json.dumps(minimal_payload)}")
    status, data = gql(acct_token, mutation, {"data": minimal_payload})
    print(f"    HTTP {status}")
    if "errors" in data:
        for err in data["errors"]:
            print(f"    ERROR: {err.get('message', err)}")
            if err.get("extensions"):
                print(f"    extensions: {json.dumps(err['extensions'], indent=6)}")
    else:
        result = (data.get("data") or {}).get("addPurchaseOrder", {})
        print(f"    SUCCESS — id={result.get('id')}, url={result.get('proshopUrl')}")
        print("    *** NOTE: Delete this test PO from ProShop! ***")

# ── 5. Compare with main PROSHOP client ───────────────────────────────────────
print("\n[5] Compare — same read probe with PROSHOP client")
try:
    main_token = get_token(
        env["PROSHOP_CLIENT_ID"],
        env["PROSHOP_CLIENT_SECRET"],
        env["PROSHOP_SCOPE"],
    )
    read_q = "{ purchaseOrders(pageSize: 1) { totalRecords records { purchaseOrderId } } }"
    status, data = gql(main_token, read_q)
    if "errors" in data:
        print(f"    BLOCKED — {data['errors'][0]['message']}")
    else:
        total = (data.get("data") or {}).get("purchaseOrders", {}).get("totalRecords", "?")
        print(f"    OK — can read purchaseOrders ({total} total records)")

    # Also try the mutation with main client
    print("\n[5b] Minimal mutation with PROSHOP client")
    # Check if PROSHOP_SCOPE includes purchaseorders
    ps_scope = env.get("PROSHOP_SCOPE", "")
    has_po = "purchaseorders" in ps_scope.lower()
    print(f"    PROSHOP_SCOPE includes purchaseorders: {has_po}")
    if has_po:
        status, data = gql(main_token, mutation, {"data": minimal_payload})
        print(f"    HTTP {status}")
        if "errors" in data:
            for err in data["errors"]:
                print(f"    ERROR: {err.get('message', err)}")
        else:
            result = (data.get("data") or {}).get("addPurchaseOrder", {})
            print(f"    SUCCESS — id={result.get('id')}, url={result.get('proshopUrl')}")
            print("    *** NOTE: Delete this test PO from ProShop! ***")
    else:
        print(f"    Skipping mutation — scope doesn't include purchaseorders")
        print(f"    Scope: {ps_scope}")
except Exception as e:
    print(f"    FAILED — {e}")

# ── 6. Token with ONLY purchaseorders scope ───────────────────────────────────
print("\n[6] Isolation test — token with ONLY purchaseorders:rwdp scope")
try:
    isolated_token = get_token(
        env["ACCOUNTING_CLIENT_ID"],
        env["ACCOUNTING_CLIENT_SECRET"],
        "purchaseorders:rwdp",
    )
    print(f"    Token acquired (scope requested: purchaseorders:rwdp)")
    read_q = "{ purchaseOrders(pageSize: 1) { totalRecords } }"
    status, data = gql(isolated_token, read_q)
    if "errors" in data:
        print(f"    Read BLOCKED — {data['errors'][0]['message']}")
        print("    --> purchaseorders scope NOT actually granted to this client")
    else:
        total = (data.get("data") or {}).get("purchaseOrders", {}).get("totalRecords", "?")
        print(f"    Read OK — {total} records visible")
        print("    --> purchaseorders scope IS granted, mutation issue is something else")
except Exception as e:
    print(f"    FAILED — {e}")

print("\n" + "=" * 70)
print("  DIAGNOSTIC COMPLETE")
print("=" * 70)
