"""Deeper permission check: query UserPermissions and test with fresh token."""
import sys, json, requests
from pathlib import Path

env = {}
env_path = Path(r"C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\.traxis.env")
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GQL_URL = "https://traxismfg.adionsystems.com/api/graphql"


def get_token(client_id_key, client_secret_key, scope_key):
    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": env[client_id_key],
        "client_secret": env[client_secret_key],
        "scope": env[scope_key],
    })
    r.raise_for_status()
    return r.json()["access_token"]


def query(token, gql, variables=None):
    r = requests.post(
        GQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": gql, "variables": variables or {}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# --- Step 1: Get fresh tokens ---
print("Getting fresh tokens...")
main_token = get_token("PROSHOP_CLIENT_ID", "PROSHOP_CLIENT_SECRET", "PROSHOP_SCOPE")
acct_token = get_token("ACCOUNTING_CLIENT_ID", "ACCOUNTING_CLIENT_SECRET", "ACCOUNTING_SCOPE")
print("  Done.\n")

# --- Step 2: Query User #010 permissions (the detailed boolean flags) ---
print("=" * 60)
print("User #010 detailed permissions")
print("=" * 60)

# Pick the permission fields most likely related to record creation
permission_fields = """
    addInvoicingInformation
    allowCrucialEdits
    allowEstimatingEdits
    allowEditAndDisplayContactsNotes
    isSystemAdministrator
    isSecurityAdmin
    isThisUserBlessed
    isDeveloper
    byPassOrderStatusProtection
    allowUserToEditRecordsInCarts
"""

gql = """
{
  users(pageSize: 50) {
    records {
      id
      firstName
      lastName
      permissions {
        %s
      }
    }
  }
}""" % permission_fields

result = query(main_token, gql)
if "errors" in result:
    print(f"  Error: {result['errors'][0]['message']}")
else:
    users = result.get("data", {}).get("users", {}).get("records", [])
    for u in users:
        if u.get("id") == "010":
            print(f"  User #010: {u['firstName']} {u['lastName']}")
            perms = u.get("permissions") or {}
            for k, v in perms.items():
                print(f"    {k:<45}  {v}")
            if not perms:
                print("    (permissions is null/empty)")
            break

# --- Step 3: Compare with a known working user (e.g., Tom #001 or an admin) ---
print(f"\n  Comparison - User #001 (Tom Buerkle):")
for u in users:
    if u.get("id") == "001":
        perms = u.get("permissions") or {}
        for k, v in perms.items():
            print(f"    {k:<45}  {v}")
        break

print(f"\n  Comparison - User #004 (Zach Clarke, LGS Admin):")
for u in users:
    if u.get("id") == "004":
        perms = u.get("permissions") or {}
        for k, v in perms.items():
            print(f"    {k:<45}  {v}")
        break

# --- Step 4: Try addCustomerPo with FRESH accounting token ---
print("\n" + "=" * 60)
print("Test addCustomerPo with FRESH accounting token")
print("=" * 60)

gql_mut = """
mutation AddCustomerPo($data: AddCustomerPoInput!) {
  addCustomerPo(data: $data) { poId proshopUrl }
}"""

test_data = {
    "client": "TEST-DO-NOT-USE",
    "clientPONumber": "TEST-PERM-CHECK-002",
    "dateEntered": "2026-04-11",
    "year": "2026",
}
print(f"  Payload: {json.dumps(test_data)}")
result = query(acct_token, gql_mut, {"data": test_data})
if "errors" in result:
    print(f"  ERROR: {result['errors'][0]['message']}")
else:
    print(f"  SUCCESS: {json.dumps(result.get('data', {}), indent=2)}")
    print("  NOTE: Delete this test PO from ProShop!")

# --- Step 5: Try with the MAIN proshop client for comparison ---
print("\n" + "=" * 60)
print("Test addCustomerPo with MAIN proshop client (for comparison)")
print("=" * 60)
print("  (main client scope does not include customerpos - expect scope error)")
result = query(main_token, gql_mut, {"data": {
    "client": "TEST-DO-NOT-USE",
    "clientPONumber": "TEST-PERM-CHECK-003",
    "dateEntered": "2026-04-11",
    "year": "2026",
}})
if "errors" in result:
    print(f"  ERROR: {result['errors'][0]['message']}")
else:
    print(f"  SUCCESS: {json.dumps(result.get('data', {}), indent=2)}")
    print("  NOTE: Delete this test PO from ProShop!")

print("\nDone.")
