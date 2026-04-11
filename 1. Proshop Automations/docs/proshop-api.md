# ProShop API Reference Summary

Full reference: `D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\proshop_api_reference.md`

## Critical Rules
- Scope param is REQUIRED on token request (otherwise HTML error page)
- `includeDeprecated` param is REQUIRED on introspection `fields()` — value can be `true` or `false`, but must be present
- Part numbers are case-sensitive
- Default pageSize is 20 — use `pageSize: 500` for larger results
- No pagination beyond page 1 (no offset/cursor)
- `parts` query filter is BROKEN — use `updatePart` which can find parts
- `customerPONumber` nested filter doesn't work — filter client-side
- Written Descriptions via API are PERMANENTLY broken (legacyId bug) — use Selenium

## OAuth Clients
| Client | Name | Scope | Status |
|--------|------|-------|--------|
| `0615-12FB-C88D` | FusionConnector | `parts:rwdp+workorders:rwdp+users:r` | **Active** |
| `3923-9C1C-7291` | Fusion Integration | `parts:rwdp+workorders:rwdp` | **BROKEN** (corrupted) |
| `99EB-27E6-8915` | Dimension Extraction | `parts:rwdp+workorders:rwdp+users:r` | Available |

**WARNING**: Editing OAuth client scope in ProShop admin can corrupt the client. The 3923 client was permanently broken after scope edits — even the original scope stopped working. Always test with `curl` after saving scope changes. Consider creating a new client instead of editing existing ones.

## Scope Documentation
- Format: `SCOPE_NAME:[{r|w|d|p}]` (space or `+` delimited)
- `r`=read, `w`=write, `d`=delete, `p`=prefs
- Scopes are space-delimited per docs, but `+` works (URL-encodes to space)
- Elevated permissions (no rwdp suffix): `securityadmin`, `systemconfig`, `sensitivedata`, `itarokay`
- **`users` module**: only `users:r` actually works via token — `users:rwdp`/`users:rw`/`users:w` all rejected even when saved in admin UI. ProShop appears to cap users at read-only for API clients.

## Time Tracking API (discovered via introspection)
Available mutations (require `{"write":["users"]}` — currently blocked):
- `timeTrackingLogin(data: TimeTrackingLoginInput)` — start timer
- `timeTrackingLogout(id, timeOut, userId)` — stop timer
- `timeTrackingPause(id, timeOut, userId)` — pause
- `timeTrackingUnpause(id, userId)` — resume

TimeTrackingLoginInput fields: workOrder, operationNumber, operator, category (REQUIRED), spentDoing, timeIn, timeOut, percentTime, qtyRun, totalQty, totalQtyOption, workCell, percentWorkCellTime, whenRunTargetPercent

Valid categories: running, setup, manufacturing planning, programming, pp check, inspection / first art, troubleshoot, break down, rework, purchasing, shipping prep, maintenance, receiving

TimeTrackingEntry fields: id, status (ACTIVE/LOGGED_OUT), timeIn, timeOut, operationNumber, operator, operatorPlainText, workOrder, workOrderPlainText, category, spentDoing, qtyRun, totalQty, totalTimePaused, lastPauseTime, workCell, workCellPlainText, percentTime, percentWorkCellTime, addToKBase, whenRunTargetPercent, totalQtyOption

## Key Query Patterns
- `workOrders(filter: {year: "2026"}, pageSize: 500)` — year filter works
- `workOrder(workOrderNumber: "26-0001")` — single WO lookup (includes ops)
- `workOrderFiles { records { title fileUrl } }` — NOT `files`
- `ops → partOperation → writtenDescriptions` — reading written desc
- `contact(name: "ATO1")` — lookup by prefix
- `contacts(filter: {companyName: "..."})` — reverse lookup WORKS

## Mutation Path
`updatePart(partNumber, data: { operations: [{ selector: {field: opNumber, value: "60"}, data: { tools: [...], writtenDescriptions: {...}, inProcessCheck: [...] } }] })`

## Field Name Gotcha
- Query: `operationNumber` (reading)
- Mutation selector: `opNumber` (writing)
- These are different names for the same concept

## GraphQL Field Types
- `part` is a nested object: `part { partNumber partName }` (not a scalar)
- `partRev` is a scalar string
- `ops` is nested: `ops { records { operationNumber operationDescription proshopUrl isOpComplete setupTime runTime } }`
- `workCenter` on WO ops is OBJECT type (WorkCell) — needs sub-selections, requires `toolpots:r`
- `workCenterPlainText` on WO ops is String — also requires `toolpots:r`

## Scheduling API (Feb 2026 probe)
- **`workCenter` IS WRITABLE** on `UpdateWorkOrderOperationInput` (String) and `UpdatePartOperationInput` (String)
- `UpdateWorkOrderOperationInput` full fields: `breakdownComplete`, `certifiedToRun`, `firstArticleComplete`, `isOpComplete`, `opNumber`, `percentComplete`, `perOpQtyComplete`, `qqNextOp`, `workCenter`
- `UpdateWorkCellInput` scheduling fields: `isScheduledResource`, `scheduleEfficiencyMultiplier`, `defaultSchedulePlacementRule/Days`, `hideOnSchedule`, `isBottleneckResource`, `warnOnScheduleWhenPartsQueued`, `displayPartImageInWorkQueue`
- `workCell`/`workCells` queries + mutations exist but require `toolpots:r` scope
- `workCell(potId: "Mill-1")` — singular query uses `potId` argument
- `__type` introspection returns null for WorkCell types without `toolpots:r` (ProShop bug)
- **Next step**: Create NEW OAuth client with `toolpots:rwdp` scope added
- Full probe results: `scheduling_probe_results.txt`
