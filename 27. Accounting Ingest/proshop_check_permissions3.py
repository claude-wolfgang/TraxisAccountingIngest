"""Compare ALL permission flags between User #010 (API) and User #001 (admin)."""
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

token = requests.post(TOKEN_URL, data={
    "grant_type": "client_credentials",
    "client_id": env["PROSHOP_CLIENT_ID"],
    "client_secret": env["PROSHOP_CLIENT_SECRET"],
    "scope": env["PROSHOP_SCOPE"],
}).json()["access_token"]

# First get ALL permission field names from introspection
r = requests.post(GQL_URL,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"query": '{ __type(name: "UserPermissions") { fields(includeDeprecated: false) { name } } }'},
    timeout=30)
fields = [f["name"] for f in r.json()["data"]["__type"]["fields"]]
print(f"Total permission fields: {len(fields)}\n")

# Build a query for all fields
fields_str = "\n        ".join(fields)
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
}""" % fields_str

r = requests.post(GQL_URL,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"query": gql},
    timeout=30)
result = r.json()
if "errors" in result:
    print(f"Error: {result['errors'][0]['message']}")
    sys.exit(1)

users = {u["id"]: u for u in result["data"]["users"]["records"]}

api_user = users.get("010", {})
admin_user = users.get("001", {})

api_perms = api_user.get("permissions", {}) or {}
admin_perms = admin_user.get("permissions", {}) or {}

print("Permissions where #010 (API) differs from #001 (Tom/Admin):")
print(f"{'Permission':<65} {'#010':>6} {'#001':>6}")
print("-" * 80)

diffs = []
for field in sorted(fields):
    api_val = api_perms.get(field)
    admin_val = admin_perms.get(field)
    if api_val != admin_val:
        diffs.append((field, api_val, admin_val))
        print(f"  {field:<63} {str(api_val):>6} {str(admin_val):>6}")

print(f"\n{len(diffs)} differences out of {len(fields)} total permissions")

# Also show all permissions that are True for admin but False for API
print(f"\nPermissions admin has that API user lacks (True vs False):")
for field, api_val, admin_val in diffs:
    if admin_val == True and api_val == False:
        print(f"  - {field}")

print("\nDone.")
