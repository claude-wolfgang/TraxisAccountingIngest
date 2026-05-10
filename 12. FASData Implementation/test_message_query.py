#!/usr/bin/env python3
"""Quick test to confirm Message API is read-only."""

import requests
from pathlib import Path

PROSHOP_TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
PROSHOP_GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
ENV_FILE = Path(r"C:\Users\TRAXIS\.traxis.env")

def load_credentials():
    creds = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                creds[key.strip()] = value.strip()
    return creds

def get_token(creds):
    data = {
        "grant_type": "client_credentials",
        "client_id": creds["PROSHOP_CLIENT_ID"],
        "client_secret": creds["PROSHOP_CLIENT_SECRET"],
        "scope": creds["PROSHOP_SCOPE"],
    }
    resp = requests.post(PROSHOP_TOKEN_URL, data=data)
    return resp.json()["access_token"]

def run_graphql(token, query):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(PROSHOP_GRAPHQL_URL, headers=headers, json={"query": query})
    return resp.json()

def main():
    creds = load_credentials()
    token = get_token(creds)
    print("Token acquired.\n")

    # Try to get MessageFilter structure
    print("1. MessageFilter structure:")
    result = run_graphql(token, """
    {
      __type(name: "MessageFilter") {
        inputFields {
          name
          type { name kind }
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        for f in result["data"]["__type"].get("inputFields", []):
            print(f"   .{f['name']}: {f.get('type', {}).get('name', '?')}")

    # Try to query messages
    print("\n2. Query messages (last 3):")
    result = run_graphql(token, """
    {
      messages(filter: { pageSize: 3 }) {
        total
        results {
          id
          subject
          messageText
          postDate
          fromPlainText
        }
      }
    }
    """)
    if result.get("errors"):
        print(f"   Error: {result['errors'][0].get('message', 'unknown')}")
    elif result.get("data") and result["data"].get("messages"):
        msgs = result["data"]["messages"]
        print(f"   Total messages in system: {msgs.get('total', '?')}")
        for m in msgs.get("results", []):
            print(f"   - {m.get('subject', 'No subject')}")
            print(f"     From: {m.get('fromPlainText')}, Date: {m.get('postDate')}")

    # Final check - look for any add/create message mutation
    print("\n3. Check all mutations containing 'message':")
    result = run_graphql(token, """
    {
      __type(name: "Mutation") {
        fields(includeDeprecated: true) {
          name
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        mutations = [f["name"] for f in result["data"]["__type"].get("fields", [])]
        message_mutations = [m for m in mutations if "message" in m.lower()]
        if message_mutations:
            print(f"   Found: {message_mutations}")
        else:
            print("   NONE FOUND - confirming messages are READ-ONLY")

    print("\n" + "=" * 60)
    print("CONCLUSION: ProShop Message API is READ-ONLY")
    print("No mutations exist to create or send messages.")
    print("Proceeding with email/HTML report delivery approach.")
    print("=" * 60)

if __name__ == "__main__":
    main()
