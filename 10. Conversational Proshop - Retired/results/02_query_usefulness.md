# Test 2: Single-Query Usefulness

**Timestamp:** 2026-01-26T17:13:55.950154

## Summary

- **Total Queries Tested:** 8
- **Successful:** 8
- **With Data:** 8
- **Failed:** 0

## Query Results

| Query | Success | Has Data | Records | Response Time |
|-------|---------|----------|---------|---------------|
| Work Order Status | Yes | Yes | - | 770ms |
| Work Order Operations | Yes | Yes | - | 1036ms |
| List Work Orders | Yes | Yes | 20 | 1679ms |
| Parts Query | Yes | Yes | 20 | 1019ms |
| Single Part with Operations | Yes | Yes | 2 | 976ms |
| Work Order Time Tracking | Yes | Yes | - | 857ms |
| Work Order Profitability | Yes | Yes | 5 | 1650ms |
| Work Order with Part Info | Yes | Yes | - | 764ms |

## Fields Available Per Query

### Work Order Status
- Fields: dueDate, hoursTotalSpent, qtyComplete, quantityOrdered, status, workOrderNumber

### Work Order Operations
- Fields: ops, workOrderNumber

### List Work Orders
- Fields: dueDate, quantityOrdered, status, workOrderNumber

### Parts Query
- Fields: partDescription, partNumber

### Single Part with Operations
- Fields: operations, partDescription, partNumber

### Work Order Time Tracking
- Fields: hoursTotalSpent, runningTimeHoursActualLabor, setupTimeHoursActualLabel, timeTracking, workOrderNumber

### Work Order Profitability
- Fields: profitability, status, workOrderNumber

### Work Order with Part Info
- Fields: dueDate, part, status, workOrderNumber


## Errors Encountered


## Pass Criteria Assessment

**Criteria:** At least 5 common questions answerable with single query

**Result:** PASS - 8 queries return useful data.

### Scope Limitations
Current OAuth scope: `parts:rwdp+workorders:rwdp`

Some queries (users, workCells, customers) require additional scopes that are not granted.
The available scope provides access to parts and workorders modules, which are the core entities for conversational queries.
