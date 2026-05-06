"""Test whether addCustomerPo works under Basic Auth (api/beginsession) flow.

Per Adion docs (PADD - Begin session):
  POST /api/beginsession with JSON {username, password, scope}
  Returns authorizationResult.token; pass token as query string arg on future calls.
"""
import json
from pathlib import Path
import requests

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

_raw_user = env["PROSHOP_USERNAME"]
USERNAME = _raw_user if "@" in _raw_user else f"{_raw_user}@traxismfg.com"
PASSWORD = env["PROSHOP_PASSWORD"]
SCOPE = env["ACCOUNTING_SCOPE"].replace("+", " ")  # JSON wants space-delimited

print(f"username: {USERNAME}")
print(f"scope:    {SCOPE}")

# --- Step 1: beginsession ---
print("\n" + "=" * 60)
print("STEP 1: POST /api/beginsession")
print("=" * 60)

r = requests.post(
    BEGIN_URL,
    headers={"Content-Type": "application/json"},
    json={"username": USERNAME, "password": PASSWORD, "scope": SCOPE},
    timeout=30,
)
print(f"  status: {r.status_code}")
body = r.text[:600]
print(f"  body: {body}")

if r.status_code != 200:
    raise SystemExit("beginsession failed — stop.")

j = r.json()
auth = j.get("authorizationResult", {})
token = auth.get("token")
print(f"  userId:   {auth.get('userId')}")
print(f"  userName: {auth.get('userName')}")
print(f"  validFor: {auth.get('sessionValidForSeconds')}s")
print(f"  token:    {token[:20]}...{token[-8:]}" if token else "  NO TOKEN")

# --- Step 2: addCustomerPo with token as query string ---
print("\n" + "=" * 60)
print("STEP 2: addCustomerPo via session token (query string)")
print("=" * 60)

mutation = """
mutation AddCustomerPo($data: AddCustomerPoInput!) {
  addCustomerPo(data: $data) { poId proshopUrl }
}"""
test_data = {
    "client": "TEST-DO-NOT-USE",
    "clientPONumber": "TEST-BASIC-AUTH-001",
    "dateEntered": "2026-05-06",
    "year": "2026",
}

r = requests.post(
    GQL_URL,
    params={"token": token},
    headers={"Content-Type": "application/json"},
    json={"query": mutation, "variables": {"data": test_data}},
    timeout=30,
)
print(f"  status: {r.status_code}")
print(f"  body: {r.text[:1500]}")

print("\nDone. If addCustomerPo SUCCEEDED, delete TEST-BASIC-AUTH-001 from ProShop UI.")
