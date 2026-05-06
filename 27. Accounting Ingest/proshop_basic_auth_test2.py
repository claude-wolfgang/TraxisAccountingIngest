"""Confirm basic auth can actually create a customer PO (not just silently skip).

Step 1: beginsession.
Step 2: query existing customer POs to grab a real client name.
Step 3: addCustomerPo with that client and a unique test PO number.
Step 4: query back to confirm it exists.
"""
from pathlib import Path
import requests, json, uuid

ENV_PATH = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")
BASE = "https://traxismfg.adionsystems.com"
BEGIN_URL = f"{BASE}/api/beginsession"
GQL_URL = f"{BASE}/api/graphql"

env = {}
for line in ENV_PATH.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

_u = env["PROSHOP_USERNAME"]
USERNAME = _u if "@" in _u else f"{_u}@traxismfg.com"
PASSWORD = env["PROSHOP_PASSWORD"]
SCOPE = env["ACCOUNTING_SCOPE"].replace("+", " ")

# beginsession
r = requests.post(BEGIN_URL, headers={"Content-Type": "application/json"},
                  json={"username": USERNAME, "password": PASSWORD, "scope": SCOPE}, timeout=30)
r.raise_for_status()
token = r.json()["authorizationResult"]["token"]
print(f"session token: {token[:16]}...")


def gql(query, variables=None):
    r = requests.post(GQL_URL, params={"token": token},
                      headers={"Content-Type": "application/json"},
                      json={"query": query, "variables": variables or {}}, timeout=30)
    return r.status_code, r.json()


# Step 2: get a real client name from existing customer POs
print("\n=== existing customer POs ===")
status, j = gql("{ customerPos(pageSize: 3) { records { poId client { name } clientPONumber year } } }")
print(json.dumps(j, indent=2)[:800])
records = (j.get("data") or {}).get("customerPos", {}).get("records", [])
if not records:
    raise SystemExit("No existing customer POs to draw a client name from.")
real_client = records[0]["client"]["name"]
print(f"\nUsing real client: {real_client!r}")

# Step 3: try addCustomerPo with real client
test_po_num = f"BASIC-AUTH-TEST-{uuid.uuid4().hex[:8].upper()}"
mutation = """
mutation AddCustomerPo($data: AddCustomerPoInput!) {
  addCustomerPo(data: $data) { poId proshopUrl }
}"""
test_data = {
    "client": real_client,
    "clientPONumber": test_po_num,
    "dateEntered": "2026-05-06",
    "year": "2026",
}
print(f"\n=== addCustomerPo (client={real_client!r}, clientPONumber={test_po_num}) ===")
status, j = gql(mutation, {"data": test_data})
print(f"status: {status}")
print(json.dumps(j, indent=2))

# Step 4: confirm by querying back
print(f"\n=== verify by searching for {test_po_num} ===")
status, j = gql("query Q($n: String!) { customerPos(filter: { field: \"clientPONumber\", value: $n }) { records { poId client clientPONumber } } }",
                {"n": test_po_num})
print(json.dumps(j, indent=2))

print(f"\nDone. If the test PO ({test_po_num}) was created, delete it from ProShop UI.")

# Cleanup: end the session
end_r = requests.get(f"{BASE}/api/endsession", params={"token": token}, timeout=15)
print(f"\nendsession: {end_r.status_code} {end_r.text[:200]}")

