# COTS Crib Kiosk — Project State Document
*Generated: 2026-03-06*

---

## Project Summary

Build a touch-screen kiosk on the Shop 3 machine (Lenovo ThinkCentre Tiny + HP touch display) that allows employees to check out consumables from the tool crib by tapping their name, scanning a QR code on the bin, entering a quantity, and confirming. The system reads and writes directly to ProShop's COTS module via the GraphQL API.

---

## Hardware

| Item | Detail |
|------|--------|
| Computer | Lenovo ThinkCentre Tiny (labeled "SHOP 3"), Intel processor |
| Display | HP touch screen tablet/display |
| OS | Windows 7 (confirmed) |
| Scanner | QR code (2D) — USB wired or Bluetooth, TBD |
| Browser | Chrome, full-screen kiosk mode (F11) |

**Note:** Windows 7 has no tablet mode. The web app approach sidesteps this entirely — full-screen Chrome with large touch targets is the correct UI strategy.

---

## User Workflow (Confirmed)

1. **Tap name** from a list on screen (no badge, no login — employees are few enough to list)
2. **Scan QR code** on the bin/item
3. **Enter quantity** via on-screen numeric keypad
4. **Confirm** → transaction logged, ProShop COTS qty updated

---

## Key Decision: ProShop COTS API — Confirmed Available

The `api_gaps.md` from Project 15 incorrectly listed Inventory as "No Endpoint." The fuller schema discovery (`proshop_actual_schema.md`) confirms **COTS has full API access**:

### OAuth Scope
```
cots:rwdp
```
(read, write, delete, purge — already in the master scope string from Project 15)

### Available Mutations
- `addCOTS`
- `updateCOTS`
- `deleteCOTS`
- `overwriteCOTS`

### Query
- `cots` (query name TBD — not explicitly listed in schema summary but `addCOTS`/`updateCOTS` confirm the entity exists)

### Key COTS Fields to Confirm
These need to be verified via a live introspection query on the COTS type — the schema doc doesn't have a COTS section, meaning it may not have been fully explored yet. Priority fields to find:
- Item name / description
- Quantity on hand
- Reorder point / minimum quantity
- Location / bin
- Unit cost
- Unique ID / legacyId (for QR code encoding)

---

## ProShop API Reference

From Project 15 (`01_api_discovery`):

| Parameter | Value |
|-----------|-------|
| GraphQL Endpoint | `https://traxismfg.adionsystems.com/api/graphql` |
| Token Endpoint | `https://traxismfg.adionsystems.com/home/member/oauth/accesstoken` |
| Client ID | `3923-9C1C-7291` |
| Token body | `grant_type=client_credentials&client_id=...&client_secret=...&scope=cots:rwdp` |
| Token lifetime | 24 hours |

### Auth Pattern (from existing `ProShopGraphQL` class)
```python
class ProShopGraphQL:
    def authenticate_oauth(self, client_id, client_secret):
        # OAuth 2.0 Client Credentials flow

    def execute(self, query, variables=None):
        # POST to /api/graphql with Bearer token
```

---

## Architecture

### Stack
| Layer | Technology | Reason |
|-------|-----------|--------|
| UI | Single-page HTML/JS web app | Runs in Chrome on Shop 3, no install needed, touch-friendly |
| Backend | None (client calls ProShop API directly, or thin Python local server if CORS is a problem) |
| Database | ProShop COTS module | Confirmed API access — no Airtable needed |
| Alerts | TBD — Make.com or email script when qty hits reorder point |
| QR codes | Generated from COTS legacyId or unique identifier | One printed label per bin |

### CORS Note
Direct browser → ProShop GraphQL API calls may hit CORS restrictions. If so, a tiny local Python Flask server on Shop 3 acts as a proxy — the browser calls `localhost:5000`, which forwards to ProShop. This is a common pattern and easy to implement.

---

## Phase Plan

### Phase 0 — COTS Schema Discovery (First Task)
Before building anything, run an introspection specifically on the COTS type to get all fields.

```graphql
{
  __type(name: "COTS") {
    name
    fields {
      name
      type {
        name
        kind
        ofType { name kind }
      }
    }
  }
}
```

Also run a live query to see real COTS records:
```graphql
{
  cots(filter: {}) {
    records {
      legacyId
      # add all scalar fields once discovered
    }
  }
}
```

**Goal:** Identify the exact field names for qty-on-hand, reorder point, item name, and bin location.

---

### Phase 1 — Core Kiosk Web App

Build `crib_kiosk.html` — a single self-contained HTML file:

**Screen 1: Who are you?**
- Grid of large name buttons (one per employee)
- Pull employee list from ProShop `users` query (active users only) OR hardcode for simplicity

**Screen 2: Scan item**
- Full-width text input that auto-focuses (scanner acts as keyboard)
- Display: "Waiting for scan..."
- On scan: look up COTS record by ID, show item name + current qty

**Screen 3: How many?**
- Large numeric keypad (touch-friendly)
- Shows: item name, current qty, employee name
- Confirm / Cancel buttons

**Screen 4: Confirmation**
- "Checked out 3x [Item Name] — [Employee]"
- Auto-returns to Screen 1 after 3 seconds

---

### Phase 2 — ProShop Write-Back

On confirm:
1. `updateCOTS` mutation to decrement quantity
2. Log the transaction (either to a COTS notes field, or a separate transaction log — TBD based on schema)
3. Check if new qty ≤ reorder point → trigger alert

---

### Phase 3 — QR Code Generation

- Script to generate QR codes for all COTS items
- Each QR encodes the COTS `legacyId` (or whichever unique ID field exists)
- Print as labels for bins

---

### Phase 4 — Reorder Alerts

When a checkout pushes qty ≤ `minimumQuantityOnHand`:
- Option A: Make.com webhook → email alert
- Option B: Python script sends email via SMTP
- Option C: ProShop message API (`addMessage` mutation) — sends internal ProShop notification

---

## Files from Project 15 to Carry Forward

These files from `01_api_discovery.zip` are directly relevant:

| File | Use |
|------|-----|
| `proshop_actual_schema.md` | Full schema reference — confirmed COTS mutations |
| `api_session1_test.py` | OAuth auth pattern |
| `api_test_results_session4.json` | Mutation test results |
| `scope_permission_map.md` | Scope reference |
| Any existing `ProShopGraphQL` class | Reuse auth + execute methods |

---

## Open Questions / First Tasks for Claude Code

In order of priority:

1. **Introspect the COTS type** — get all field names (especially qty, reorder, bin, name)
2. **Query live COTS records** — confirm data is there and readable
3. **Test `updateCOTS` mutation** — decrement a qty field on a test record
4. **CORS check** — can Chrome on Shop 3 call ProShop GraphQL directly, or do we need a local proxy?
5. **Employee list source** — query `users` (active only) or hardcode names?
6. **QR encoding scheme** — which COTS field is stable enough to encode in a QR label?

---

## Related Future Project

**Tool Crib — Serialized Tools (Phase 2)**
Same kiosk, same workflow, but using the `tools` entity instead of COTS. The Tool schema has `qtyInBin`, `qtyAvailable`, `minimumQuantityOnHand`, `location` — all confirmed present. Defer until COTS version is running.

---

## Notes

- The `api_gaps.md` file from Project 15 has an **error** — it lists Inventory as "No Endpoint." This was written before the full schema was discovered. The correct reference is `proshop_actual_schema.md`.
- Windows 7 on Shop 3 has no tablet mode — the full-screen Chrome web app approach is the right solution.
- The Lenovo ThinkCentre Tiny has confirmed Intel processor and runs Windows 7. Consider upgrading to Windows 10 long-term (drivers exist for this hardware) but not a blocker for this project.
