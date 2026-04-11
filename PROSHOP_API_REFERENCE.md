# ProShop API Reference

Complete reference for ProShop ERP GraphQL API at Traxis Manufacturing.

---

## Endpoints

| Endpoint | URL |
|----------|-----|
| **Base URL** | `https://traxismfg.adionsystems.com` |
| **GraphQL API** | `https://traxismfg.adionsystems.com/api/graphql` |
| **OAuth Token** | `https://traxismfg.adionsystems.com/home/member/oauth/accesstoken` |
| **Web UI** | `https://traxismfg.adionsystems.com/procnc` |

---

## OAuth 2.0 Credentials

### Active Client: FusionConnector
```
PROSHOP_CLIENT_ID=0615-12FB-C88D
PROSHOP_CLIENT_SECRET=1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32
PROSHOP_SCOPE=parts:rwdp+workorders:rwdp+users:r
```

### Backup Client: Dimension Extraction
```
PROSHOP_CLIENT_ID=99EB-27E6-8915
PROSHOP_CLIENT_SECRET=220985BF7EEA5A6FC0C0AB3F603FAE099A93EB6146AFC1C4346B8BBB7654FE70
PROSHOP_SCOPE=parts:rwdp+workorders:rwdp+users:r
```

### BROKEN Client: Fusion Integration (scope corrupted)
```
PROSHOP_CLIENT_ID=3923-9C1C-7291
PROSHOP_CLIENT_SECRET=0C6B59BA79E959342830EDA69E4294549A07EF14561DE3BDC16C6F47FCF8FD81
PROSHOP_SCOPE=parts:rwdp+workorders:rwdp
```

### Web Login (for Selenium workarounds)
```
PROSHOP_USERNAME=tbuerkle
PROSHOP_PASSWORD=5tgbNHY67ujm
```

### Credentials File Location
- Local: `C:\Users\TRAXIS\.traxis.env`
- Shared: `~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env`
- Project: `1. Proshop Automations\.traxis.env`

---

## Authentication

### Token Request (Client Credentials Flow)
```bash
curl -X POST https://traxismfg.adionsystems.com/home/member/oauth/accesstoken \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=0615-12FB-C88D" \
  -d "client_secret=1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32" \
  -d "scope=parts:rwdp+workorders:rwdp+users:r"
```

### GraphQL Request
```bash
curl -X POST https://traxismfg.adionsystems.com/api/graphql \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ workOrders(pageSize: 5) { totalRecords } }"}'
```

---

## Scope Documentation

### Format
`SCOPE_NAME:[{r|w|d|p}]` — space or `+` delimited

| Letter | Permission |
|--------|------------|
| `r` | Read |
| `w` | Write |
| `d` | Delete |
| `p` | Prefs |

### Available Scopes
- `parts:rwdp` — Part records
- `workorders:rwdp` — Work order records
- `users:r` — User records (READ ONLY — write permissions blocked for API clients)
- `toolpots:r` — Work cells / machines (needed for scheduling)
- `contacts:r` — Customer/vendor contacts

### Elevated Permissions (no rwdp suffix)
- `securityadmin`
- `systemconfig`
- `sensitivedata`
- `itarokay`

---

## Critical Rules & Gotchas

### MUST DO
1. **Scope param is REQUIRED** on token request — omitting returns HTML error page
2. **`includeDeprecated` is REQUIRED** on introspection `fields()` — value can be `true` or `false`
3. **Use `pageSize: 500`** — default is only 20 records

### FIELD NAME GOTCHA
- Query: `operationNumber` (when reading)
- Mutation selector: `opNumber` (when writing)
- These are different names for the same concept!

### BROKEN FEATURES
- `parts` query filter is **BROKEN** — use `updatePart` which can find parts
- `customerPONumber` nested filter doesn't work — filter client-side
- Written Descriptions via API are **PERMANENTLY BROKEN** (legacyId bug) — use Selenium
- No pagination beyond page 1 (no offset/cursor support)

### WARNINGS
- Part numbers are **case-sensitive**
- Editing OAuth client scope in ProShop admin can **corrupt the client** — test with curl after saving
- The 3923 client was permanently broken after scope edits

---

## Key Query Patterns

### Work Orders
```graphql
# List work orders by year
query {
  workOrders(filter: {year: "2026"}, pageSize: 500) {
    totalRecords
    records {
      workOrderNumber
      status
      partRev
      part { partNumber partName }
    }
  }
}

# Single work order with operations
query {
  workOrder(workOrderNumber: "26-0001") {
    workOrderNumber
    status
    ops {
      records {
        operationNumber
        operationDescription
        isOpComplete
        setupTime
        runTime
        proshopUrl
      }
    }
  }
}

# Work order files
query {
  workOrder(workOrderNumber: "26-0001") {
    workOrderFiles { records { title fileUrl } }
  }
}
```

### Parts
```graphql
# Part with operations and written descriptions
query {
  part(partNumber: "12345") {
    partNumber
    partName
    operations {
      records {
        operationNumber
        writtenDescriptions { records { description } }
      }
    }
  }
}
```

### Contacts
```graphql
# Lookup by prefix
query {
  contact(name: "ATO1") { companyName }
}

# Reverse lookup by company name
query {
  contacts(filter: {companyName: "ACME Corp"}) {
    records { name companyName }
  }
}
```

---

## Key Mutation Patterns

### Update Part Operation
```graphql
mutation {
  updatePart(
    partNumber: "12345"
    data: {
      operations: [{
        selector: {field: opNumber, value: "60"}
        data: {
          tools: [...]
          writtenDescriptions: {...}
          inProcessCheck: [...]
        }
      }]
    }
  ) {
    partNumber
  }
}
```

### Update Work Order Operation
```graphql
mutation {
  updateWorkOrderOperation(
    workOrderNumber: "26-0001"
    data: {
      opNumber: "10"
      isOpComplete: true
      percentComplete: 100
    }
  ) {
    workOrderNumber
  }
}
```

---

## Time Tracking API

Requires `{"write":["users"]}` scope — **currently blocked for API clients**.

### Mutations
- `timeTrackingLogin(data: TimeTrackingLoginInput)` — start timer
- `timeTrackingLogout(id, timeOut, userId)` — stop timer
- `timeTrackingPause(id, timeOut, userId)` — pause
- `timeTrackingUnpause(id, userId)` — resume

### TimeTrackingLoginInput Fields
```
workOrder, operationNumber, operator, category (REQUIRED), spentDoing,
timeIn, timeOut, percentTime, qtyRun, totalQty, totalQtyOption,
workCell, percentWorkCellTime, whenRunTargetPercent
```

### Valid Categories
```
running, setup, manufacturing planning, programming, pp check,
inspection / first art, troubleshoot, break down, rework,
purchasing, shipping prep, maintenance, receiving
```

### TimeTrackingEntry Fields
```
id, status (ACTIVE/LOGGED_OUT), timeIn, timeOut, operationNumber,
operator, operatorPlainText, workOrder, workOrderPlainText,
category, spentDoing, qtyRun, totalQty, totalTimePaused,
lastPauseTime, workCell, workCellPlainText, percentTime,
percentWorkCellTime, addToKBase, whenRunTargetPercent, totalQtyOption
```

---

## Scheduling API

### Writable Fields on UpdateWorkOrderOperationInput
```
breakdownComplete, certifiedToRun, firstArticleComplete, isOpComplete,
opNumber, percentComplete, perOpQtyComplete, qqNextOp, workCenter
```

### UpdateWorkCellInput Scheduling Fields
```
isScheduledResource, scheduleEfficiencyMultiplier,
defaultSchedulePlacementRule, defaultSchedulePlacementDays,
hideOnSchedule, isBottleneckResource, warnOnScheduleWhenPartsQueued,
displayPartImageInWorkQueue
```

### WorkCell Queries
- Require `toolpots:r` scope
- `workCell(potId: "Mill-1")` — singular query uses `potId` argument
- `__type` introspection returns null without `toolpots:r` (ProShop bug)

---

## Available Query Fields (89 total)

```
approval, approvals, auditReport, auditReports, bill, bills,
classification, classifications, clockPunch, companyPosition,
companyPositions, contact, contacts, correctiveActionRequest,
correctiveActionRequests, cotsItem, cotsItems, customerPO, customerPOs,
customerSatisfactionSurvey, customerSurveys, document, documents,
editLog, equipment, equipments, estimate, estimateArchive, estimates,
estimatesArchive, fixture, fixtures, format, formats, globalSearches,
invoice, invoices, localSearches, merchandise, message, messages,
moduleConfiguration, nonConformanceReport, nonConformanceReports,
packingSlip, packingSlips, par, pars, part, partArchive, parts,
partsArchive, purchaseOrder, purchaseOrders, qualityManual,
qualityManualSection, qualityProcedure, qualityProcedures, quote,
quotes, returnMaterialAuthorization, returnMaterialAuthorizations,
riskAndOpportunity, risksAndOpportunities, rta, rtas, session,
smartTrips, standards, standardSection, systemConfig, systemSearches,
task, tasks, tool, tools, training, trainings, user, users, vendorPO,
vendorPOs, workCell, workCells, workOrder, workOrders, writeCheckouts
```

---

## Available Mutations (100+ total)

### Add Operations
```
addBill, addClassification, addCompanyPosition, addContact,
addCorrectiveActionRequest, addCOTS, addCustomerPo, addCustomLink,
addDocument, addEquipment, addEstimate, addEstimateOpComponents,
addFixture, addInvoice, addNCR, addPackingSlip, addPart,
addPartOpComponents, addPreventiveActionRequest, addPurchaseOrder,
addQualityManual, addQualityProcedure, addQuote, addRMA, addRTA,
addSavedSearch, addStandard, addTask, addTimeClockPunch, addTool,
addTraining, addUser, addWorkCell, addWorkOrder
```

### Update Operations
```
updateBill, updateClassification, updateCompanyPosition, updateContact,
updateCorrectiveActionRequest, updateCOTS, updateCustomerPo,
updateCustomLink, updateDocument, updateEffectivenessNumbers,
updateEquipment, updateEstimate, updateFixture, updateInvoice,
updateNCR, updatePackingSlip, updatePart, updatePartOperation,
updatePreventiveActionRequest, updatePurchaseOrder, updateQualityManual,
updateQualityProcedure, updateQuote, updateRMA, updateRTA,
updateSavedSearch, updateStandard, updateSystemSettings, updateTask,
updateTimeClockPunch, updateTimeTracking, updateTool, updateTraining,
updateUser, updateUserDisplayPrefs, updateUserPrefs,
updateUserQuickJumpPrefs, updateWorkCell, updateWorkCellPocket,
updateWorkOrder, updateWorkOrderIPC, updateWorkOrderOperation
```

### Delete Operations
```
deleteBill, deleteClassification, deleteCompanyPosition, deleteContact,
deleteCorrectiveActionRequest, deleteCOTS, deleteCustomerPo,
deleteCustomLink, deleteDocument, deleteEquipment, deleteEstimate,
deleteEstimateOpComponents, deleteFixture, deleteInvoice, deleteNCR,
deletePackingSlip, deletePart, deletePartOpComponents,
deletePreventiveActionRequest, deletePurchaseOrder, deleteQualityManual,
deleteQualityProcedure, deleteQuote, deleteRMA, deleteRTA,
deleteSavedSearch, deleteStandard, deleteTask, deleteTimeClockPunch,
deleteTool, deleteTraining, deleteUser, deleteWorkCell, deleteWorkOrder,
deleteWriteCheckout
```

### Special Operations
```
finalizeWorkOrder, overwriteBill, overwriteCompanyPosition,
overwriteContact, overwriteCorrectiveActionRequest, overwriteCOTS,
overwriteCustomerPo, overwriteFixture, overwriteInvoice,
overwritePurchaseOrder, overwriteRTA, overwriteUser, overwriteWorkCell,
timeClockPunchIn, timeClockPunchOut, timeTrackingLogin,
timeTrackingLogout, timeTrackingPause, timeTrackingUnpause
```

---

## Python Client Example

```python
import requests
import time

class ProShopClient:
    BASE_URL = "https://traxismfg.adionsystems.com"
    TOKEN_URL = f"{BASE_URL}/home/member/oauth/accesstoken"
    GRAPHQL_URL = f"{BASE_URL}/api/graphql"

    def __init__(self, client_id, client_secret, scope):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.access_token = None
        self.token_expires_at = 0
        self.session = requests.Session()

    def authenticate(self):
        response = self.session.post(
            self.TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope
            }
        )
        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            self.token_expires_at = time.time() + data.get("expires_in", 86400) - 60
            return True
        return False

    def execute(self, query, variables=None):
        if not self.access_token or time.time() >= self.token_expires_at:
            self.authenticate()

        response = self.session.post(
            self.GRAPHQL_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            },
            json={"query": query, "variables": variables or {}}
        )
        return response.json()

# Usage
client = ProShopClient(
    "0615-12FB-C88D",
    "1265BF3FE51C7972AD6B26236002409F6FD75149BDAD86CA844A78B02CE33E32",
    "parts:rwdp+workorders:rwdp+users:r"
)
result = client.execute('{ workOrders(pageSize: 5) { totalRecords } }')
print(result)
```

---

## Related Files in This Project

| File | Description |
|------|-------------|
| `1. Proshop Automations\.traxis.env` | Credentials file |
| `1. Proshop Automations\docs\proshop-api.md` | Original API notes |
| `10. Conversational Proshop\src\proshop_client.py` | Full Python client with caching |
| `10. Conversational Proshop\proshop_schema_full.json` | Complete GraphQL schema |
| `12. FASData Implementation\proshop_api_discovery.json` | API discovery results |
| `1. Proshop Automations\FASDataDashboard\proshop_client.py` | Shop Hub client |

---

*Last updated: February 2026*
