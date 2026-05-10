"""
COTS Crib Kiosk — Phase 0: Schema & Data Discovery
Run on any machine that can reach traxismfg.adionsystems.com

    python cots_discovery.py

Prints everything to the terminal — just paste the output back to Claude.
"""

import requests
import json
import sys

TOKEN_URL   = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"

CLIENT_ID     = "E88F-BE23-AC08"
CLIENT_SECRET = "E190F2AD406FA4DCBEC5F867CC055142A46E75E6D4728328A7A64E4EA897C110"
SCOPES_TO_TRY = [
    "ots:rwdp+cots:rwdp+parts:r+users:r",
    "ots:rwdp+cots:rwdp+users:r",
    "cots:rwdp+users:r",
]

# ── Auth ──────────────────────────────────────────────────────────────────────
print("=== AUTH ===")
token = None
for scope in SCOPES_TO_TRY:
    auth = requests.post(TOKEN_URL, data={
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         scope,
    })
    if auth.status_code == 200:
        token = auth.json()["access_token"]
        print(f"Scope: {scope}")
        print(f"Status: {auth.status_code}")
        print(f"Token: {token[:24]}...\n")
        break
    else:
        print(f"  Scope '{scope}' -> {auth.status_code}")

if not token:
    print("All scopes failed. Exiting.")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def gql(query):
    r = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        print("  GraphQL errors:")
        for e in body["errors"]:
            print(f"    - {e.get('message', e)}")
    return body

def type_label(t):
    """Build a readable type string from a GraphQL introspection type."""
    name = t.get("name")
    if name:
        return name
    kind = t.get("kind")
    inner = t.get("ofType") or {}
    inner_name = inner.get("name") or inner.get("kind") or "?"
    if kind == "NON_NULL":
        return f"{inner_name}!"
    if kind == "LIST":
        return f"[{inner_name}]"
    return inner_name

# ── 1. COTS object fields ────────────────────────────────────────────────────
print("=== 1. COTS OBJECT FIELDS ===")
result = gql("""
{
  __type(name: "COTS") {
    name
    fields(includeDeprecated: true) {
      name
      type { name kind ofType { name kind ofType { name kind } } }
    }
  }
}
""")

cots_type = (result.get("data") or {}).get("__type")
if cots_type:
    for f in cots_type["fields"]:
        print(f"  {f['name']:45s} {type_label(f['type'])}")
else:
    print("  __type(name:\"COTS\") returned null — listing all COTS-related types instead:")
    all_types = gql('{ __schema { types { name kind } } }')
    types_data = (all_types.get("data") or {}).get("__schema", {}).get("types", [])
    for t in types_data:
        n = t["name"].lower()
        if any(x in n for x in ["cots", "crib", "consumable"]):
            print(f"    {t['name']:55s} {t['kind']}")

# ── 2. COTS input-type fields (AddCOTSInput, UpdateCOTSInput, etc.) ──────────
print("\n=== 2. COTS INPUT TYPES ===")
input_names = [
    "AddCOTSInput",
    "UpdateCOTSInput",
    "OverwriteCOTSInput",
    "COTSFilter",
    "COTSQuery",
]
for inp_name in input_names:
    result = gql(f'{{ __type(name: "{inp_name}") {{ name inputFields {{ name type {{ name kind ofType {{ name kind ofType {{ name kind }} }} }} }} }} }}')
    inp = (result.get("data") or {}).get("__type")
    if inp:
        print(f"\n  {inp['name']}:")
        for f in inp["inputFields"]:
            print(f"    {f['name']:42s} {type_label(f['type'])}")
    else:
        print(f"\n  {inp_name}: not found")

# ── 3. COTS mutations ────────────────────────────────────────────────────────
print("\n=== 3. COTS MUTATIONS ===")
try:
    result = gql("""
    {
      __schema {
        mutationType {
          fields(includeDeprecated: true) {
            name
            args {
              name
              type { name kind ofType { name kind } }
            }
          }
        }
      }
    }
    """)
    mut_type = (result.get("data") or {}).get("__schema", {}).get("mutationType")
    if mut_type:
        mutations = mut_type.get("fields", [])
        cots_mutations = [m for m in mutations if "cots" in m["name"].lower()]
        if cots_mutations:
            for m in cots_mutations:
                print(f"\n  {m['name']}:")
                for a in m["args"]:
                    print(f"    {a['name']:35s} {type_label(a['type'])}")
        else:
            print("  No COTS mutations found in schema.")
    else:
        print("  mutationType is null (introspection may be restricted).")
except Exception as ex:
    print(f"  Error querying mutations: {ex}")

# ── 4. All root query & mutation field names ─────────────────────────────────
print("\n=== 4. ALL ROOT QUERY FIELDS ===")
try:
    result = gql("""
    {
      __schema {
        queryType {
          name
          fields(includeDeprecated: true) {
            name
            args {
              name
              type { name kind ofType { name kind } }
            }
          }
        }
      }
    }
    """)
    q_type = (result.get("data") or {}).get("__schema", {}).get("queryType")
    if q_type:
        print(f"  Query type name: {q_type['name']}")
        for q in q_type.get("fields", []):
            args_str = ", ".join(a["name"] for a in q.get("args", []))
            print(f"    {q['name']:45s} args: ({args_str})")
    else:
        print("  queryType is null.")
except Exception as ex:
    print(f"  Error: {ex}")

# ── 5. Probe cotsItems / cotsItem args ────────────────────────────────────────
print("\n=== 5. PROBE cotsItems & cotsItem ARGS ===")

# Introspect specific fields to learn their arguments
for field_name in ["cotsItems", "cotsItem"]:
    print(f"\n  --- {field_name} ---")
    result = gql(f"""
    {{
      __type(name: "Query") {{
        fields(includeDeprecated: true) {{
          name
          args {{
            name
            type {{ name kind ofType {{ name kind ofType {{ name kind }} }} }}
          }}
          type {{ name kind ofType {{ name kind ofType {{ name kind }} }} }}
        }}
      }}
    }}
    """)
    q_type = (result.get("data") or {}).get("__type")
    if q_type:
        for f in q_type["fields"]:
            if f["name"] == field_name:
                print(f"    Return type: {type_label(f['type'])}")
                if f["args"]:
                    for a in f["args"]:
                        print(f"    arg: {a['name']:30s} {type_label(a['type'])}")
                else:
                    print("    (no arguments)")
                break
        else:
            print(f"    Field '{field_name}' not found in Query type.")
    else:
        # Try alternate root type names
        for root_name in ["RootQuery", "QueryRoot", "Root"]:
            result2 = gql(f"""
            {{
              __type(name: "{root_name}") {{
                fields(includeDeprecated: true) {{
                  name
                  args {{
                    name
                    type {{ name kind ofType {{ name kind }} }}
                  }}
                  type {{ name kind ofType {{ name kind }} }}
                }}
              }}
            }}
            """)
            rt = (result2.get("data") or {}).get("__type")
            if rt:
                print(f"    Found root type: {root_name}")
                for f in rt["fields"]:
                    if f["name"] == field_name:
                        print(f"    Return type: {type_label(f['type'])}")
                        for a in f["args"]:
                            print(f"    arg: {a['name']:30s} {type_label(a['type'])}")
                        break
                break
        else:
            print(f"    Could not find root query type to introspect {field_name}.")

# ── 6. Live COTS records ─────────────────────────────────────────────────────
print("\n=== 6. LIVE COTS RECORDS (first 3) ===")
try:
    result = gql("""
    {
      cotsItems(pageSize: 3) {
        records {
          otsId
          legacyId
          number
          aka
          type
          subclass
          description
          location
          quantity
          inventoryQuantity
          material
          partPlainText
          thread
          od
          length
          units
          isSerialized
          createdTime
          lastModifiedTime
        }
      }
    }
    """)
    data = (result.get("data") or {}).get("cotsItems")
    if data and data.get("records"):
        print(json.dumps(data, indent=2))
    else:
        print("  No records returned.")
        print(json.dumps(result, indent=2))
except Exception as ex:
    print(f"  Error: {ex}")

print("\n=== DONE ===")
