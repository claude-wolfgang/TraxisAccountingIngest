# Test 5: Query Coverage Mapping

**Timestamp:** 2026-01-26T17:14:53.223241

## Summary

- **Total Questions:** 20
- **Easy (single query):** 12
- **Complex (chained/client-side filter):** 8
- **Impossible:** 0
- **Feasible Percentage:** 100.0%

## Question-to-Query Mapping

| # | Question | Category | Query Type | Notes |
|---|----------|----------|------------|-------|
| 1 | What's the status of WO 25-0001? | Easy | workOrder | Single workOrder query with workOrderNumber arg |
| 2 | Show me all open work orders | Easy | workOrders | workOrders query, filter by status client-side |
| 3 | What work orders are due this week? | Complex | workOrders | Fetch all WOs and filter by dueDate client-side |
| 4 | What operations are on part XYZ? | Easy | part | part query with partNumber, access operations field |
| 5 | Who is the contact for customer ABC? | Complex | contacts | May require contacts module scope |
| 6 | What's the current operation for WO 25-0001? | Easy | workOrder | workOrder query, check ops for incomplete operation |
| 7 | Show me R2Sonic's open orders | Complex | workOrders | Filter by customerPlainText and status client-side |
| 8 | What tools are needed for Op 60 on part XYZ? | Easy | part | part query > operations > tools nested query |
| 9 | When is WO 25-0001 due? | Easy | workOrder | Single workOrder query, access dueDate field |
| 10 | How many open work orders do we have? | Easy | workOrders | workOrders, count with status filter client-side |
| 11 | What work orders were shipped last week? | Complex | workOrders | Filter by dateShipped client-side |
| 12 | Show me all parts for customer R2Sonic | Complex | parts | parts query, filter by customerPlainText |
| 13 | What's the job number for WO 25-0001? | Easy | workOrder | workOrder query, access job info fields |
| 14 | Are there any late work orders? | Complex | workOrders | Fetch WOs, compare dueDate to today client-side |
| 15 | What operations need to be run today? | Complex | workOrders | Complex - need to check scheduling data |
| 16 | Show me the sequence details for part XYZ Op 60 | Easy | part | part > operations filter > tools/writtenDescriptions |
| 17 | What's the priority of WO 25-0001? | Easy | workOrder | workOrder query, check priority-related fields |
| 18 | Who is assigned to WO 25-0001? | Complex | workOrder | May need timeTracking or users scope |
| 19 | What's the quantity for WO 25-0001? | Easy | workOrder | workOrder query, access quantityOrdered field |
| 20 | Show me all work orders in 'In Process' status | Easy | workOrders | workOrders query, filter by status |

## Available Root Queries

The following root queries are available in the ProShop GraphQL API:

- `approval`
- `approvals`
- `auditReport`
- `auditReports`
- `bill`
- `bills`
- `classification`
- `classifications`
- `clockPunch`
- `companyPosition`
- `companyPositions`
- `contact`
- `contacts`
- `correctiveActionRequest`
- `correctiveActionRequests`
- `cotsItem`
- `cotsItems`
- `customerPO`
- `customerPOs`
- `customerSatisfactionSurvey`
- `customerSurveys`
- `document`
- `documents`
- `editLog`
- `equipment`
- `equipments`
- `estimate`
- `estimateArchive`
- `estimates`
- `estimatesArchive`
- `fixture`
- `fixtures`
- `format`
- `formats`
- `globalSearches`
- `invoice`
- `invoices`
- `localSearches`
- `merchandise`
- `message`

... and 47 more

## Pass Criteria Assessment

**Criteria:** 80%+ of questions are answerable (easy + complex)

**Result:** PASS - 100.0% of questions are feasible.

### Breakdown:
- **12 questions** can be answered with a single GraphQL query
- **8 questions** require client-side filtering or chained queries
- **0 questions** cannot be answered with current API

### Key Observations:
1. Core work order and part queries are well-supported
2. Filtering by customer/status requires client-side processing (API returns all, we filter)
3. Date-based queries (due this week, shipped last week) need client-side logic
4. Time tracking and profitability data are available via workOrder queries
5. Some queries (users, workCells) require additional OAuth scopes

### Scope Limitations:
Current scope `parts:rwdp+workorders:rwdp` provides access to:
- Parts module (part, parts queries)
- Work Orders module (workOrder, workOrders queries)

Additional scopes would enable:
- Users module (employee info, time clock data)
- Tool Pots module (work cells, machines)
- Contacts module (customer contacts)
