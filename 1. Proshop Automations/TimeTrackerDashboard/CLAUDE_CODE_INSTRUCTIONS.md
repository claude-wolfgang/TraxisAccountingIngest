# Claude Code: Fix Time Tracking Dashboard

## Context

You are helping Wolfgang (Tom Buerkle) at Traxis Manufacturing debug and get running a Time Tracking Status Dashboard. The dashboard polls ProShop ERP's GraphQL API for employee clock-in/out status and time tracking data, then displays it on a web dashboard via Flask.

The code is in:
`D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\TimeTrackerDashboard\`

## The Problem

The Flask server starts fine but gets a **403 error** when requesting an OAuth2 token from ProShop. We need to debug why.

## Step 1: Read the existing working automations for reference

Other scripts in this project folder already successfully authenticate with ProShop. Read these to understand the working auth pattern:

```
Read the contents of D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\
```

Look specifically for:
- Any Python scripts that successfully call the ProShop API (especially `proshop_gui_v1.4.py`, `ExportToProShop.py`, or anything in the Dimension Extraction folder)
- How they handle OAuth2 authentication (token URL, headers, body format)
- How they load the client ID and secret
- What scopes they request
- The `.env` file format (check `traxis.env` files)

## Step 2: Compare auth approaches

The current dashboard script (`time_status_display_v1.0.py`) authenticates like this:

```python
POST https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
client_id=0615-12FB-C88D
client_secret=[from PROSHOP_CLIENT_SECRET env var]
scope=parts:rwdp+workorders:rwdp+users:r+toolpots:r
```

Compare this with how the working scripts authenticate. Check for differences in:
- Token URL
- Content-Type header
- Body encoding (form data vs JSON vs URL params)
- Scope format (plus signs vs spaces vs URL encoding)
- Any additional headers or parameters
- How the secret is loaded/parsed (watch for trailing whitespace, newlines, BOM characters)

## Step 3: Fix the dashboard script

Once you identify the difference, update `time_status_display_v1.0.py` to match the working pattern.

## Step 4: Test

Run the script:
```
"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe" "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\TimeTrackerDashboard\time_status_display_v1.0.py"
```

Verify:
1. Token request succeeds (no 403)
2. Employee data loads
3. Dashboard is accessible at http://localhost:8050

## Key Info

- ProShop URL: traxismfg.adionsystems.com
- API endpoint: /api/graphql
- Client ID: 0615-12FB-C88D (also in traxis.env as PROSHOP_CLIENT_ID)
- Client Secret: in traxis.env as PROSHOP_CLIENT_SECRET
- The .env file is at: `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations\TimeTrackerDashboard\traxis.env`
- Python: `C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe`
- Flask and requests are installed in that Python

## API Reference

There is comprehensive API documentation in the project. Check:
`D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\`

Look for any markdown files, docs, or reference files about the ProShop API, especially around authentication and available GraphQL queries for users, time clock, and time tracking.

## Important GraphQL Queries (known working from past testing)

```graphql
# List users
query {
  users(pageSize: 50) {
    records { id firstName lastName isActive }
  }
}

# User with time clock and tracking
query($userId: String!) {
  user(id: $userId) {
    id firstName lastName isActive
    timeClock(pageSize: 1) {
      records { clockPunchId punchDate inOrOut }
    }
    timeTracking(pageSize: 20) {
      records {
        id timeIn timeOut status operationNumber
        spentDoing qtyRun percentTime
        workOrderPlainText workCellPlainText
      }
    }
  }
}
```

## Required Scopes
- `users:r` — for user list, clock punches, time tracking per user
- `workorders:rwdp` — for work order data
- `parts:rwdp` — for part data
- `toolpots:r` — for work cells (machines)

Scopes must be enabled in ProShop Admin → Manage Authorizations for the API client.
