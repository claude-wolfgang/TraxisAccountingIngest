# FOCAS Machine Monitor

A Windows service that monitors FANUC CNC machines via FOCAS protocol and records data to a SQLite database.

## Setup

### Prerequisites

1. **.NET 6.0 Runtime (x86)** - Download from https://dotnet.microsoft.com/download/dotnet/6.0
   - You need the **x86** version (32-bit) for FOCAS DLL compatibility
   - Download "Run desktop apps" → ".NET Runtime" → Windows x86

2. **FOCAS DLLs** - Copy these to the project folder:
   - Fwlib32.dll
   - fwlibe1.dll
   - fwlib30i.dll
   - (others from your focas-test folder)

### Installation

1. Copy this entire folder to the collector PC (e.g., `C:\FocasMonitor\`)

2. Copy FOCAS DLLs from your focas-test folder into this folder

3. Edit `machines.json` to configure your machines

4. **Test first** - Double-click `Run-Console.bat` to test in console mode
   - Watch for connection errors
   - Press Ctrl+C to stop

5. **Install as service** - Right-click `Install-Service.bat` → Run as administrator

## Configuration

Edit `machines.json`:

```json
{
  "pollIntervalSeconds": 60,
  "databasePath": "C:\\FASData\\monitoring.db",
  "machines": [
    {
      "id": "M2",
      "name": "FANUC Mill 2",
      "type": "Mill",
      "ip": "10.1.1.159",
      "port": 8193,
      "enabled": true
    }
  ]
}
```

- **pollIntervalSeconds** - How often to poll (60 = once per minute)
- **databasePath** - Where to store the SQLite database
- **machines** - List of machines to monitor
  - Set `enabled: false` to skip a machine

## Data Storage

Data is stored in SQLite at `C:\FASData\monitoring.db`

Each poll records:
- Timestamp
- Machine ID and name
- Connection status
- Mode (MEM, MDI, JOG, etc.)
- Run status (STOP, STRT, HOLD)
- Program number
- Spindle speed (RPM)
- Feed rate
- Override percentages
- Emergency/alarm status
- Axis positions (X, Y, Z)

## Querying Data

Use any SQLite tool (DB Browser for SQLite, DBeaver, etc.) or command line:

```sql
-- Today's samples for one machine
SELECT * FROM machine_samples 
WHERE machine_id = 'M2' 
AND timestamp >= date('now')
ORDER BY timestamp DESC;

-- Utilization summary (running vs stopped)
SELECT 
    machine_id,
    date(timestamp) as day,
    COUNT(*) as total_samples,
    SUM(CASE WHEN run_status = 'STRT' THEN 1 ELSE 0 END) as running,
    ROUND(100.0 * SUM(CASE WHEN run_status = 'STRT' THEN 1 ELSE 0 END) / COUNT(*), 1) as utilization_pct
FROM machine_samples
WHERE connected = 1
GROUP BY machine_id, date(timestamp);
```

## Service Management

```
sc query FocasMonitor     # Check status
sc stop FocasMonitor      # Stop service
sc start FocasMonitor     # Start service
```

Or use Services (services.msc)

## Troubleshooting

**Service won't start:**
- Check Event Viewer → Windows Logs → Application
- Verify FOCAS DLLs are in the publish folder
- Verify .NET 6 x86 runtime is installed

**Connection failures:**
- Verify machine is powered on
- Verify IP address in machines.json
- Test with: `Test-NetConnection -ComputerName 10.1.1.x -Port 8193`
- Check FOCAS is enabled on CNC ([SYSTEM] → [EMBED PORT] → [FOCAS2])

**Missing data:**
- Check C:\FASData\monitoring.db exists
- Check logs in Event Viewer

---

Traxis Manufacturing - January 2026
