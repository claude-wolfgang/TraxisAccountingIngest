#!/usr/bin/env python3
"""
ProShop API Discovery Script
Explores the GraphQL schema to find time tracking, employee, and profitability fields.

Usage:
    python proshop_api_discovery.py

You'll be prompted for your client secret (not stored).
"""

import requests
import json
from datetime import datetime

def masked_input(prompt=""):
    """Get password input with asterisk masking (Windows compatible)."""
    import msvcrt
    print(prompt, end="", flush=True)
    password = []
    while True:
        char = msvcrt.getch()
        if char in (b'\r', b'\n'):  # Enter pressed
            print()
            break
        elif char == b'\x08':  # Backspace
            if password:
                password.pop()
                print('\b \b', end="", flush=True)
        elif char == b'\x03':  # Ctrl+C
            raise KeyboardInterrupt
        else:
            password.append(char.decode('utf-8'))
            print('*', end="", flush=True)
    return ''.join(password)

# === CONFIGURATION ===
CLIENT_ID = "3923-9C1C-7291"
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
SCOPES = "parts:rwdp+workorders:rwdp"

# Keywords to search for in the schema
KEYWORDS_OF_INTEREST = [
    "time", "clock", "labor", "hour", "employee", "worker", "user", "member",
    "profit", "cost", "revenue", "margin", "price", "rate",
    "operation", "workorder", "work_order", "wo", "job",
    "schedule", "shift", "attendance", "punch", "entry", "log"
]


def get_access_token(client_secret: str) -> str:
    """Authenticate and get access token."""
    print("\n🔐 Authenticating with ProShop...")
    
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "scope": SCOPES
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Authentication failed: {response.status_code}")
        print(response.text)
        raise Exception("Authentication failed")
    
    token = response.json().get("access_token")
    print("✅ Authentication successful")
    return token


def run_graphql_query(token: str, query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    response = requests.post(GRAPHQL_URL, headers=headers, json=payload)
    return response.json()


def get_full_schema(token: str) -> dict:
    """Run full introspection query."""
    print("\n📡 Running schema introspection...")
    
    introspection_query = """
    query IntrospectionQuery {
      __schema {
        queryType { name }
        mutationType { name }
        types {
          kind
          name
          description
          fields(includeDeprecated: true) {
            name
            description
            type {
              kind
              name
              ofType {
                kind
                name
                ofType {
                  kind
                  name
                }
              }
            }
            args {
              name
              type {
                kind
                name
              }
            }
          }
        }
      }
    }
    """
    
    result = run_graphql_query(token, introspection_query)
    
    if "errors" in result:
        print(f"⚠️  Introspection errors: {result['errors']}")
    
    if "data" in result and result["data"]:
        print("✅ Schema retrieved successfully")
        return result["data"]["__schema"]
    
    return None


def get_root_queries(token: str) -> list:
    """Get all available root queries."""
    print("\n📋 Fetching root queries...")
    
    query = """
    query {
      __schema {
        queryType {
          fields {
            name
            description
            type {
              kind
              name
              ofType { name }
            }
            args {
              name
              type { 
                kind
                name 
              }
            }
          }
        }
      }
    }
    """
    
    result = run_graphql_query(token, query)
    
    if "data" in result and result["data"]:
        return result["data"]["__schema"]["queryType"]["fields"]
    return []


def get_root_mutations(token: str) -> list:
    """Get all available root mutations."""
    print("📋 Fetching root mutations...")
    
    query = """
    query {
      __schema {
        mutationType {
          fields {
            name
            description
            args {
              name
              type { 
                kind
                name 
              }
            }
          }
        }
      }
    }
    """
    
    result = run_graphql_query(token, query)
    
    if "data" in result and result["data"] and result["data"]["__schema"]["mutationType"]:
        return result["data"]["__schema"]["mutationType"]["fields"]
    return []


def search_schema_for_keywords(schema: dict, keywords: list) -> dict:
    """Search through schema for types/fields matching keywords."""
    matches = {
        "types": [],
        "fields": []
    }
    
    if not schema or "types" not in schema:
        return matches
    
    for type_def in schema["types"]:
        type_name = type_def.get("name", "")
        type_desc = type_def.get("description", "") or ""
        
        # Skip internal types
        if type_name.startswith("__"):
            continue
        
        # Check type name and description
        type_name_lower = type_name.lower()
        type_desc_lower = type_desc.lower()
        
        matched_keywords = []
        for keyword in keywords:
            if keyword in type_name_lower or keyword in type_desc_lower:
                matched_keywords.append(keyword)
        
        if matched_keywords:
            matches["types"].append({
                "name": type_name,
                "description": type_desc,
                "matched_keywords": matched_keywords,
                "fields": type_def.get("fields") or []
            })
        
        # Also search individual fields
        if type_def.get("fields"):
            for field in type_def["fields"]:
                field_name = field.get("name", "")
                field_desc = field.get("description", "") or ""
                field_name_lower = field_name.lower()
                field_desc_lower = field_desc.lower()
                
                for keyword in keywords:
                    if keyword in field_name_lower or keyword in field_desc_lower:
                        matches["fields"].append({
                            "type": type_name,
                            "field": field_name,
                            "description": field_desc,
                            "keyword": keyword,
                            "field_type": get_type_name(field.get("type", {}))
                        })
                        break
    
    return matches


def get_type_name(type_obj: dict) -> str:
    """Extract readable type name from GraphQL type object."""
    if not type_obj:
        return "Unknown"
    
    kind = type_obj.get("kind", "")
    name = type_obj.get("name", "")
    
    if name:
        return name
    
    if kind == "NON_NULL" and type_obj.get("ofType"):
        return get_type_name(type_obj["ofType"]) + "!"
    
    if kind == "LIST" and type_obj.get("ofType"):
        return "[" + get_type_name(type_obj["ofType"]) + "]"
    
    return kind or "Unknown"


def get_type_details(token: str, type_name: str) -> dict:
    """Get detailed information about a specific type."""
    query = """
    query($name: String!) {
      __type(name: $name) {
        name
        kind
        description
        fields(includeDeprecated: true) {
          name
          description
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
    """
    
    result = run_graphql_query(token, query, {"name": type_name})
    
    if "data" in result and result["data"]:
        return result["data"]["__type"]
    return None


def try_sample_queries(token: str):
    """Try some common query patterns to see what works."""
    print("\n🧪 Testing sample queries...")
    
    test_queries = [
        ("employees", "query { employees { id name } }"),
        ("users", "query { users { id name } }"),
        ("members", "query { members { id name } }"),
        ("timeEntries", "query { timeEntries { id } }"),
        ("timeLogs", "query { timeLogs { id } }"),
        ("laborEntries", "query { laborEntries { id } }"),
        ("workOrders (first 1)", "query { workOrders(first: 1) { edges { node { id number } } } }"),
        ("workOrders (no pagination)", "query { workOrders { id number } }"),
        ("parts (first 1)", "query { parts(first: 1) { edges { node { partNumber } } } }"),
    ]
    
    results = []
    for name, query in test_queries:
        result = run_graphql_query(token, query)
        success = "data" in result and result["data"] is not None and not result.get("errors")
        has_data = False
        
        if success and result["data"]:
            # Check if any field has non-null data
            for key, value in result["data"].items():
                if value is not None:
                    has_data = True
                    break
        
        results.append({
            "name": name,
            "success": success,
            "has_data": has_data,
            "response": result
        })
        
        status = "✅" if success else "❌"
        data_status = " (has data)" if has_data else " (empty/null)" if success else ""
        print(f"  {status} {name}{data_status}")
    
    return results


def print_report(schema: dict, root_queries: list, root_mutations: list, 
                 keyword_matches: dict, sample_results: list):
    """Print a formatted report of findings."""
    
    print("\n" + "=" * 70)
    print("PROSHOP API DISCOVERY REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Root Queries
    print("\n## ROOT QUERIES AVAILABLE")
    print("-" * 40)
    if root_queries:
        for q in sorted(root_queries, key=lambda x: x["name"]):
            args = ", ".join([a["name"] for a in q.get("args", [])])
            args_str = f"({args})" if args else ""
            return_type = get_type_name(q.get("type", {}))
            desc = q.get("description", "")[:60] if q.get("description") else ""
            print(f"  • {q['name']}{args_str} → {return_type}")
            if desc:
                print(f"      {desc}")
    else:
        print("  No queries found or unable to retrieve")
    
    # Root Mutations
    print("\n## ROOT MUTATIONS AVAILABLE")
    print("-" * 40)
    if root_mutations:
        for m in sorted(root_mutations, key=lambda x: x["name"]):
            args = ", ".join([a["name"] for a in m.get("args", [])])
            desc = m.get("description", "")[:60] if m.get("description") else ""
            print(f"  • {m['name']}({args})")
            if desc:
                print(f"      {desc}")
    else:
        print("  No mutations found or unable to retrieve")
    
    # Keyword Matches - Types
    print("\n## TYPES MATCHING TIME/EMPLOYEE/PROFIT KEYWORDS")
    print("-" * 40)
    if keyword_matches["types"]:
        for t in keyword_matches["types"]:
            print(f"\n  📦 {t['name']}")
            print(f"     Keywords: {', '.join(t['matched_keywords'])}")
            if t["description"]:
                print(f"     Description: {t['description'][:100]}")
            if t["fields"]:
                print(f"     Fields ({len(t['fields'])}):")
                for f in t["fields"][:10]:  # Show first 10 fields
                    ftype = get_type_name(f.get("type", {}))
                    print(f"       - {f['name']}: {ftype}")
                if len(t["fields"]) > 10:
                    print(f"       ... and {len(t['fields']) - 10} more")
    else:
        print("  No matching types found")
    
    # Keyword Matches - Fields
    print("\n## FIELDS MATCHING TIME/EMPLOYEE/PROFIT KEYWORDS")
    print("-" * 40)
    if keyword_matches["fields"]:
        # Group by type
        by_type = {}
        for f in keyword_matches["fields"]:
            if f["type"] not in by_type:
                by_type[f["type"]] = []
            by_type[f["type"]].append(f)
        
        for type_name, fields in sorted(by_type.items()):
            if type_name.startswith("__"):
                continue
            print(f"\n  In {type_name}:")
            for f in fields:
                print(f"    • {f['field']}: {f['field_type']} (matched: {f['keyword']})")
    else:
        print("  No matching fields found")
    
    # Sample Query Results
    print("\n## SAMPLE QUERY RESULTS")
    print("-" * 40)
    for r in sample_results:
        status = "✅ Works" if r["success"] else "❌ Failed"
        data_note = " (has data)" if r["has_data"] else ""
        print(f"  {status}: {r['name']}{data_note}")
        
        if not r["success"] and "errors" in r["response"]:
            for err in r["response"]["errors"][:2]:
                msg = err.get("message", "Unknown error")[:80]
                print(f"      Error: {msg}")
    
    print("\n" + "=" * 70)
    print("END OF REPORT")
    print("=" * 70)


def save_full_schema(schema: dict, filename: str = "proshop_schema_full.json"):
    """Save the full schema to a JSON file for reference."""
    with open(filename, "w") as f:
        json.dump(schema, f, indent=2)
    print(f"\n💾 Full schema saved to {filename}")


def main():
    print("=" * 50)
    print("ProShop API Discovery Tool")
    print("=" * 50)
    print(f"\nTarget: {GRAPHQL_URL}")
    print(f"Client ID: {CLIENT_ID}")
    
    # OPTION 1: Hardcode secret for testing (delete after!)
    # Uncomment the line below and paste your secret:
    # client_secret = "0C6B59BA79E959342830EDA69E4294549A07EF14561DE3BDC16C6F47FCF8FD81"
    
    # OPTION 2: Masked input (comment out if using Option 1)
    client_secret = "0C6B59BA79E959342830EDA69E4294549A07EF14561DE3BDC16C6F47FCF8FD81"
    
    if not client_secret:
        print("❌ No client secret provided. Exiting.")
        return
    
    try:
        # Authenticate
        token = get_access_token(client_secret)
        
        # Get schema
        schema = get_full_schema(token)
        
        # Get root queries and mutations
        root_queries = get_root_queries(token)
        root_mutations = get_root_mutations(token)
        
        # Search for keywords
        keyword_matches = search_schema_for_keywords(schema, KEYWORDS_OF_INTEREST)
        
        # Try sample queries
        sample_results = try_sample_queries(token)
        
        # Print report
        print_report(schema, root_queries, root_mutations, keyword_matches, sample_results)
        
        # Save full schema
        if schema:
            save_full_schema(schema)
        
        print("\n✅ Discovery complete!")
        print("\nNext steps:")
        print("  1. Review the matching types and fields above")
        print("  2. Check proshop_schema_full.json for complete schema")
        print("  3. Share the output with Claude for help building queries")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
