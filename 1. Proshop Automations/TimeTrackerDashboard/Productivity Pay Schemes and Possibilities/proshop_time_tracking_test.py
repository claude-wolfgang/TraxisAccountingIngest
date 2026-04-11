#!/usr/bin/env python3
"""
ProShop Time Tracking & Profitability API Test Script
Tests the queries needed for employee feedback system.

Usage:
    python proshop_time_tracking_test.py
"""

import requests
import json
from datetime import datetime, timedelta

# === CONFIGURATION ===
CLIENT_ID = "3923-9C1C-7291"
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
SCOPES = "parts:rwdp+workorders:rwdp+users:r+toolpots:r"

# Output file for results
OUTPUT_FILE = "proshop_api_test_results.json"


def get_access_token(client_secret: str) -> str:
    """Authenticate and get access token."""
    print("\n🔐 Authenticating with ProShop...")
    
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "scope": SCOPES
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Authentication failed: {response.status_code}")
        print(response.text)
        raise Exception("Authentication failed")
    
    token = response.json().get("access_token")
    print("✅ Authentication successful")
    return token


def run_query(token: str, query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    response = requests.post(GRAPHQL_URL, headers=headers, json=payload)
    return response.json()


def test_users_list(token: str) -> dict:
    """Get list of all users."""
    print("\n📋 Testing: List all users...")
    
    query = """
    query {
      users(pageSize: 50) {
        totalRecords
        records {
          id
          firstName
          lastName
          isActive
          emailAddress
          workShift
        }
      }
    }
    """
    
    result = run_query(token, query)
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("users"):
        users = result["data"]["users"]
        print(f"  ✅ Found {users['totalRecords']} users")
        for u in users.get("records", [])[:10]:
            status = "✓" if u.get("isActive") else "✗"
            print(f"     [{status}] {u.get('firstName')} {u.get('lastName')} (ID: {u.get('id')})")
    else:
        print(f"  ⚠️ No data returned")
    
    return result


def test_single_user_with_time_data(token: str, user_id: str) -> dict:
    """Get a single user with their time clock and time tracking data."""
    print(f"\n👤 Testing: User '{user_id}' with time data...")
    
    query = """
    query($userId: String!) {
      user(id: $userId) {
        id
        firstName
        lastName
        isActive
        timeClock(pageSize: 20) {
          totalRecords
          records {
            clockPunchId
            punchDate
            inOrOut
            operatorPlainText
            creationMachine
          }
        }
        timeTracking(pageSize: 20) {
          totalRecords
          records {
            id
            timeIn
            timeOut
            status
            operationNumber
            spentDoing
            qtyRun
            percentTime
            workOrderPlainText
            workCellPlainText
          }
        }
      }
    }
    """
    
    result = run_query(token, query, {"userId": user_id})
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("user"):
        user = result["data"]["user"]
        print(f"  ✅ Found user: {user.get('firstName')} {user.get('lastName')}")
        
        tc = user.get("timeClock", {})
        print(f"  📍 Clock punches: {tc.get('totalRecords', 0)} total")
        for p in tc.get("records", [])[:5]:
            print(f"     {p.get('punchDate')} - {p.get('inOrOut')}")
        
        tt = user.get("timeTracking", {})
        print(f"  ⏱️ Time tracking entries: {tt.get('totalRecords', 0)} total")
        for t in tt.get("records", [])[:5]:
            print(f"     {t.get('timeIn')} - {t.get('status')} - WO: {t.get('workOrderPlainText')}")
    else:
        print(f"  ⚠️ User not found or no data")
    
    return result


def test_clock_punch_data(token: str) -> dict:
    """Get clock punch data via the clockPunch query."""
    print("\n🕐 Testing: Clock punch data (latestClockPunches)...")
    
    query = """
    query {
      clockPunch {
        latestClockPunches(pageSize: 50) {
          totalRecords
          records {
            clockPunchId
            punchDate
            inOrOut
            operator
            creationMachine
            flNeedsReview
          }
        }
      }
    }
    """
    
    result = run_query(token, query)
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("clockPunch"):
        cp = result["data"]["clockPunch"]
        lcp = cp.get("latestClockPunches", {})
        print(f"  ✅ Found {lcp.get('totalRecords', 0)} recent clock punches")
        for p in lcp.get("records", [])[:10]:
            print(f"     {p.get('punchDate')} | {p.get('operator')} | {p.get('inOrOut')}")
    else:
        print(f"  ⚠️ No clock punch data returned")
    
    return result


def test_work_orders_with_profitability(token: str) -> dict:
    """Get work orders with profitability data."""
    print("\n💰 Testing: Work orders with profitability...")
    
    query = """
    query {
      workOrders(pageSize: 20) {
        totalRecords
        records {
          workOrderNumber
          status
          quantityOrdered
          qtyComplete
          dueDate
          hoursTotalSpent
          runningTimeHoursActualLabor
          setupTimeHoursActualLabel
          profitability {
            profit
            profitMargin
            profitPerDLH
            grossProfit
            grossProfitMargin
            dlh
            totalCost
            dollarsConsideredBilled
          }
        }
      }
    }
    """
    
    result = run_query(token, query)
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("workOrders"):
        wos = result["data"]["workOrders"]
        print(f"  ✅ Found {wos.get('totalRecords', 0)} work orders")
        for wo in wos.get("records", [])[:10]:
            profit = wo.get("profitability", {})
            margin = profit.get("profitMargin") or 0
            print(f"     WO {wo.get('workOrderNumber')} | {wo.get('status')} | Margin: {margin:.1f}% | Hours: {wo.get('hoursTotalSpent')}")
    else:
        print(f"  ⚠️ No work order data returned")
    
    return result


def test_work_order_time_tracking(token: str, wo_number: str) -> dict:
    """Get time tracking entries for a specific work order."""
    print(f"\n⏱️ Testing: Time tracking for WO {wo_number}...")
    
    query = """
    query($woNumber: String!) {
      workOrder(workOrderNumber: $woNumber) {
        workOrderNumber
        status
        hoursTotalSpent
        timeTracking(pageSize: 50) {
          totalRecords
          records {
            id
            timeIn
            timeOut
            status
            operationNumber
            operatorPlainText
            spentDoing
            qtyRun
            percentTime
            workCellPlainText
          }
        }
        ops(pageSize: 20) {
          records {
            operationNumber
            operationDescription
            setupTime
            setupTimeSpent
            runTime
            runTimeSpent
            isOpComplete
            workCenterPlainText
          }
        }
      }
    }
    """
    
    result = run_query(token, query, {"woNumber": wo_number})
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("workOrder"):
        wo = result["data"]["workOrder"]
        print(f"  ✅ Found WO: {wo.get('workOrderNumber')} ({wo.get('status')})")
        print(f"     Total hours spent: {wo.get('hoursTotalSpent')}")
        
        tt = wo.get("timeTracking", {})
        print(f"  ⏱️ Time entries: {tt.get('totalRecords', 0)}")
        for t in tt.get("records", [])[:5]:
            print(f"     {t.get('operatorPlainText')} | Op {t.get('operationNumber')} | {t.get('spentDoing')} | {t.get('status')}")
        
        ops = wo.get("ops", {})
        print(f"  📋 Operations: {len(ops.get('records', []))}")
        for op in ops.get("records", [])[:5]:
            complete = "✓" if op.get("isOpComplete") else "○"
            print(f"     [{complete}] Op {op.get('operationNumber')}: {op.get('operationDescription', '')[:40]}")
    else:
        print(f"  ⚠️ Work order not found")
    
    return result


def test_work_cells(token: str) -> dict:
    """Get work cells (machines) for utilization tracking."""
    print("\n🏭 Testing: Work cells (machines)...")
    
    query = """
    query {
      workCells(pageSize: 50) {
        totalRecords
        records {
          potId
          cellDescription
          type
          isActive
          defaultLaborRate
          scheduledHoursPerDay
        }
      }
    }
    """
    
    result = run_query(token, query)
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("workCells"):
        wcs = result["data"]["workCells"]
        print(f"  ✅ Found {wcs.get('totalRecords', 0)} work cells")
        for wc in wcs.get("records", [])[:15]:
            status = "✓" if wc.get("isActive") else "✗"
            hrs = wc.get("scheduledHoursPerDay") or "-"
            print(f"     [{status}] {wc.get('potId')}: {wc.get('cellDescription', '')[:35]} | {hrs} hrs/day")
    else:
        print(f"  ⚠️ No work cell data returned")
    
    return result


def test_recent_completed_work_orders(token: str) -> dict:
    """Get recently completed work orders for profitability analysis."""
    print("\n📊 Testing: Recent completed work orders...")
    
    # Try filtering by status
    query = """
    query {
      workOrders(pageSize: 30, filter: { status: { eq: "Complete" } }) {
        totalRecords
        records {
          workOrderNumber
          status
          dateShipped
          quantityOrdered
          hoursTotalSpent
          profitability {
            profit
            profitMargin
            dlh
          }
        }
      }
    }
    """
    
    result = run_query(token, query)
    
    if "errors" in result:
        print(f"  ⚠️ Filter query failed, trying without filter...")
        # Try without filter
        query2 = """
        query {
          workOrders(pageSize: 50) {
            totalRecords
            records {
              workOrderNumber
              status
              dateShipped
              quantityOrdered
              hoursTotalSpent
              profitability {
                profit
                profitMargin
                dlh
              }
            }
          }
        }
        """
        result = run_query(token, query2)
        
        if result.get("data", {}).get("workOrders"):
            wos = result["data"]["workOrders"]
            complete = [wo for wo in wos.get("records", []) if wo.get("status") == "Complete"]
            print(f"  ✅ Found {len(complete)} complete WOs (of {wos.get('totalRecords')} total)")
            for wo in complete[:10]:
                profit = wo.get("profitability", {})
                margin = profit.get("profitMargin") or 0
                print(f"     WO {wo.get('workOrderNumber')} | Shipped: {wo.get('dateShipped')} | Margin: {margin:.1f}%")
    elif result.get("data", {}).get("workOrders"):
        wos = result["data"]["workOrders"]
        print(f"  ✅ Found {wos.get('totalRecords', 0)} complete work orders")
        for wo in wos.get("records", [])[:10]:
            profit = wo.get("profitability", {})
            margin = profit.get("profitMargin") or 0
            print(f"     WO {wo.get('workOrderNumber')} | Shipped: {wo.get('dateShipped')} | Margin: {margin:.1f}%")
    
    return result


def test_session_info(token: str) -> dict:
    """Get current session info."""
    print("\n🔑 Testing: Session info...")
    
    query = """
    query {
      session {
        user {
          id
          firstName
          lastName
        }
      }
    }
    """
    
    result = run_query(token, query)
    
    if "errors" in result:
        print(f"  ❌ Error: {result['errors']}")
    elif result.get("data", {}).get("session"):
        session = result["data"]["session"]
        user = session.get("user", {})
        print(f"  ✅ Logged in as: {user.get('firstName')} {user.get('lastName')} (ID: {user.get('id')})")
    else:
        print(f"  ⚠️ No session data")
    
    return result


def main():
    print("=" * 60)
    print("ProShop Time Tracking & Profitability API Test")
    print("=" * 60)
    print(f"\nTarget: {GRAPHQL_URL}")
    print(f"Client ID: {CLIENT_ID}")
    
    # Get client secret - hardcode option for Windows compatibility
    print("\n" + "-" * 40)
    print("Enter your client secret below.")
    print("(Or hardcode it in the script for easier testing)")
    print("-" * 40)
    
    # OPTION: Hardcode secret here for testing (delete after!)
    # client_secret = "YOUR_SECRET_HERE"
    
    client_secret = input("Client secret: ").strip()
    
    if not client_secret:
        print("❌ No client secret provided. Exiting.")
        return
    
    all_results = {}
    
    try:
        # Authenticate
        token = get_access_token(client_secret)
        
        # Test session
        all_results["session"] = test_session_info(token)
        
        # Test users list
        all_results["users"] = test_users_list(token)
        
        # Get first active user ID for detailed test
        users_data = all_results["users"].get("data", {}).get("users", {}).get("records", [])
        active_users = [u for u in users_data if u.get("isActive")]
        
        if active_users:
            test_user_id = active_users[0].get("id")
            all_results["user_detail"] = test_single_user_with_time_data(token, test_user_id)
        
        # Test clock punch data
        all_results["clock_punches"] = test_clock_punch_data(token)
        
        # Test work cells
        all_results["work_cells"] = test_work_cells(token)
        
        # Test work orders with profitability
        all_results["work_orders"] = test_work_orders_with_profitability(token)
        
        # Test completed work orders
        all_results["completed_wos"] = test_recent_completed_work_orders(token)
        
        # Get a work order number to test detailed query
        wos_data = all_results["work_orders"].get("data", {}).get("workOrders", {}).get("records", [])
        if wos_data:
            test_wo = wos_data[0].get("workOrderNumber")
            all_results["wo_detail"] = test_work_order_time_tracking(token, test_wo)
        
        # Save all results
        with open(OUTPUT_FILE, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\n💾 Full results saved to {OUTPUT_FILE}")
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print("""
Based on the test results, here's what's available for your feedback system:

CLOCK IN/OUT:
  • clockPunch.latestClockPunches - Recent punches across all users
  • user(id).timeClock - Punches for specific user

TIME TRACKING (per operation):
  • user(id).timeTracking - Time entries for a user
  • workOrder(number).timeTracking - Time entries for a WO

PROFITABILITY:
  • workOrder(number).profitability - Full profit breakdown
  • workOrders query with profitability field

WORK CELLS (machines):
  • workCells query - List of machines with scheduled hours

USERS:
  • users query - All employees
  • user(id) query - Single employee details
        """)
        
        print("✅ API test complete!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
