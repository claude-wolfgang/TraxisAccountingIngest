"""Check ProShop API user permissions for the accounting connector.

Uses the main PROSHOP client (which has users:r) to query the API user
that the accounting connector maps to, and inspect its moduleAccess
and permissions fields.
"""
import sys, json, os, time, requests
from pathlib import Path

# Load env
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
    result = r.json()
    if "errors" in result:
        print(f"  GraphQL Error: {result['errors'][0]['message']}")
        return result
    return result.get("data", {})


# --- Step 1: Introspect the UserModuleAccess and UserPermissions types ---
print("=" * 60)
print("STEP 1: Introspect UserModuleAccess and UserPermissions types")
print("=" * 60)

# Use main proshop client (has users:r)
token = get_token("PROSHOP_CLIENT_ID", "PROSHOP_CLIENT_SECRET", "PROSHOP_SCOPE")

for type_name in ["UserModuleAccess", "UserPermissions"]:
    print(f"\n--- {type_name} ---")
    # Use raw request to avoid includeDeprecated issue
    r = requests.post(
        GQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": '{ __type(name: "' + type_name + '") { kind fields(includeDeprecated: false) { name type { name kind ofType { name kind ofType { name kind ofType { name } } } } } } }'},
        timeout=30,
    )
    data = r.json().get("data", {})
    t = data.get("__type")
    if not t:
        print("  (type not found)")
        continue
    print(f"  kind: {t['kind']}")
    for f in (t.get("fields") or t.get("inputFields") or []):
        ft = f["type"]
        tname = ft.get("name") or f"{ft.get('kind','?')}({ft.get('ofType',{}).get('name','?')})"
        print(f"    {f['name']:>35}  {tname}")

# --- Step 2: List all users and find the API connector user ---
print("\n" + "=" * 60)
print("STEP 2: List users (looking for API / connector accounts)")
print("=" * 60)

gql = """
{
  users(pageSize: 50) {
    records {
      id
      firstName
      lastName
      emailAddress
      licenseType
      isActive
    }
  }
}"""
data = query(token, gql)
users = data.get("users", {}).get("records", [])
print(f"\nFound {len(users)} users:")
for u in users:
    marker = ""
    name = f"{u.get('firstName','')} {u.get('lastName','')}".strip()
    lt = u.get("licenseType", "")
    if "api" in (lt or "").lower() or "api" in name.lower() or "connector" in name.lower() or "auth" in name.lower():
        marker = " <-- POSSIBLE API USER"
    active = "active" if u.get("isActive") else "inactive"
    print(f"  #{u.get('id','?'):>5}  {name:<35}  type={lt:<15}  {active}{marker}")

# --- Step 3: Query moduleAccess for API-like users ---
print("\n" + "=" * 60)
print("STEP 3: Query moduleAccess for API/connector users")
print("=" * 60)

# Try to get detailed permissions for users that look like API accounts
api_users = [u for u in users if
             "api" in (u.get("licenseType") or "").lower() or
             "api" in f"{u.get('firstName','')} {u.get('lastName','')}".lower() or
             "connector" in f"{u.get('firstName','')} {u.get('lastName','')}".lower() or
             "auth" in f"{u.get('firstName','')} {u.get('lastName','')}".lower()]

if not api_users:
    print("  No obvious API users found. Querying first 5 users for moduleAccess...")
    api_users = users[:5]

for u in api_users:
    uid = u.get("id")
    name = f"{u.get('firstName','')} {u.get('lastName','')}".strip()
    print(f"\n--- User #{uid}: {name} ---")

    # Query all users and filter client-side (no id filter available)
    gql = """
    {
      users(pageSize: 50) {
        records {
          id
          firstName
          lastName
          moduleAccess { moduleName readAccess writeAccess deleteAccess prefsAccess }
        }
      }
    }"""
    data = query(token, gql)
    all_records = data.get("users", {}).get("records", [])
    records = [r for r in all_records if r.get("id") == uid]
    if not records:
        print(f"  (user #{uid} not found in results)")
        continue

    rec = records[0]
    ma = rec.get("moduleAccess")
    perms = rec.get("permissions")

    if ma:
        print(f"  moduleAccess ({len(ma)} entries):")
        # Show all entries for the API user
        for entry in ma:
            mod = entry.get("moduleName", "")
            r = entry.get("readAccess")
            w = entry.get("writeAccess")
            d = entry.get("deleteAccess")
            p = entry.get("prefsAccess")
            marker = ""
            if "customer" in mod.lower() or "po" in mod.lower() or "bill" in mod.lower() or "invoice" in mod.lower() or "packing" in mod.lower() or "quote" in mod.lower() or "purchase" in mod.lower():
                marker = "  <-- ACCOUNTING"
            print(f"    {mod:<35}  read={r}  write={w}  delete={d}  prefs={p}{marker}")
        print()
    else:
        print("  moduleAccess: (null or empty)")

    if perms:
        print(f"  permissions: {json.dumps(perms, indent=4)}")
    else:
        print("  permissions: (null or empty)")

# --- Step 4: Try addCustomerPo with accounting client to capture exact error ---
print("\n" + "=" * 60)
print("STEP 4: Test addCustomerPo with accounting client (expect error)")
print("=" * 60)

try:
    acct_token = get_token("ACCOUNTING_CLIENT_ID", "ACCOUNTING_CLIENT_SECRET", "ACCOUNTING_SCOPE")
    gql = """
    mutation AddCustomerPo($data: AddCustomerPoInput!) {
      addCustomerPo(data: $data) { poId proshopUrl }
    }"""
    # Minimal test payload
    test_data = {
        "client": "TEST-DO-NOT-USE",
        "clientPONumber": "TEST-PERM-CHECK-001",
        "dateEntered": "2026-04-11",
        "year": "2026",
    }
    print(f"  Sending test mutation with payload: {json.dumps(test_data)}")
    result = query(acct_token, gql, {"data": test_data})
    if "errors" not in result:
        print(f"  SUCCESS (unexpected!): {json.dumps(result, indent=2)}")
        print("  NOTE: If this succeeded, delete the test PO from ProShop!")
    else:
        print(f"  Expected error captured above.")
except Exception as e:
    print(f"  Exception: {e}")

print("\nDone.")
