#!/usr/bin/env python3
"""
ProShop Scope Tester
Tries different scope combinations to find what works.
"""

import requests

CLIENT_ID = "3923-9C1C-7291"
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"

# Different scope combinations to try
SCOPE_TESTS = [
    "parts:rwdp+workorders:rwdp",  # Original - should work
    "parts:rwdp+workorders:rwdp+users:r",  # Add users only
    "parts:rwdp+workorders:rwdp+toolpots:r",  # Add toolpots only (lowercase)
    "parts:rwdp+workorders:rwdp+toolPots:r",  # Add toolPots only (camelCase)
    "parts:rwdp+workorders:rwdp+users:r+toolpots:r",  # Both lowercase
    "parts:rwdp+workorders:rwdp+users:r+toolPots:r",  # Mixed case
    "parts:r+workorders:r+users:r+toolpots:r",  # All read-only
    "parts:r+workorders:r+users:r",  # Read only, no toolpots
]

def test_scope(client_secret: str, scope: str) -> bool:
    """Test if a scope works."""
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "scope": scope
        }
    )
    
    if response.status_code == 200:
        return True, response.json().get("access_token")
    else:
        return False, response.json().get("error_message", response.text)

def main():
    print("=" * 60)
    print("ProShop Scope Tester")
    print("=" * 60)
    
    client_secret = input("\nClient secret: ").strip()
    
    if not client_secret:
        print("No secret provided.")
        return
    
    print("\nTesting scope combinations...\n")
    
    working_scopes = []
    
    for scope in SCOPE_TESTS:
        success, result = test_scope(client_secret, scope)
        status = "✅" if success else "❌"
        print(f"{status} {scope}")
        if not success:
            print(f"   Error: {result[:80]}")
        else:
            working_scopes.append(scope)
    
    print("\n" + "=" * 60)
    print("WORKING SCOPES:")
    print("=" * 60)
    for s in working_scopes:
        print(f"  ✅ {s}")
    
    if working_scopes:
        best = max(working_scopes, key=len)  # Longest working scope = most permissions
        print(f"\nRecommended scope (most permissions):\n  {best}")

if __name__ == "__main__":
    main()
