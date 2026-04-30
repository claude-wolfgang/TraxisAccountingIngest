# ProShop → QBO Invoicing Sync Problem

## Issue
ProShop's QBO connector is **unidirectional** (ProShop → QBO only). When invoices are created in QuickBooks Online outside of ProShop's native invoicing workflow, ProShop has no mechanism to receive status updates back.

## Symptom
After invoicing shipped work orders in QBO:
- Invoices are created and sent in QBO ✓
- Work order line items remain marked as **"Shipped"** in ProShop (not "Invoiced")
- ProShop has no visibility into which items have been invoiced in QBO

## Root Cause
The ProShop-QBO integration uses the QuickBooks Web Connector, which:
- Tracks what was sent to QBO in an internal database on the QBS Server
- Does **not** push QBO status changes back into ProShop
- Does **not** expose a readable field in ProShop to indicate "sent to QBO" status

## Current State
- No visible ProShop status field indicates which work orders have been invoiced in QBO
- The Web Connector database exists but is not accessible via ProShop UI or API
- There is no automatic status synchronization between QBO and ProShop

## Impact
Work order status in ProShop becomes out of sync with invoicing reality. Line items show "Shipped" indefinitely, even after invoices have been sent to customers and recorded in QBO, making it difficult to track which jobs have been fully invoiced.
