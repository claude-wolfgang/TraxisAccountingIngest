#!/usr/bin/env python3
"""
ProShop API Messaging Discovery
Traxis Manufacturing

Explores the ProShop GraphQL API to find any messaging, notification,
or communication capabilities.
"""

import os
import sys
import json
import requests
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

PROSHOP_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
PROSHOP_GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
ENV_FILE = Path(r"C:\Users\TRAXIS\.traxis.env")

# Types to probe for messaging capabilities
MESSAGE_TYPES = [
    "Message", "Messages", "MessageInput", "CreateMessageInput", "SendMessageInput",
    "Notification", "Notifications", "NotificationInput",
    "Note", "Notes", "NoteInput", "CreateNoteInput",
    "Comment", "Comments", "CommentInput",
    "Alert", "Alerts", "AlertInput",
    "Communication", "Communications",
    "Inbox", "InboxMessage",
    "UserMessage", "SystemMessage", "ShopMessage",
    "Bulletin", "Bulletins", "BulletinInput",
    "Announcement", "Announcements",
    "Email", "EmailInput",
]

# Keywords to search for in field/type names
MESSAGING_KEYWORDS = [
    "message", "msg", "notification", "notify", "alert", "chat",
    "comment", "note", "send", "broadcast", "inbox", "mail",
    "email", "announce", "bulletin", "communication", "dispatch", "memo", "log"
]


# ── Credential Loading ───────────────────────────────────────────────────────

def load_credentials():
    """Load ProShop credentials from .traxis.env file."""
    if not ENV_FILE.exists():
        print(f"ERROR: Credentials file not found: {ENV_FILE}")
        sys.exit(1)

    creds = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                creds[key.strip()] = value.strip()

    required = ["PROSHOP_CLIENT_ID", "PROSHOP_CLIENT_SECRET", "PROSHOP_SCOPE"]
    missing = [k for k in required if k not in creds]
    if missing:
        print(f"ERROR: Missing credentials: {missing}")
        sys.exit(1)

    return creds


# ── Token Acquisition ────────────────────────────────────────────────────────

def get_access_token(creds):
    """Get OAuth 2.0 access token from ProShop."""
    print("\n[1] Acquiring access token...")

    data = {
        "grant_type": "client_credentials",
        "client_id": creds["PROSHOP_CLIENT_ID"],
        "client_secret": creds["PROSHOP_CLIENT_SECRET"],
        "scope": creds["PROSHOP_SCOPE"],
    }

    resp = requests.post(PROSHOP_TOKEN_URL, data=data)

    if resp.status_code != 200:
        print(f"ERROR: Token request failed ({resp.status_code})")
        print(resp.text)
        sys.exit(1)

    token_data = resp.json()
    if "access_token" not in token_data:
        print(f"ERROR: No access_token in response: {token_data}")
        sys.exit(1)

    print(f"    Token acquired (scope: {creds['PROSHOP_SCOPE']})")
    return token_data["access_token"]


# ── GraphQL Queries ──────────────────────────────────────────────────────────

def run_graphql(token, query, variables=None):
    """Execute a GraphQL query against ProShop API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(PROSHOP_GRAPHQL_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}", "body": resp.text}

    return resp.json()


def get_query_fields(token):
    """Get all root Query fields."""
    query = """
    {
      __type(name: "Query") {
        fields(includeDeprecated: true) {
          name
          description
          type { name kind ofType { name kind } }
          args { name type { name kind } }
        }
      }
    }
    """
    return run_graphql(token, query)


def get_mutation_fields(token):
    """Get all Mutation fields."""
    query = """
    {
      __type(name: "Mutation") {
        fields(includeDeprecated: true) {
          name
          description
          args {
            name
            type { name kind ofType { name kind } }
          }
        }
      }
    }
    """
    return run_graphql(token, query)


def probe_type(token, type_name):
    """Probe a specific type by name."""
    query = f"""
    {{
      __type(name: "{type_name}") {{
        name
        kind
        description
        fields(includeDeprecated: true) {{
          name
          type {{ name kind ofType {{ name kind }} }}
        }}
        inputFields {{
          name
          type {{ name kind ofType {{ name kind }} }}
        }}
      }}
    }}
    """
    return run_graphql(token, query)


def get_all_types(token):
    """Try to get full schema type list (may fail)."""
    query = """
    {
      __schema {
        types {
          name
          kind
        }
      }
    }
    """
    return run_graphql(token, query)


# ── Analysis ─────────────────────────────────────────────────────────────────

def filter_messaging_related(items, name_key="name"):
    """Filter items that might be messaging-related."""
    results = []
    for item in items:
        name = item.get(name_key, "").lower()
        for keyword in MESSAGING_KEYWORDS:
            if keyword in name:
                results.append(item)
                break
    return results


def format_type(t):
    """Format a GraphQL type for display."""
    if not t:
        return "?"
    kind = t.get("kind", "")
    name = t.get("name", "")
    if kind == "NON_NULL":
        inner = t.get("ofType", {})
        return f"{format_type(inner)}!"
    elif kind == "LIST":
        inner = t.get("ofType", {})
        return f"[{format_type(inner)}]"
    return name or kind


# ── Main Discovery ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("ProShop API Messaging Discovery")
    print("=" * 70)

    creds = load_credentials()
    token = get_access_token(creds)

    findings = {
        "query_fields": [],
        "mutations": [],
        "messaging_types_found": [],
        "messaging_related_queries": [],
        "messaging_related_mutations": [],
        "all_types": [],
    }

    # ── Step 1: Get Query Fields ─────────────────────────────────────────
    print("\n[2] Fetching Query fields...")
    result = get_query_fields(token)

    if "errors" in result:
        print(f"    ERROR: {result['errors']}")
    elif "data" in result and result.get("data") and result["data"].get("__type"):
        fields = result["data"]["__type"].get("fields", [])
        findings["query_fields"] = [f["name"] for f in fields]
        print(f"    Found {len(fields)} Query fields")

        messaging_queries = filter_messaging_related(fields)
        findings["messaging_related_queries"] = messaging_queries
        if messaging_queries:
            print(f"    *** MESSAGING RELATED: {[f['name'] for f in messaging_queries]}")

    # ── Step 2: Get Mutations ────────────────────────────────────────────
    print("\n[3] Fetching Mutation fields...")
    result = get_mutation_fields(token)

    if "errors" in result:
        print(f"    ERROR: {result['errors']}")
    elif "data" in result and result.get("data") and result["data"].get("__type"):
        fields = result["data"]["__type"].get("fields", [])
        findings["mutations"] = [f["name"] for f in fields]
        print(f"    Found {len(fields)} Mutations")

        messaging_mutations = filter_messaging_related(fields)
        findings["messaging_related_mutations"] = messaging_mutations
        if messaging_mutations:
            print(f"    *** MESSAGING RELATED: {[f['name'] for f in messaging_mutations]}")

    # ── Step 3: Probe Message-Related Types ──────────────────────────────
    print("\n[4] Probing message-related types...")
    for type_name in MESSAGE_TYPES:
        result = probe_type(token, type_name)
        if "data" in result and result.get("data") and result["data"].get("__type"):
            t = result["data"]["__type"]
            findings["messaging_types_found"].append(t)
            print(f"    FOUND: {type_name} ({t.get('kind', '?')})")
            if t.get("fields"):
                for f in t["fields"][:5]:
                    print(f"           .{f['name']}: {format_type(f.get('type'))}")
                if len(t["fields"]) > 5:
                    print(f"           ... and {len(t['fields']) - 5} more fields")

    if not findings["messaging_types_found"]:
        print("    No messaging types found.")

    # ── Step 4: Try Full Schema Dump ─────────────────────────────────────
    print("\n[5] Attempting full schema dump...")
    result = get_all_types(token)

    if "errors" in result:
        print(f"    Schema dump failed (expected): {result.get('errors', [{}])[0].get('message', 'unknown')[:50]}...")
    elif "data" in result and result.get("data") and result["data"].get("__schema"):
        types = result["data"]["__schema"].get("types", [])
        findings["all_types"] = [t["name"] for t in types]
        print(f"    Found {len(types)} types in schema")

        # Search for messaging-related types
        messaging_types = [t for t in types if any(kw in t["name"].lower() for kw in MESSAGING_KEYWORDS)]
        if messaging_types:
            print(f"    MESSAGING-RELATED TYPES: {[t['name'] for t in messaging_types]}")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    has_messaging = bool(
        findings["messaging_types_found"] or
        findings["messaging_related_queries"] or
        findings["messaging_related_mutations"]
    )

    if has_messaging:
        print("\n[OK] MESSAGING CAPABILITIES FOUND!")
        if findings["messaging_related_queries"]:
            print("\n  Queries:")
            for q in findings["messaging_related_queries"]:
                print(f"    - {q['name']}: {format_type(q.get('type'))}")
        if findings["messaging_related_mutations"]:
            print("\n  Mutations:")
            for m in findings["messaging_related_mutations"]:
                args = ", ".join(f"{a['name']}: {format_type(a.get('type'))}" for a in m.get("args", []))
                print(f"    - {m['name']}({args})")
        if findings["messaging_types_found"]:
            print("\n  Types:")
            for t in findings["messaging_types_found"]:
                print(f"    - {t['name']} ({t.get('kind')})")
    else:
        print("\n[X] NO MESSAGING CAPABILITIES FOUND IN API")
        print("\n  The ProShop GraphQL API does not expose messaging endpoints.")
        print("  Will proceed with email/HTML report delivery instead.")

    print("\n  All Query fields:")
    for name in sorted(findings["query_fields"]):
        print(f"    - {name}")

    print("\n  All Mutations:")
    for name in sorted(findings["mutations"]):
        print(f"    - {name}")

    # Save findings to JSON
    output_path = Path(__file__).parent / "proshop_api_discovery.json"
    with open(output_path, "w") as f:
        json.dump(findings, f, indent=2, default=str)
    print(f"\n  Detailed findings saved to: {output_path}")

    return has_messaging, findings


if __name__ == "__main__":
    has_messaging, findings = main()
    sys.exit(0 if has_messaging else 1)
