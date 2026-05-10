#!/usr/bin/env python3
"""
Deep exploration of ProShop Message type to understand its structure
and determine if we can create/send messages via API.
"""

import os
import sys
import json
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


def run_graphql(token, query, variables=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(PROSHOP_GRAPHQL_URL, headers=headers, json=payload)
    return resp.json()


def main():
    print("=" * 70)
    print("Deep Exploration of ProShop Message Type")
    print("=" * 70)

    creds = load_credentials()
    token = get_token(creds)
    print("Token acquired.\n")

    # 1. Get full Message type fields
    print("[1] Full Message type structure:")
    print("-" * 50)
    result = run_graphql(token, """
    {
      __type(name: "Message") {
        name
        kind
        description
        fields(includeDeprecated: true) {
          name
          description
          type {
            name
            kind
            ofType { name kind ofType { name kind } }
          }
        }
      }
    }
    """)

    if result.get("data") and result["data"].get("__type"):
        msg_type = result["data"]["__type"]
        print(f"  Description: {msg_type.get('description', 'None')}")
        print(f"  Fields ({len(msg_type.get('fields', []))}):")
        for f in msg_type.get("fields", []):
            ftype = f.get("type", {})
            type_str = ftype.get("name") or ftype.get("kind", "?")
            if ftype.get("ofType"):
                inner = ftype["ofType"]
                type_str = f"{ftype.get('kind')}({inner.get('name', '?')})"
            print(f"    .{f['name']}: {type_str}")
            if f.get("description"):
                print(f"        -> {f['description'][:60]}...")

    # 2. Check MessageTo type (recipients)
    print("\n[2] MessageTo type (recipients):")
    print("-" * 50)
    result = run_graphql(token, """
    {
      __type(name: "MessageTo") {
        fields(includeDeprecated: true) {
          name
          type { name kind ofType { name } }
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        for f in result["data"]["__type"].get("fields", []):
            print(f"    .{f['name']}")

    # 3. Check for Input types (for mutations)
    print("\n[3] Searching for Message Input types:")
    print("-" * 50)
    input_types = ["MessageInput", "CreateMessageInput", "SendMessageInput",
                   "AddMessageInput", "NewMessageInput", "MessageCreateInput"]
    for t in input_types:
        result = run_graphql(token, f"""
        {{
          __type(name: "{t}") {{
            name
            kind
            inputFields {{
              name
              type {{ name kind }}
            }}
          }}
        }}
        """)
        if result.get("data") and result["data"].get("__type"):
            print(f"    FOUND: {t}")
            for f in result["data"]["__type"].get("inputFields", []):
                print(f"        .{f['name']}: {f.get('type', {}).get('name', '?')}")

    # 4. Look for message-related mutations more specifically
    print("\n[4] Searching mutations for 'message' or 'send':")
    print("-" * 50)
    result = run_graphql(token, """
    {
      __type(name: "Mutation") {
        fields(includeDeprecated: true) {
          name
          description
          args {
            name
            type { name kind ofType { name } }
          }
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        for f in result["data"]["__type"].get("fields", []):
            name = f["name"].lower()
            if "message" in name or "send" in name or "msg" in name or "notify" in name:
                print(f"    {f['name']}")
                if f.get("description"):
                    print(f"        {f['description'][:60]}")
                for arg in f.get("args", []):
                    print(f"        arg: {arg['name']}")

    # 5. Try querying actual messages to see structure
    print("\n[5] Trying to query existing messages:")
    print("-" * 50)
    result = run_graphql(token, """
    {
      messages(filter: { limit: 3 }) {
        total
        results {
          id
          subject
          body
          createdTime
          createdByPlainText
        }
      }
    }
    """)
    if result.get("errors"):
        print(f"    Query error: {result['errors'][0].get('message', 'unknown')[:80]}")
    elif result.get("data") and result["data"].get("messages"):
        msgs = result["data"]["messages"]
        print(f"    Total messages: {msgs.get('total', '?')}")
        for m in msgs.get("results", [])[:3]:
            print(f"    - [{m.get('id')}] {m.get('subject', 'No subject')[:40]}")
            print(f"        by: {m.get('createdByPlainText')} at {m.get('createdTime')}")

    # 6. Check UserInboxType for inbox functionality
    print("\n[6] Exploring UserInboxType:")
    print("-" * 50)
    result = run_graphql(token, """
    {
      __type(name: "UserInboxType") {
        fields(includeDeprecated: true) {
          name
          type { name kind }
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        for f in result["data"]["__type"].get("fields", []):
            print(f"    .{f['name']}: {f.get('type', {}).get('name', '?')}")

    # 7. Check TaskNote for notes/comments functionality
    print("\n[7] Exploring TaskNote (potential alternative):")
    print("-" * 50)
    result = run_graphql(token, """
    {
      __type(name: "TaskNote") {
        fields(includeDeprecated: true) {
          name
          type { name kind }
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        for f in result["data"]["__type"].get("fields", []):
            print(f"    .{f['name']}: {f.get('type', {}).get('name', '?')}")

    # 8. Look for updateTaskNotes mutation
    print("\n[8] Exploring UpdateTaskNotesInput:")
    print("-" * 50)
    result = run_graphql(token, """
    {
      __type(name: "UpdateTaskNotesInput") {
        inputFields {
          name
          type { name kind ofType { name } }
        }
      }
    }
    """)
    if result.get("data") and result["data"].get("__type"):
        for f in result["data"]["__type"].get("inputFields", []):
            print(f"    .{f['name']}: {f.get('type', {}).get('name', '?')}")

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)


if __name__ == "__main__":
    main()
