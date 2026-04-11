# ProShop Mobile App — iOS Project Plan

**Created:** February 19, 2026
**Purpose:** Build a native iOS app for querying and interacting with ProShop ERP from the shop floor
**Stack:** SwiftUI (iOS) + FastAPI (Python backend) + ProShop GraphQL API

---

## What Already Exists

You're NOT starting from scratch. Traxis already has:

1. **Working ProShop GraphQL client** — OAuth 2.0 auth, query execution, token management
2. **Working conversational CLI prototype** (`proshop_chat.py`) — natural language → GraphQL → formatted results
3. **Schema introspection data** — known working queries, documented API limitations
4. **Fusion 360 → ProShop bridge** — web automation patterns for things the GraphQL can't do

### Existing Code Location
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\10. Conversational Proshop\
```

### ProShop API Details

| Item | Value |
|------|-------|
| Base URL | `https://traxismfg.adionsystems.com` |
| GraphQL Endpoint | `/api/graphql` |
| Auth Endpoint | `/home/member/oauth/accesstoken` |
| Auth Method | OAuth 2.0 Client Credentials |
| Client ID | `3923-9C1C-7291` |
| Scope | `parts:rwdp+workorders:rwdp` |
| Token Lifetime | 86400 seconds (24 hours) |

### Known Working Queries

```graphql
# Get part with operations, tools, written descriptions
query GetPart($partNumber: [String!]!) {
  parts(filter: { partNumber: $partNumber }) {
    records {
      partNumber
      partDescription
      operations {
        records {
          opNumber
          operationDescription
          writtenDescriptions {
            records { legacyId, writtenDescription }
          }
          tools {
            records { sequenceNumber, outOfHolder, holder, sequenceDescription }
          }
        }
      }
    }
  }
}

# Get work order with operations
{
  workOrder(workOrderNumber: "25-0001") {
    ops {
      records {
        operationNumber
        partOperation {
          writtenDescriptions {
            records { legacyId, writtenDescription }
          }
        }
      }
    }
  }
}
```

### Known API Limitations
- Parts filter sometimes returns empty for known part numbers
- Written Description display bug (data stored but not visible in ProShop UI)
- Work order nested filter by PO doesn't work — must fetch all and match client-side
- GraphQL schema is limited — not all ProShop data is exposed
- No REST API exists

---

## Architecture

```
┌──────────────────┐     HTTPS/JSON      ┌──────────────────────┐     GraphQL     ┌──────────┐
│   iOS App        │ ◄──────────────────► │   FastAPI Backend    │ ◄─────────────► │ ProShop  │
│   (SwiftUI)      │                      │   (Python)           │                 │ ERP      │
│                  │                      │                      │                 │          │
│  • Job Dashboard │                      │  • /api/workorders   │                 │          │
│  • QR Scanner    │                      │  • /api/parts        │                 │          │
│  • Search        │                      │  • /api/search       │                 │          │
│  • Job Detail    │                      │  • /api/chat         │                 │          │
│  • Chat Interface│                      │  • Auth/token mgmt   │                 │          │
└──────────────────┘                      └──────────────────────┘                 └──────────┘
       iPhone                              Shop PC (always on)                    ProShop Cloud
```

### Why a Backend Server?

- **Security** — ProShop OAuth credentials stay on the server, never on phones
- **Caching** — Reduce load on ProShop API, faster responses
- **Shared logic** — Same backend serves iOS app, future web app, existing CLI
- **Offline queue** — Backend can queue and retry actions when ProShop is slow

---

## Phase 1: Backend API Server (No Mac Required)

Build a FastAPI server that wraps the existing ProShop GraphQL client with clean REST endpoints.

### 1.1 Project Setup

```
proshop-mobile-backend/
├── main.py                  # FastAPI app entry point
├── config.py                # Environment variables, ProShop credentials
├── auth/
│   ├── proshop_auth.py      # OAuth token management (from existing code)
│   └── app_auth.py          # Simple API key auth for the iOS app
├── api/
│   ├── workorders.py        # Work order endpoints
│   ├── parts.py             # Parts/operations endpoints
│   ├── customers.py         # Customer lookup
│   ├── search.py            # Universal search
│   └── chat.py              # Natural language query (from existing CLI)
├── graphql/
│   ├── client.py            # ProShop GraphQL client (from existing code)
│   └── queries.py           # Query templates (from existing code)
├── models/
│   └── schemas.py           # Pydantic response models
├── requirements.txt
└── README.md
```

### 1.2 API Endpoints

```
GET  /api/health                          → Server status + ProShop connection
GET  /api/workorders                      → List work orders (with filters)
GET  /api/workorders/{wo_number}          → Single work order detail
GET  /api/workorders/{wo_number}/ops      → Operations for a work order
GET  /api/parts                           → List/search parts
GET  /api/parts/{part_number}             → Part detail with operations & tools
GET  /api/parts/{part_number}/ops/{op}    → Single operation detail
GET  /api/customers                       → Customer list
GET  /api/customers/{name}/workorders     → Work orders for a customer
GET  /api/search?q=                       → Universal search across WOs, parts, customers
POST /api/chat                            → Natural language query (body: {"message": "..."})
```

### 1.3 Response Format (Standardized)

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "query_time_ms": 142,
    "cached": false,
    "timestamp": "2026-02-19T10:30:00Z"
  }
}
```

### 1.4 Key Features

- **Token management** — Auto-refresh OAuth tokens, never expose to clients
- **Response caching** — Cache frequently-accessed data (configurable TTL)
- **Error handling** — Graceful degradation when ProShop is slow/down
- **Request logging** — Track who's querying what for debugging
- **Simple auth** — API key in header for now (can upgrade to JWT later)
- **CORS** — Allow requests from local network devices
- **12-month default window** — Only return WOs from last 12 months unless requested

### 1.5 Testing

```bash
# Start server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Test from any device on the network
curl http://SHOP-PC-IP:8000/api/health
curl http://SHOP-PC-IP:8000/api/workorders/25-0001
curl -X POST http://SHOP-PC-IP:8000/api/chat -d '{"message": "show open work orders"}'
```

---

## Phase 2: iOS App (Requires Mac + Xcode)

### 2.1 App Structure

```
ProShopMobile/
├── ProShopMobileApp.swift          # App entry point
├── Models/
│   ├── WorkOrder.swift             # Data models
│   ├── Part.swift
│   ├── Operation.swift
│   └── Customer.swift
├── Services/
│   ├── APIClient.swift             # HTTP client for backend
│   ├── QRScanner.swift             # Camera QR code reader
│   └── CacheManager.swift          # Local data caching
├── Views/
│   ├── Dashboard/
│   │   ├── DashboardView.swift     # Main overview screen
│   │   └── JobCard.swift           # Individual job summary card
│   ├── WorkOrder/
│   │   ├── WorkOrderListView.swift
│   │   ├── WorkOrderDetailView.swift
│   │   └── OperationDetailView.swift
│   ├── Search/
│   │   ├── SearchView.swift        # Universal search
│   │   └── SearchResultRow.swift
│   ├── Scanner/
│   │   └── QRScannerView.swift     # Camera-based QR scanner
│   ├── Chat/
│   │   ├── ChatView.swift          # Natural language query interface
│   │   └── ChatBubble.swift
│   └── Settings/
│       └── SettingsView.swift      # Server URL, preferences
├── Assets.xcassets/
└── Info.plist
```

### 2.2 Key Screens

**Dashboard** — At-a-glance overview
- Open work orders count with status breakdown
- Jobs due this week (highlighted if overdue)
- Quick action buttons: Scan QR, Search, Chat

**Work Order Detail** — Everything about a job
- WO number, customer, part, quantity, due date, status
- Operations list with completion status
- Tap operation → setup notes, tools, written descriptions

**QR Scanner** — Point and go
- Scan QR code on traveler/tag → instantly load that WO or part
- Minimal UI — camera takes up the full screen, info overlays on top

**Search** — Find anything
- Single search bar
- Results grouped: Work Orders, Parts, Customers
- Recent searches saved locally

**Chat** — Ask in plain English
- Same conversational interface as the CLI prototype
- "What WOs are due this week?"
- "Show me tools for part XYZ Op 60"
- Response formatted as tappable cards when possible

### 2.3 Design Principles

- **Big touch targets** — Shop floor hands are often gloved or dirty
- **High contrast** — Readable in bright shop lighting
- **Minimal navigation** — Max 2 taps to any information
- **Fast** — Show cached data immediately, update in background
- **Dark mode support** — Easier on eyes during long shifts

### 2.4 iOS-Specific Features

- **Camera** — QR scanning for instant job lookup
- **Haptic feedback** — Confirm actions with vibration
- **Spotlight search** — Search ProShop data from iPhone home screen
- **Widget** — Show today's job count or overdue items on home screen
- **Dictation** — Use iOS keyboard mic to speak queries in Chat view
- **Offline mode** — Cache last-viewed jobs, sync when reconnected

---

## Phase 3: QR Code System

### 3.1 QR Code Format

Encode work order or part info in QR codes printed on travelers/tags:

```
proshop://wo/25-0001          → Opens work order 25-0001
proshop://part/TRA1-TEMP      → Opens part TRA1-TEMP
proshop://op/25-0001/60       → Opens Op 60 of WO 25-0001
```

### 3.2 QR Code Generation

Add an endpoint to the backend that generates QR codes:

```
GET /api/qr/wo/{wo_number}        → Returns QR code image (PNG)
GET /api/qr/part/{part_number}    → Returns QR code image (PNG)
```

These can be printed on travelers, stuck on material bins, or attached to tooling.

### 3.3 Scanning Flow

1. Tap "Scan" button (or shake phone to activate scanner)
2. Point camera at QR code
3. App decodes URL scheme → routes to appropriate detail view
4. Job info loads instantly (cached if available, fetches fresh in background)

---

## Phase 4: Future Enhancements

- **Push notifications** — Alert when a job status changes or a WO is assigned
- **Time tracking** — Clock in/out of operations from the app
- **Photo capture** — Take inspection photos attached to operations
- **Multi-user** — Different views for machinists vs. management
- **Apple Watch** — Quick glance at current job status
- **Siri integration** — "Hey Siri, what's the status of work order 25-0001?"

---

## Getting Started — Step by Step

### Step 1: Build the Backend (Claude Code on your shop PC)

```powershell
cd "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects"
mkdir "11. ProShop Mobile App"
cd "11. ProShop Mobile App"
claude
```

Prompt for Claude Code:
```
Read this PROJECT.md file. Build Phase 1: the FastAPI backend server.

Start by copying the existing ProShop GraphQL client from 
"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\10. Conversational Proshop"

Then build the REST API endpoints on top of it. Use FastAPI with Pydantic models.
Include the /api/chat endpoint that wraps the existing conversational query logic.

Make it runnable with: uvicorn main:app --host 0.0.0.0 --port 8000

Test each endpoint against live ProShop data.
```

### Step 2: Test Backend from Phone

Once the server is running, open Safari on your iPhone and go to:
```
http://YOUR-SHOP-PC-IP:8000/docs
```
FastAPI auto-generates interactive API docs. Test every endpoint from your phone's browser.

### Step 3: Build the iOS App (Needs a Mac)

Options:
- **If you have a Mac:** Install Xcode, create a new SwiftUI project, hand this doc to Claude Code
- **If you don't have a Mac:** Consider a Mac Mini (~$599) as a build server. It can also run your backend
- **Alternative:** Build as a Progressive Web App (PWA) first — runs in Safari, no Mac needed, still gets QR scanning and home screen icon. Convert to native later

### Step 4: Deploy

- Backend runs on a shop PC (or the Mac Mini) on your local network
- iOS app connects to `http://192.168.x.x:8000`
- For remote access: set up a VPN or use Tailscale (free, easy)

---

## Decision Point: Native iOS vs. Progressive Web App

| Factor | Native iOS (SwiftUI) | PWA (Web App) |
|--------|---------------------|---------------|
| **Requires Mac** | Yes | No |
| **App Store** | Optional (can sideload) | N/A |
| **QR Scanning** | Excellent | Good (via browser API) |
| **Offline** | Full support | Limited |
| **Push Notifications** | Native | Supported on iOS 16.4+ |
| **Camera** | Full access | Limited |
| **Build time** | Longer | Faster |
| **Maintenance** | Xcode updates | Just HTML/JS/CSS |
| **Claude Code can build solo** | No (needs Xcode) | Yes |

**Recommendation:** Start with a **PWA** so Claude Code can build and test the entire thing without needing a Mac. If you want native features later, the backend API stays the same — you just swap the frontend.

---

## PWA Alternative (Phase 2B — No Mac Required)

If you go the PWA route, Claude Code can build the entire frontend:

```
proshop-mobile-frontend/
├── index.html              # Single page app shell
├── manifest.json           # PWA manifest (home screen icon, etc.)
├── sw.js                   # Service worker (offline caching)
├── css/
│   └── app.css             # Mobile-first styles
├── js/
│   ├── app.js              # Main app logic + routing
│   ├── api.js              # Backend API client
│   ├── scanner.js          # QR code scanner (via camera API)
│   ├── chat.js             # Chat interface
│   └── cache.js            # Local storage management
└── icons/
    ├── icon-192.png
    └── icon-512.png
```

This runs in Safari and can be "installed" to the home screen with an icon. It looks and feels like a native app for most use cases.

---

## Budget Estimate

| Item | Cost | Notes |
|------|------|-------|
| FastAPI backend | $0 | Runs on existing shop PC |
| PWA frontend | $0 | Free to build and host locally |
| Mac Mini (if going native) | ~$599 | Also useful as a build/automation server |
| Apple Developer Account | $99/year | Only needed for App Store distribution |
| QR code labels | ~$30 | Dymo or Brother label printer |
| Tailscale (remote access) | $0 | Free for personal use |

**Minimum viable cost: $0** (PWA route on existing hardware)
**Full native setup: ~$700** (Mac Mini + dev account)
