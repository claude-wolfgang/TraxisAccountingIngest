# Project Structure

## Main Components

| Component | Location | Version | Status |
|-----------|----------|---------|--------|
| **ProShop Bridge** | ProShopBridge/ | v1.4.0 | Active — unified Fusion add-in (WO browser + CAM export + push) |
| **Time Tracker Dashboard** | TimeTrackerDashboard/ | v1.0 | Active — Flask :8050, employee status |
| **FASData Live Dashboard** | FASDataDashboard/ | v1.0 | Active — Flask :8070, CNC machine utilization |
| **Service Overseer** | Overseer/ | v1.2 | Active — Flask :8060, monitors all services |
| **FocasMonitor** | C:\FocasMonitor\ | — | Active — Windows Service, FOCAS CNC polling |
| ProgrammingTimer | ProgrammingTimer/ | v1.1.0 | Active — Fusion add-in, programming time tracking |
| GraphQL Module | proshop_graphql_v2.py | — | Standalone utility, still works |
| Fusion CAM Export | EXPORT TO PROSHOP.py | v7.0.0 | Legacy (superseded by Bridge) |
| ProShop Push GUI | proshop_gui_v1_5.py | — | Legacy (superseded by Bridge) |
| ProShopConnector | ProShopConnector/ | v1.6.0 | **Obsolete** — removed from Fusion, source archived |
| GenerateSetupSheet | Scripts/GenerateSetupSheet/ | v1.0.0 | Utility script |

## Services (see `services-architecture.md` for full details)

| Service | Port | Auto-Start | Managed By |
|---------|------|------------|------------|
| Time Tracker Dashboard | 8050 | Overseer | Overseer (process) |
| Service Overseer | 8060 | Manual / Startup folder | Self |
| FASData Live Dashboard | 8070 | Overseer | Overseer (process) |
| FocasMonitor | — | Windows (Automatic) | Windows + Overseer monitoring |

All accessible on LAN at `10.1.1.71:{port}`.

## File Locations
- **Working dir:** `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\1. Proshop Automations`
- **FocasMonitor:** `C:\FocasMonitor\` (installed as Windows Service)
- **FocasMonitor DB:** `C:\FASData\monitoring.db` (SQLite, read by FASData dashboard)
- **Fusion Scripts:** `C:\Users\TRAXIS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\Scripts\`
- **Fusion Add-Ins:** `C:\Users\TRAXIS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\`
  - Only `ProShopBridge/` deployed (ProShopConnector removed Feb 2026)
- **Fusion Posts:** `%appdata%\Autodesk\Autodesk Fusion 360\CAM\Posts\`
- **Exports:** `D:\Dropbox\MACHINE COMM Traxis\ProShop Exports\`
- **Setup Sheet Reference:** `D:\Dropbox\MACHINE COMM Traxis\ProShop Exports\setup_sheet_reference\`
- **Credentials:** `C:\Users\TRAXIS\.traxis.env` — single source of truth for ALL API creds
- **Credentials fallback:** `~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env` (shared)

## ProShop API
- OAuth 2.0 client credentials (active clients: `0615-12FB-C88D`, `B769-88F7-A69B`)
- GraphQL endpoint: `https://traxismfg.adionsystems.com/api/graphql`
- Part numbers are case-sensitive
- Fusion stores values in centimeters (convert: `value_cm / 2.54` for inches)
- `tool_bodyLength` is the internal param for "Length below holder" (NOT `tool_lengthBelowHolder`)

## Sync Reminder
ProShopBridge exists in TWO locations — always sync after edits:
```
cp "D:/Dropbox/.../ProShopBridge/FILE" "C:/Users/TRAXIS/AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns/ProShopBridge/FILE"
```
