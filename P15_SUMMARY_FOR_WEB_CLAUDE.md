# P15 — ProShop Replacement Research: Briefing for Web Claude

**Purpose of this document.** Bring web Claude up to speed on what P15 already established about ProShop's interconnections and API surface, so we don't re-discover ground. We are pursuing a **strangler fig** strategy: stand the replacement up alongside ProShop, peel off responsibility module-by-module, retire ProShop last. P15's job was to map the seams.

**Source material.** All claims below are drawn from the P15 working tree at `15. Proshop Replacement Research and Architecture/` — primarily `discoveries.md` (12 night-by-night investigation logs), `01_api_discovery/scope_permission_map.md`, `23_integrations/data_bridge_architecture.md`, and `proshop_api_change_requests.md` (the 5-item formal change request sent to ProShop). Investigation period: 2026-02-22 through 2026-04-07.

**Authorization in use.** OAuth client `ClaudeCodeResearch` (E88F-BE23-AC08), Client Credentials grant. Credentials are in `15.../.env`. ProShop charges $3,630/yr for API access — already paid.

---

## 1. The Headline Finding

**ProShop publicly claims it has "no API." This is false.** ProShop has a fully functional GraphQL API at `https://traxismfg.adionsystems.com/api/graphql`. OAuth 2.0 Client Credentials at `/home/member/oauth/accesstoken`. 24-hour token TTL. We have credentials and have been using it.

Night 1's early estimate (Feb 22) was that ~85% of modules were locked. **That number was wrong.** Once Session 5 (Mar 5) systematically mapped scopes to queries — including support-confirmed scope-name corrections — the real picture emerged: **24 of ~28 modules are accessible, with ~17,100 records across them, and 34 add / 42 update / 35 delete mutations available.** The earlier "locked module" verdicts in `discoveries.md` Nights 3–8 reflect missing scopes on our token at the time, not architectural locks in ProShop. **Use the scope map (Section 4 below), not Night 1's numbers, as the authoritative coverage view.**

---

## 2. Strangler-Fig Strategy Already Designed

P15's `23_integrations/data_bridge_architecture.md` lays out a four-phase parallel operation plan. This is the strangler-fig:

| Phase | Duration | What changes |
|-------|----------|--------------|
| **1. Shadow** | Months 1–2 | Read-only bridge. New system gets a copy of ProShop data via API, processes it, but ProShop stays sole authority. Zero risk. |
| **2. Dual Entry** | Months 2–4 | Bidirectional sync. Specific modules cut over to "new system primary"; remainder stay "ProShop primary." Bridge keeps both in lockstep. |
| **3. Replacement Primary** | Months 4–6 | ProShop becomes read-only archive. New system is canonical. Writes still mirror to ProShop for compliance/parity. |
| **4. Retirement** | Month 6+ | Stop writing to ProShop. Keep read access for historical queries. Cancel license when confident. |

**Module cutover order** (lowest risk first): Estimates/Quotes → Contacts → Parts → Work Orders → Financial chain (CustomerPOs → PackingSlips → Invoices) → Quality (NCRs → CARs).

This ordering matters: Contacts has to move early because everything references it; Work Orders is intentionally late because it's the highest-blast-radius entity.

---

## 3. What the API Lets Us Do (and What It Doesn't)

### Capabilities verified
- **Read all 24 accessible entity types** — 17,023 records pulled in Session 6 export.
- **Create / Update / Delete** on most entities. Mutations use a `data:` argument (not `input:` — ProShop-specific).
- **Shop-floor control:** `updateWorkOrderOperation` — mark ops complete, set percent done.
- **Time clock:** `timeClockPunchIn` / `timeClockPunchOut` work (need `users:rw`, currently we have `users:r`).
- **System config:** `updateSystemSettings` exposes 382 settings via the `securityadmin` scope.
- **Performance:** 244 records/sec at `pageSize=500` with 0.3s inter-request delay. No rate limit hit in benchmarks.

### Hard limitations (these are the strangler-fig friction points)
| Limitation | Strangler-fig impact | Workaround |
|------------|---------------------|------------|
| **No file uploads via API** | NC programs, drawings, certs, photos cannot land in ProShop programmatically | Selenium browser automation (fragile, in use in P1 ProShop Bridge) |
| **No webhooks / no events** | Cannot react to ProShop changes; must poll | Incremental scan every 5 min + full reconcile every 24 hr |
| **No `modifiedTime` / `updatedAt` field** | Can't filter "changed since X" — must full-scan and diff | Local change-detection layer in the bridge |
| **No bulk/batch mutation endpoint** | One mutation per request | Sequential with backoff; tolerable at our volumes |
| **Read-only scopes allow writes** | Security bug: a `parts:r` token can still call `addPart`. Reported to ProShop 2026-03-06; filed formally 2026-04-07. | Treat scope as advisory; use dedicated auths per integration |
| **Written-description bug** | API writes to certain description fields don't render in the ProShop UI | Avoid relying on description writes; use mutation-confirmed fields |
| **Nested-field filters broken** | Can't filter `customerPONumber.clientPONumber` | Fetch and filter client-side |
| **Some queries return 500** | `documents` and `auditReports` queries throw server errors | Open with ProShop; no workaround |
| **Scope names ≠ query names** | `cotsItems` is gated by `ots:r`; `tasks` by `taskstable:r`. Token endpoint silently accepts invalid scopes. | Use the scope map in Section 4; ProShop has no public scope-to-query reference |

### Truly blocked (no API path at all — confirmed, not "we lacked the scope")
- **File uploads** of any kind
- **Approvals** module — scope name not accepted
- **Return Material Authorizations** (`returnmaterialauthorization`) — scope not accepted
- **Parts archive** (`partsarchive`) — scope not accepted
- **Classifications** (security/ITAR classification metadata) — scope not accepted

Everything else we previously called "no API" in Nights 3–8 is actually accessible with the right scope string.

---

## 4. Authoritative Scope → Query Map

Each scope unlocks **exactly one** query. Three queries are accessible with any valid token (`vendorPOs`, `globalSearches`, `systemSearches`).

| Scope | Query | Records | Notes |
|-------|-------|---------|-------|
| `parts:r` | `parts` | 1,010 | Mutations: `addPart`, `updatePart`, `deletePart`. Includes operations, tools, IPC nested. |
| `workorders:r` | `workOrders` | 2,323 | Includes `updateWorkOrderOperation`, `finalizeWorkOrder`, time-tracking subqueries. |
| `users:r` | `users` | 29 | **Need `users:rw`** to unlock time-clock mutations + `timeTrackingLogin/Logout/Pause`. |
| `toolpots:r` | `workCells` | 24 | Naming quirk: "toolpots" not "workcells". |
| `tools:r` | `tools` | 903 | Tool library only; no crib / checkout API. |
| `contacts:r` | `contacts` | 137 | |
| `estimates:r` | `estimates` | 1,379 | |
| `quotes:r` | `quotes` | 914 | |
| `customerpos:r` | `customerPOs` | 1,132 | |
| `invoices:r` | `invoices` | 1,303 | |
| `bills:r` | `bills` | 5 | Largely unused — see P27 finding that bills go to QBO only. |
| `packingslips:r` | `packingSlips` | 1,568 | |
| `equipment:r` | `equipments` | 162 | |
| `fixtures:r` | `fixtures` | 142 | |
| `training:r` | `trainings` | 426 | |
| `qualityprocedures:r` | `qualityProcedures` | 30 | |
| `nonconformancereports:r` | `nonConformanceReports` | 255 | Full CRUD via `addNCR`/`updateNCR`/`deleteNCR`. |
| `correctiveactionrequests:r` | `correctiveActionRequests` | 5 | |
| `rtas:r` | `rtas` | 13 | |
| `messages:r` | `messages` | 3,554 | |
| `companypositions:r` | `companyPositions` | 85 | |
| `customersurveys:r` | `customerSurveys` | 2 | |
| `formats:r` | `formats` | 2 | |
| `standards:r` | `standards` | 110 | |
| `estimatesarchive:r` | `estimatesArchive` | 4 | |
| `ots:r` | `cotsItems` | — | **Name mismatch.** Confirmed by Joao at ProShop 2026-03-06. |
| `taskstable:r` | `tasks` | — | **Name mismatch.** Confirmed by Joao at ProShop 2026-03-06. |
| `securityadmin` | (no entity query) | — | Grants `updateSystemSettings` over 382 settings. |

**Permission level suffixes** — `:r`, `:rw`, `:rwd`, `:rwdp`. ProShop's intent is that `:r` blocks writes, but the API does not actually enforce this (see Section 6, Item 1).

**Full read-everything scope string** (for a Shadow-mode bridge):
```
parts:r+workorders:r+users:r+toolpots:r+tools:r+contacts:r+estimates:r+quotes:r+customerpos:r+invoices:r+bills:r+packingslips:r+equipment:r+fixtures:r+training:r+qualityprocedures:r+nonconformancereports:r+correctiveactionrequests:r+rtas:r+messages:r+companypositions:r+customersurveys:r+formats:r+standards:r+estimatesarchive:r+vendorpos:r+ots:r+taskstable:r
```

---

## 5. Entity ID Conventions (for the bridge)

| Entity | ID field | Type | Notes |
|--------|---------|------|-------|
| WorkOrder | `workOrderNumber` | String | Auto-assigned, sequential |
| Part | `partNumber` | String | Auto-assigned. **Canonical form uses customer prefix** (e.g., `R2S1-`, `ICO1-`, `AUS1-`). Some simple forms drop info — use the prefix form. |
| Contact | `accountNumber` | String | Mutations also identify by `companyName` |
| CustomerPO | `clientPONumber` | String | |
| Estimate | `estimateId` | String | |
| Invoice | — | — | No primary ID exposed; identify by `clientPoNum` + `clientPartNumber` |
| PackingSlip | — | — | Identify by `customerPO` reference |
| VendorPO | — | — | Always accessible without scope; default sort is **oldest first** |
| Quote | `quoteId` | String | |
| Tool | `toolNumber` | String | |

**Tooling schema gotcha:** `approvedBrand` = manufacturer (YG-1), `vendorPlainText` = distributor (AJR1), `vendorToolId` = EDP code. Distinct fields. Scrape-based reads on tool pages are unreliable.

**WorkOrder schema gotchas:** Material lives on `partStockStatuses.records[]`, NOT on WorkOrder. `customerPONumber` is an OBJECT — use the `customerPONumberPlainText` scalar for filtering.

**Invoice / PackingSlip schema gotchas:** Invoice number is `invoiceId`. Prices are null on un-invoiced slips. No date-range filters available.

**ProShop↔QBO sync is create-only:** The ProShop Web Connector pushes new invoices to QuickBooks but **does not push updates**. Post-sync edits in ProShop have to be repeated manually in QBO. Relevant when designing the replacement's accounting integration — don't assume parity.

---

## 6. Known Bugs and Requested API Changes (sent to ProShop 2026-04-07)

Five items in `proshop_api_change_requests.md`:

1. **[Security bug]** Read-only scopes must reject writes. Currently `parts:r` can call `addPart` and succeed against production. Reproduced 2026-03-05; reported to Joao 2026-03-06; he acknowledged the contradiction with his stated `:r`/`:w` model and is escalating.
2. **[Feature]** Add file upload via API. Currently the **only** path to attach files to ProShop records is the web UI (or Selenium against it). Blocks every "automate the full loop" workflow we have.
3. **[Feature]** Add webhooks or a `modifiedTime` field. Either solves the polling problem.
4. **[Bug]** Silent token acceptance — token endpoint returns a valid token for nonexistent scope names. Combined with the scope-name-mismatch problem, this is a debugging trap.
5. **[Feature]** Publish a scope-to-query reference. Joao agreed internally it would be useful but ProShop has no documentation of this.

Items 1 and 4 are bugs; 2, 3, 5 are features. No fixes shipped yet.

---

## 7. Existing Traxis Code That Already Talks to ProShop

The strangler fig isn't starting from scratch — several projects already speak ProShop:

| Project | What it does with ProShop |
|---------|--------------------------|
| **P1: Proshop Automations / ProShopBridge** | The original Selenium-based bridge. Selenium for file uploads, GraphQL where possible. Treat as the production bridge model — `discoveries.md` flags "don't build new Selenium workarounds until P1 revision proves a durable model." |
| **P3: The Fearless Emu** | Customer portal effort against ProShop. F4 Labs test client created in ProShop for this. |
| **P11: Proshop Mobile App** | `proshop-mobile-backend` — mobile-facing wrapper. |
| **P14, P18, P30** | Chrome MV3 extensions deployed via CWS unlisted + registry policy (self-hosted CRX broke on non-domain PCs). P30 is the current canonical extension model. |
| **P22: Schemas / data architecture** | Schemas project; intersects with P15's `03_data_model/`. |
| **P25: Agent Exploration / Overseer** | Process supervisor running on the dedicated server (srv-01). Hosts auxiliary services that consume ProShop data. Generates `project_index.json` and the nightly `TRAXIS_ECOSYSTEM.md` scan. |
| **P27: Accounting Ingest** | ProShop → QBO bookkeeping flow. **Stop pushing `VENDOR_INVOICE` to ProShop's `/bills/` endpoint** — bills are QBO-only at Traxis. |
| **P30: Material Label Extension** | Browser extension; CWS production ID `kepfeakajdfklilmpaidipmloclichjp`. |
| **P31: Workstation Display / BLE** | Touches ProShop user pages — note that **user profile pages have no CKEditor / file input** (the base64-into-CKEditor pattern from P31 elsewhere doesn't apply there). |

P15 owns the `scope_permission_map.md` reference; P1 and P27 are its primary downstream consumers.

---

## 8. Auth Pattern Wolfgang Wants You to Know About

The user `010` was set up for OAuth and got blocked at `acceptNewRecord` permission. User was deleted 2026-05-06. **Basic auth via `/api/beginsession` bypasses the OAuth-permission block** and is the working pattern for some workflows. Use OAuth for GraphQL; basic auth where OAuth's per-user permission model rejects writes.

**Email-sending rule** (relevant if the replacement sends customer correspondence): Wolfgang's address `wolfgang@traxismfg.com` is an alias on `tom@traxismfg.com`. Microsoft Graph cannot override From. Any tool-sent email **must be from wolfgang@**; sending as tom@ triggers a privilege revoke. Hard rule.

---

## 9. ProShop's Architectural Weaknesses (Inferred — Useful for Replacement Schema)

From API behavior, response shapes, and reviews. These are not confirmed against ProShop source — they are observable from the outside.

| Weakness | Why it matters for the replacement |
|----------|-----------------------------------|
| Integer PKs (no UUIDs) | Replacement should use UUID v7 — time-sortable, globally unique, no sequence contention |
| No `updated_at` / `updated_by` | No change detection possible — bake into every replacement table |
| No `version` / no optimistic concurrency | Bake `version INT NOT NULL DEFAULT 1` into every table |
| No soft delete | Bake `deleted_at TIMESTAMPTZ` into every table |
| No classification column / ITAR handling unverifiable from outside | Replacement bakes `classification_level` + PostgreSQL RLS into every table |
| String enums in DB (typo-prone) | Use enum types or lookup tables |
| Cross-module reporting requires Excel export | Replacement: unified GraphQL with cross-module queries |

The detailed replacement schema is in `15.../03_data_model/replacement_schema.md` with an ER diagram at `replacement_er_diagram.mermaid`.

---

## 10. ProShop Pricing (context for the retire-it economics)

- ~$500/mo minimum (7–8 users), per-employee $50–175/mo
- 12-month minimum commitment
- API add-on: **$3,630/yr extra** (already paid)
- 30+ modules, ASP.NET/C# backend, English only
- Mainsail Partners equity 2023, ~$32M investment, 600+ shops served

---

## 11. The Investigation's Open Questions Still Worth Asking

These were flagged for Wolfgang during the investigation and have not all been resolved:

1. **ITAR access control inside ProShop** — how does it actually work? Can foreign nationals be restricted from ITAR parts? Are ITAR files encrypted separately? Unverifiable from API alone.
2. **Complex assemblies** — reviews flag weak child/parent handling. Does Traxis hit this in practice?
3. **WO status transitions** — what triggers them? (Material? Schedule? Approval?) The state machine `Planned → Released → In Progress → QC Hold → Complete → Shipped → Invoiced → Closed` is inferred, not documented.
4. **ProShop notification/email behavior** — what does it send automatically today? The replacement needs to preserve or supersede these.
5. **`documents` and `auditReports` 500 errors** — open with ProShop, no resolution as of 2026-04.

---

## 12. What I'd Tell Web Claude To Read First

If web Claude only has time for three files in the P15 tree:

1. **`23_integrations/data_bridge_architecture.md`** — the strangler-fig plan, sync engine design, entity ID map, conflict resolution
2. **`01_api_discovery/scope_permission_map.md`** — the authoritative scope → query reference, with mutation permissions and known-blocked items
3. **`proshop_api_change_requests.md`** — the five formal change requests, useful as a concise "what's broken" inventory

If more time is available: `discoveries.md` (the cumulative night-by-night log), `01_api_discovery/api_gaps.md`, `22_data_flows/module_data_flows.md`, and `24_gap_analysis/gap_analysis.md`.

---

## 13. Strangler-Fig Investigation: What's Worth Probing Next

Concrete things P15 did not finish, in rough priority for an interconnections investigation:

- **Foreign-key graph extraction.** ProShop's introspection has 1,497 types and 130 mutations. We have `01_api_discovery/graphql_introspection_types.json` but have not built a complete relationship graph from it. Building that graph identifies the order in which entities must be sync'd (parents before children) and which deletes will cascade.
- **Change-detection probe.** With no `modifiedTime`, how do we detect what's changed since the last sync without scanning everything? Test whether sorting by `createdTime` desc + tracking max-seen-ID is reliable, and whether any entity has an undocumented updated-at-equivalent.
- **Document the four 500-error / unavailable scopes more carefully.** `documents`, `auditReports`, `approvals`, `returnmaterialauthorizations`, `partsarchive`, `classifications` are the holes in the strangler-fig. Confirm whether they hold genuinely important data or are vestigial.
- **Mutation idempotency.** Most ProShop mutations are not advertised as idempotent. For a bridge that may retry on transient failure, we need to know which add/update mutations are safe to call twice. Session 4 touched this but did not exhaust it.
- **File-upload Selenium hardening.** Until ProShop ships the API, file upload is the only path that requires browser automation. The P1 bridge does this; harden or replace it before scaling.
- **Validate the security bug is still live.** The read-only-scope-writes bug was confirmed 2026-03-05. If ProShop fixed it quietly, our strangler-fig auth model gets simpler. Worth retesting before each major phase.

---

*Generated 2026-05-23 from P15 working tree. Re-generate if discoveries.md, scope_permission_map.md, or data_bridge_architecture.md changes materially.*
