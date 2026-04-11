# Fusion Tool Library Product ID Auditor — Claude Code Brief

## Objective

Build a Fusion 360 add-in panel that lets the user browse any tool library, review all tools, and assign/edit the **Product ID** field on each tool to match the correct Traxis ProShop tool ID. This is a one-time cleanup utility to ensure all Fusion tools have valid ProShop library numbers set — which is required for the ProShop Bridge automation pipeline to function.

---

## Background

**Why this matters:** ProShop Bridge (v1.1.0) pairs Fusion program tools with ProShop library tools using the **Product ID** field in the Fusion tool definition. If a tool has no Product ID (or the wrong one), the bridge pipeline fails to match it. All tools across all Traxis libraries need a valid ProShop ID set.

**Indexable tools:** Use format `BODY/INSERT` in the Product ID field (e.g., `I460/G458`). The slash is the separator between the tool body ID and insert ID. The post-processor and ProShop automation both rely on this format.

**Fusion internal units:** Fusion stores values in centimeters internally. Convert to inches with `value_cm / 2.54` if displaying dimensions.

---

## Phase 1 — Probe ProShop Tools API

Before building the UI, query the ProShop API to understand what tool data is available for lookup/matching.

### Credentials
```
Client ID:     0615-12FB-C88D
Client Secret: 1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32
Scope:         parts:rwdp+workorders:rwdp+users:r
Token URL:     https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
GraphQL URL:   https://traxismfg.adionsystems.com/api/graphql
```

### Token Request
```bash
curl -X POST https://traxismfg.adionsystems.com/home/member/oauth/accesstoken \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=0615-12FB-C88D" \
  -d "client_secret=1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32" \
  -d "scope=parts:rwdp+workorders:rwdp+users:r"
```

### Step 1 — Introspect the `tool` type
```graphql
{
  __type(name: "Tool") {
    fields(includeDeprecated: true) {
      name
      type { name kind ofType { name kind } }
    }
  }
}
```

### Step 2 — Query tool list
```graphql
{
  tools(pageSize: 500) {
    totalRecords
    records {
      # Add fields discovered from introspection
      # Expected useful fields: id, name, description, toolNumber, diameter, type
    }
  }
}
```

**Goal:** Understand what fields are available so the UI can show useful matching info (name, number, description, diameter/type if available).

---

## Phase 2 — Fusion Add-in

### Add-in Structure
```
FusionToolAuditor/
  FusionToolAuditor.py        # Entry point (must match folder and manifest name exactly)
  FusionToolAuditor.manifest
  resources/                  # Icons if needed
```

> **Critical Fusion rule:** Folder name, .py filename, and .manifest filename must all match exactly.

> **Critical Fusion rule:** All blocking operations (network calls, file I/O, sleep) MUST run off the main thread. Use `threading.Thread` and `adsk.core.Application.get().fireCustomEvent()` to push results back to the UI thread. Blocking the main thread freezes Fusion entirely.

### Core Features

#### 1. Library Picker
- On panel open, enumerate all available tool libraries using `adsk.cam.CAMManager.get().libraryManager`
- Show a dropdown listing all libraries (local, cloud, document-embedded)
- On selection, load and display all tools from that library

#### 2. Tool Table
Display each tool with these columns:
| Column | Source |
|--------|--------|
| Tool Number | `tool.toolNumber` |
| Description | `tool.description` |
| Type | `tool.type` |
| Diameter | `tool.diameter` (convert cm → inches: `/ 2.54`) |
| Product ID | `tool.productId` — editable |
| Status | ✅ set / ⚠️ empty |

- Highlight tools with empty/missing Product ID
- Provide a filter toggle: "Show all" vs "Show missing only" — useful for working through gaps efficiently

#### 3. ProShop Tool Lookup
- On panel load, fetch ProShop tool list in a background thread
- Show a search/filter input alongside each tool's Product ID field
- As user types, filter the ProShop list and show matches
- Selecting a ProShop tool from the list populates the Product ID field
- Support the `BODY/INSERT` format for indexable tools

#### 4. Save
- Write edited Product IDs back to Fusion tool library via API
- Confirm save with a simple status message
- Do not require a full Fusion restart

### Threading Pattern (required for network calls)
```python
import threading
import adsk.core

app = adsk.core.Application.get()

# Register custom event for UI updates
FETCH_COMPLETE_EVENT = 'ProShopFetchComplete'

def fetch_proshop_tools_async():
    """Run in background thread — never call Fusion API from here"""
    # Do HTTP request here
    tools = fetch_from_proshop()
    # Fire event to pass data back to UI thread
    app.fireCustomEvent(FETCH_COMPLETE_EVENT, json.dumps(tools))

# Start background fetch
thread = threading.Thread(target=fetch_proshop_tools_async)
thread.daemon = True
thread.start()
```

---

## Key API Notes (from previous work)

- **`pageSize: 500`** required — default returns only 20 records
- **`includeDeprecated: true`** required on introspection `fields()` calls
- Written Descriptions API is broken (legacyId bug) — not relevant here
- `parts` query filter is broken — not relevant here
- Part numbers are case-sensitive

---

## ProShop Client (reuse existing pattern)
```python
import requests
import time

class ProShopClient:
    BASE_URL = "https://traxismfg.adionsystems.com"
    TOKEN_URL = f"{BASE_URL}/home/member/oauth/accesstoken"
    GRAPHQL_URL = f"{BASE_URL}/api/graphql"

    def __init__(self):
        self.client_id = "0615-12FB-C88D"
        self.client_secret = "1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32"
        self.scope = "parts:rwdp+workorders:rwdp+users:r"
        self.access_token = None
        self.token_expires_at = 0
        self.session = requests.Session()

    def authenticate(self):
        response = self.session.post(
            self.TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope
            }
        )
        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            self.token_expires_at = time.time() + data.get("expires_in", 86400) - 60
            return True
        return False

    def execute(self, query, variables=None):
        if not self.access_token or time.time() >= self.token_expires_at:
            self.authenticate()
        response = self.session.post(
            self.GRAPHQL_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            },
            json={"query": query, "variables": variables or {}}
        )
        return response.json()
```

---

## Suggested Build Order

1. **Probe ProShop `tools` API** — introspect schema, run test query, document available fields
2. **Basic Fusion add-in scaffold** — panel opens, library picker works, tools load and display
3. **Editable Product ID column** — user can type and save back to Fusion
4. **ProShop lookup** — background fetch, searchable dropdown to assist ID assignment
5. **Missing ID filter** — "show only tools without Product ID" toggle

---

## Files / Locations

| Item | Path |
|------|------|
| Credentials | `C:\Users\TRAXIS\.traxis.env` or `~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env` |
| ProShop Bridge source | `Dropbox/.../ProShopBridge/` |
| Existing ProShop client | `10. Conversational Proshop\src\proshop_client.py` |
| Add-in deploy location | Fusion 360 Add-ins folder (use symlink from Dropbox for multi-seat) |

---

*Brief prepared February 2026 — Traxis Manufacturing*
