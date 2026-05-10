# Claude Code Task: Update Utilization Thresholds

## What to Change

Update the utilization thresholds in ALL report-related files from the old values to:

- **Green (On Target):** ≥ 30%
- **Yellow (Below Target):** 10% to 29%
- **Red (Critical):** < 10%

## Files to Update

All files are in:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\
```

### 1. `generate_report.py`

Find:
```python
GREEN_THRESHOLD = 70
YELLOW_THRESHOLD = 50
```

Replace with:
```python
GREEN_THRESHOLD = 30
YELLOW_THRESHOLD = 10
```

### 2. `build_report.js`

Find any references to the old threshold values (70 and 50) in status logic, labels, or display text. Update to 30 and 10. The thresholds are read from `report_data.json` so the main logic should follow `data.green_threshold` and `data.yellow_threshold` — but verify that any hardcoded values or display labels are also updated.

### 3. `send_daily_report.py`

Same as above — find any hardcoded threshold values (70 and 50) and update to 30 and 10. This file was just created and likely reads thresholds from the JSON data, but verify.

## Verification

After making changes, run:
```
"C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe" generate_report.py
```

Check that `report_data.json` in the output shows:
```json
"green_threshold": 30,
"yellow_threshold": 10,
```

And that the chart PNG files show the threshold lines at the correct positions (30% and 10%).
