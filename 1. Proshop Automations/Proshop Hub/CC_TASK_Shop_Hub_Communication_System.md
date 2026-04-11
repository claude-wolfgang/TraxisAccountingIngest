# Claude Code Task: Shop Hub — Live Machine & WO Communication System

## Project: 12. FASData Implementation (Extension)

## Overview

Build a unified shop floor communication hub that extends the FASData Live Dashboard with:
1. Program comment reading via FOCAS (to extract part numbers)
2. ProShop integration (to look up active WOs by part number)
3. Live messaging system (machine-specific and shop-wide)
4. WO selection and display on machine cards

This is a significant feature addition. Take it step by step, test as you go.

---

## Part 1: FOCAS Program Comment Reading

### Goal
Read the program comment/header from running CNC programs to extract part numbers.

### Technical Background

FOCAS functions that can read program info:
- `cnc_rdexecprog` — Reads currently executing program content
- `cnc_rdproginfo` — Reads program information
- `cnc_rdprgnum` — Reads program number (you already have this)

The controls at Traxis are 0i-TF (lathe) and 0i-MF (mills). Both should support program comment reading.

### Existing Code Reference

FocasMonitor is a C# Windows service at:
```
C:\FocasMonitor\
```

Source code is at:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\FocasMonitor\
```

Key files:
- `Focas.cs` — P/Invoke wrappers for FOCAS DLLs
- `MonitoringService.cs` — Main polling loop
- `Database.cs` — SQLite writes

The FOCAS DLLs are 32-bit, project builds as win-x86.

### Task 1a: Add Program Comment Reading to FocasMonitor

1. Add new P/Invoke declarations to `Focas.cs` for reading program content/comments
2. Add a new field to the polling data: `program_comment`
3. Update the database schema to include the new field
4. Update `MonitoringService.cs` to read and store the comment on each poll
5. Handle cases where comment is empty or unreadable

### Task 1b: Test on Live Machine

After building, test on one machine first. The YCM lathe (T2) at 10.1.1.82 is reliable.

```
Machine: T2 (YCM NTC1600LY)
IP: 10.1.1.82
Port: 8193
Control: 0i-TF
```

### Expected Comment Format

Programs typically have a header comment like:
```gcode
O1234 (3847-C FINISH MILL)
```
or
```gcode
O1234
(PART 3847-C OP20 FINISH)
```

The comment is in parentheses. Extract the full comment string; parsing for part number comes later.

---

## Part 2: Part Number Parsing

### Goal
Extract part numbers from program comments using pattern matching.

### Part Number Formats at Traxis

Part numbers may appear as:
- `3847-C` (number-letter)
- `3847` (number only)
- `PN-3847-C` or `PN:3847-C` (prefixed)
- Mixed in with other text: `(3847-C FINISH MILL OP20)`

### Task 2: Create Parser

Build a Python function (for the dashboard) that:
1. Takes a raw program comment string
2. Extracts the most likely part number
3. Returns `None` if no part number found

```python
def extract_part_number(comment: str) -> str | None:
    """
    Extract part number from CNC program comment.
    
    Examples:
        "(3847-C FINISH MILL)" -> "3847-C"
        "(PN-3847 OP20)" -> "3847"
        "(ROUGH CYCLE)" -> None
    """
    # Implement pattern matching
    pass
```

Be generous in matching — better to extract something than nothing. Can refine later.

---

## Part 3: ProShop API Integration

### Goal
Query ProShop to get active Work Orders for a given part number.

### ProShop API Details

```
Endpoint: https://traxismfg.adionsystems.com/api/graphql
Auth: OAuth2 (client credentials flow)
Client ID: 0615-12FB-C88D (production)
Scope: parts:rwdp+workorders:rwdp
```

OAuth token endpoint:
```
POST https://traxismfg.adionsystems.com/api/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=0615-12FB-C88D&scope=parts:rwdp+workorders:rwdp
```

### Task 3a: Query Active WOs by Part Number

GraphQL query to find work orders for a part:

```graphql
query GetWorkOrdersForPart($partNumber: String!) {
  workOrders(filter: { partNumber: $partNumber, status: "Active" }) {
    edges {
      node {
        id
        workOrderNumber
        partNumber
        partDescription
        operationNumber
        quantityRequired
        quantityComplete
        status
        dueDate
      }
    }
  }
}
```

Note: The exact filter syntax may need adjustment. Check the ProShop API schema. There are reference docs at:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\docs\proshop-api.md
```

### Task 3b: Create ProShop Client Module

Create a Python module for ProShop API calls:

```python
# proshop_client.py

class ProShopClient:
    def __init__(self, client_id: str, base_url: str):
        self.client_id = client_id
        self.base_url = base_url
        self.token = None
        self.token_expires = None
    
    def get_token(self) -> str:
        """Get or refresh OAuth token."""
        pass
    
    def get_active_wos_for_part(self, part_number: str) -> list[dict]:
        """Return list of active WOs for the given part number."""
        pass
```

Cache the token (they last 1 hour typically). Handle token refresh gracefully.

---

## Part 4: Messaging System

### Goal
Add a simple messaging system for shop floor communication.

### Data Model

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- ISO format
    author TEXT NOT NULL,              -- Who sent it
    machine_id TEXT,                   -- NULL for shop-wide
    work_order TEXT,                   -- NULL if not WO-specific
    message TEXT NOT NULL,
    read_by TEXT DEFAULT ''            -- Comma-separated user list (future use)
);

CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_messages_machine ON messages(machine_id);
```

### Task 4a: Message Storage

Options:
1. **Add to existing monitoring.db** — Simple, but mixes concerns
2. **New shophub.db** — Cleaner separation
3. **Add to FASData Live Dashboard's memory** — No persistence across restarts

Recommendation: New `shophub.db` in `C:\FASData\` alongside `monitoring.db`.

### Task 4b: Message API Endpoints

Add to the Flask app (either extend FASData Live Dashboard or create new Shop Hub service):

```
GET  /api/messages?machine_id=M8&limit=20    — Get recent messages
POST /api/messages                            — Send a message
     Body: { "author": "Joe", "machine_id": "M8", "message": "Need tooling" }
```

### Task 4c: Real-Time Updates

For live updates without page refresh, options:
1. **Polling** — Dashboard fetches `/api/messages` every 10-30 seconds (simple)
2. **WebSocket** — Server pushes new messages instantly (better UX, more complex)
3. **Server-Sent Events (SSE)** — One-way push, simpler than WebSocket

Recommendation: Start with polling (option 1). Can upgrade to WebSocket later if needed.

---

## Part 5: Unified Dashboard UI

### Goal
Extend the Aztec-themed dashboard to show WO info and messages on each machine card.

### Updated Machine Card Layout

```
┌─────────────────────────────────────────┐
│  M8                        🟢 68.3%     │
│  FANUC Mill 8                           │
├─────────────────────────────────────────┤
│  📋 Program: O1234                      │
│  🔧 Part: 3847-C                        │
├─────────────────────────────────────────┤
│  📦 Active WOs:                         │
│  ○ WO-24518 (Op 20) — 12 pcs           │
│  ● WO-24612 (Op 20) — 8 pcs  ← running │
├─────────────────────────────────────────┤
│  💬 "Need 1/2 EM" — Joe (2m ago)       │
│     "On my way" — Mike (1m ago)         │
│                                         │
│  [Type message...]            [Send]    │
└─────────────────────────────────────────┘
```

### Task 5a: Update Dashboard HTML/JS

1. Extend the existing machine card template
2. Add WO display section with selection (radio buttons or tap to select)
3. Add message display section (last 3-5 messages)
4. Add message input field + send button
5. Store selected WO in localStorage so it persists on refresh

### Task 5b: Shop-Wide Message Panel

Add a collapsible panel (or separate tab) for shop-wide messages:

```
┌─────────────────────────────────────────┐
│  📢 SHOP MESSAGES                   [−] │
├─────────────────────────────────────────┤
│  "Parts for WO-24518 at saw" — Sarah    │
│  "Lunch meeting at noon" — Wolfgang     │
│  "M2 back online" — System              │
│                                         │
│  [Type shop message...]        [Send]   │
└─────────────────────────────────────────┘
```

### Task 5c: Author Identification

For MVP, just ask for name on first message and store in localStorage:

```javascript
let author = localStorage.getItem('shopHubAuthor');
if (!author) {
    author = prompt('Enter your name:');
    localStorage.setItem('shopHubAuthor', author);
}
```

Future enhancement: Tie to ProShop operator login or badge scan.

---

## Part 6: Integration & Testing

### Task 6a: Wire It All Together

1. FocasMonitor writes program_comment to monitoring.db
2. Dashboard reads monitoring.db, extracts part number from comment
3. Dashboard queries ProShop for active WOs with that part number
4. Dashboard displays WOs, allows selection
5. Messages flow through /api/messages endpoints
6. Dashboard polls for new messages every 15 seconds

### Task 6b: Test Scenarios

1. **Program with part number** — Verify WO lookup works
2. **Program without part number** — Graceful fallback (show "Unknown" or allow manual entry)
3. **Part with multiple WOs** — Verify selection works
4. **Part with no active WOs** — Graceful message
5. **Message send/receive** — Verify persistence and display
6. **Multiple users** — Open dashboard on two devices, verify messages sync

### Task 6c: Error Handling

- FOCAS read fails → Show "—" for program/comment
- ProShop API down → Show cached data or "WO lookup unavailable"
- Message send fails → Show error, don't lose the message
- Database locked → Retry with backoff

---

## File Locations

### Existing (read/extend)
```
C:\FocasMonitor\                          — FocasMonitor service (C#)
C:\FASData\monitoring.db                  — Machine data (SQLite)
D:\Dropbox\...\12. FASData Implementation\
    FocasMonitor\                         — Source code
    FASDataDashboard\                     — Live dashboard (Python/Flask)
        fasdata_live.py
        fasdata_dashboard.html
```

### New (create)
```
C:\FASData\shophub.db                     — Messages database
D:\Dropbox\...\12. FASData Implementation\
    FASDataDashboard\
        proshop_client.py                 — ProShop API client
        part_parser.py                    — Part number extraction
        (updated) fasdata_live.py         — Extended with messaging + WO
        (updated) fasdata_dashboard.html  — Extended UI
```

---

## Deployment Notes

### FocasMonitor Update

After updating FocasMonitor:
1. Build: `dotnet publish -c Release -r win-x86 --self-contained true -o publish`
2. Stop service: `sc stop FocasMonitor`
3. Copy new files to `C:\FocasMonitor\`
4. Start service: `sc start FocasMonitor`

### Dashboard Update

The FASData Live Dashboard runs on 10.1.1.71:8070. After updating:
1. The Overseer should auto-restart it, or
2. Manual restart via Overseer UI, or
3. Kill python process and re-run `fasdata_live.py`

### Database Migration

If adding `program_comment` column to existing monitoring.db:
```sql
ALTER TABLE machine_samples ADD COLUMN program_comment TEXT;
```

SQLite handles this gracefully — existing rows get NULL for the new column.

---

## Success Criteria

- [ ] Program comments read from at least one machine (T2)
- [ ] Part numbers extracted from comments
- [ ] ProShop returns active WOs for a part number
- [ ] WOs displayed on machine cards
- [ ] Operator can select which WO they're running
- [ ] Messages can be sent and appear on dashboard
- [ ] Messages persist across page refresh
- [ ] Multiple users see the same messages
- [ ] Aztec theme maintained throughout

---

## Final Step: Update Documentation

After completing this task, update:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\FASData System Reference.md
```

Add dated entry documenting:
- New FOCAS fields (program_comment)
- ProShop integration details
- Messaging system schema and endpoints
- Updated dashboard features
- Any configuration needed
