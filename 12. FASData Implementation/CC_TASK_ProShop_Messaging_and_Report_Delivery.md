# Claude Code Task: ProShop Messaging API Discovery + Utilization Report Delivery

## Context

We're building a CNC machine utilization monitoring system at Traxis Manufacturing. We already have:

- A FOCAS-based collector service polling 5 FANUC CNC machines every 60 seconds
- Data stored in SQLite (`monitoring.db`) and synced hourly to Dropbox
- A Python + Node.js report generator that produces a Word doc with utilization charts and tables

**Goal:** We want to automatically deliver a daily utilization report to shop personnel. The preferred channel is ProShop's internal messaging system — but we don't know if the API supports it. Your job is to find out and, if possible, build the integration.

---

## Step 1: Discover ProShop Messaging API

### Authentication

ProShop uses OAuth 2.0 Client Credentials. Credentials are stored in:

```
C:\Users\TRAXIS\.traxis.env
```

Format:
```
PROSHOP_CLIENT_ID=<client_id>
PROSHOP_CLIENT_SECRET=<client_secret>
```

**Token request:**
```
POST https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=parts:rwdp+workorders:rwdp
```

> ⚠️ CRITICAL: Use `data=` (form-encoded) in Python requests, NOT `json=`. The `scope` parameter is REQUIRED or you'll get a misleading "accessTokenResult does not point to valid database object" error.

**GraphQL endpoint:**
```
https://traxismfg.adionsystems.com/api/graphql
```

**Using the token:**
```
Authorization: Bearer <access_token>
```

> ⚠️ ProShop's introspection can be flaky. Full `__schema { types { ... } }` queries sometimes return `API_ERROR`. Use targeted `__type(name: ...)` queries instead if that happens.

> ⚠️ The `includeDeprecated` parameter is REQUIRED on `fields()` queries. Omitting it causes errors.

### What to Search For

Run GraphQL introspection queries to find anything related to messaging, notifications, or communication:

1. **Get all root Query fields** — look for anything messaging-related:
```graphql
{
  __type(name: "Query") {
    fields(includeDeprecated: true) {
      name
      type { name kind }
    }
  }
}
```

2. **Get all Mutations** — look for send/create message mutations:
```graphql
{
  __type(name: "Mutation") {
    fields(includeDeprecated: true) {
      name
      args {
        name
        type { name kind }
      }
    }
  }
}
```

3. **Probe specific type names** that might exist:
```
Message, Messages, MessageInput, Notification, Notifications,
Note, Notes, NoteInput, Comment, Comments, Alert, Alerts,
Communication, Inbox, SendMessageInput, CreateMessageInput,
UserMessage, SystemMessage, ShopMessage, Bulletin, Announcement
```

For each, try:
```graphql
{
  __type(name: "Message") {
    name
    kind
    fields(includeDeprecated: true) {
      name
      type { name kind }
    }
  }
}
```

4. **Try full schema dump** (may fail — that's OK):
```graphql
{
  __schema {
    types {
      name
      kind
    }
  }
}
```

If it works, search the results for any type names containing: message, msg, notification, notify, alert, chat, comment, note, send, broadcast, inbox, mail, email, announce, bulletin, communication, dispatch, memo, log.

5. **Check available scopes** — our current scope is `parts:rwdp+workorders:rwdp`. There may be additional scopes we haven't enabled. If you find messaging types but can't access them, try adding scopes like `messages:rwdp` or `notifications:rwdp` to the token request.

### Report Your Findings

Document everything you find:
- All root Query field names
- All Mutation names
- Any messaging-related types, their fields, and input types
- If messaging IS available: the exact query/mutation syntax needed to send a message
- If messaging is NOT available: confirm that and list what IS available

---

## Step 2: If Messaging IS Available

Build a Python function that sends a utilization summary message through ProShop. The message should include:

- Date range
- Per-machine utilization percentages
- Shop average
- Which machines are above/below target (70% green, 50% yellow, below 50% red)
- Any machines offline

Integrate this into the existing report pipeline so it runs after generating the report.

---

## Step 3: If Messaging is NOT Available — Build Email Delivery

If ProShop messaging isn't available via API, build email-based delivery instead.

### Requirements

Create a Python script (`send_daily_report.py`) that:

1. Runs the existing `generate_report.py` to query the database and produce charts
2. Generates an HTML email body with:
   - Utilization bar chart (embedded as inline image)
   - Summary table with per-machine utilization, hours, and status
   - Color-coded status (green/yellow/red)
3. Sends the email via SMTP
4. Can be scheduled as a Windows task to run daily at (e.g.) 7 PM after the shift ends

### Email Config

Create a config file (`email_config.json`) with:
```json
{
  "smtp_server": "",
  "smtp_port": 587,
  "username": "",
  "password": "",
  "from_address": "",
  "to_addresses": [],
  "subject_prefix": "FASData Daily Report"
}
```

Leave the values blank — Wolfgang will fill them in. The script should check for this file and prompt if it's missing.

### Fallback: HTML to Dropbox

Also generate a standalone HTML report file saved to:
```
D:\Dropbox\MACHINE COMM Traxis\FASData\reports\utilization_YYYY-MM-DD.html
```

This gives anyone with Dropbox access a way to view the report in a browser, even if email isn't set up yet.

---

## File Locations

| Item | Path |
|------|------|
| Monitoring database (synced copy) | `D:\Dropbox\MACHINE COMM Traxis\FASData\monitoring.db` |
| Project folder | `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\` |
| ProShop credentials | `C:\Users\TRAXIS\.traxis.env` |
| Existing report generator | `generate_report.py` (in project folder) |
| Existing docx builder | `build_report.js` (in project folder) |
| Python executable | `C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe` |

---

## Database Schema

The monitoring database has one table:

```sql
CREATE TABLE machine_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    machine_name TEXT,
    connected INTEGER NOT NULL,
    error_message TEXT,
    mode TEXT,
    run_status TEXT,
    motion TEXT,
    program_number INTEGER,
    main_program INTEGER,
    spindle_speed INTEGER,
    feed_rate INTEGER,
    spindle_override INTEGER,
    feedrate_override INTEGER,
    emergency INTEGER,
    alarm INTEGER,
    alarm_message TEXT,
    axis_x INTEGER,
    axis_y INTEGER,
    axis_z INTEGER
);
```

### Utilization Calculation

```
Utilization % = (samples where spindle_speed > 0 OR run_status = 'STRT'/'MSTR') / total samples × 100
```

Only count samples during shift hours: **6:00 AM – 7:00 PM, Monday–Friday**.

### Machines

| ID | Name | Status |
|----|------|--------|
| T2 | YCM NTC1600LY | Active |
| M2 | FANUC Mill 2 | Active |
| M3 | FANUC Mill 3 | Offline (ethernet adapter failed) |
| M6 | FANUC Mill 6 | Active |
| M8 | FANUC Mill 8 | Active |

### Thresholds

- Green (on target): ≥ 70%
- Yellow (below target): 50–69%
- Red (critical): < 50%

---

## Summary of Priorities

1. **First:** Scan ProShop API for messaging capabilities
2. **If found:** Build messaging integration
3. **If not found:** Build HTML report auto-saved to Dropbox + email delivery script
4. **Always:** Generate a standalone HTML report to `FASData\reports\` folder in Dropbox
