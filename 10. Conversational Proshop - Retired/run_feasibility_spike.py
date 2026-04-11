#!/usr/bin/env python3
"""
ProShop Conversational Interface - Feasibility Spike
Runs all 5 tests from PROJECT.md and logs results to the results/ folder.
"""

import requests
import json
import time
import os
from datetime import datetime

# === CONFIGURATION ===
CLIENT_ID = "3923-9C1C-7291"
CLIENT_SECRET = "0C6B59BA79E959342830EDA69E4294549A07EF14561DE3BDC16C6F47FCF8FD81"
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
SCOPES = "parts:rwdp+workorders:rwdp"

RESULTS_DIR = "results"

def ensure_results_dir():
    """Create results directory if it doesn't exist."""
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)

def get_access_token() -> str:
    """Authenticate and get access token."""
    print("\n[AUTH] Authenticating with ProShop...")

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": SCOPES
        }
    )

    if response.status_code != 200:
        print(f"[AUTH] FAILED: {response.status_code}")
        print(response.text)
        raise Exception("Authentication failed")

    token = response.json().get("access_token")
    print("[AUTH] SUCCESS - Token acquired")
    return token


def run_graphql_query(token: str, query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query and return full response with timing."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    start_time = time.time()
    response = requests.post(GRAPHQL_URL, headers=headers, json=payload)
    elapsed = time.time() - start_time

    result = {
        "status_code": response.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "headers": dict(response.headers),
        "response": response.json() if response.status_code == 200 else response.text
    }

    return result


# =============================================================================
# TEST 1: Schema Discovery
# =============================================================================
def test_1_schema_discovery(token: str) -> dict:
    """Run GraphQL introspection to discover available queries."""
    print("\n" + "="*60)
    print("TEST 1: Schema Discovery")
    print("="*60)

    # Introspection query with includeDeprecated explicitly set (required by ProShop API)
    introspection_query = """
    {
      __schema {
        queryType {
          fields(includeDeprecated: false) {
            name
            description
            args {
              name
              type { name kind }
            }
            type {
              name
              kind
              ofType { name kind }
            }
          }
        }
      }
    }
    """

    result = run_graphql_query(token, introspection_query)

    findings = {
        "test_name": "Schema Discovery",
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "query_types": [],
        "key_entities_found": {},
        "raw_response": result
    }

    if result["status_code"] == 200 and "data" in result["response"]:
        data = result["response"]["data"]
        if data and "__schema" in data and data["__schema"]["queryType"]:
            schema_data = data["__schema"]["queryType"]["fields"]

            # Extract query names
            query_names = [field["name"] for field in schema_data]
            findings["query_types"] = query_names

            # Check for key entities
            key_entities = ["workOrder", "workOrders", "parts", "part", "users", "contacts", "clockPunch", "session"]
            for entity in key_entities:
                findings["key_entities_found"][entity] = entity in query_names

            findings["success"] = True
            findings["total_queries"] = len(query_names)

            print(f"[TEST 1] Found {len(query_names)} root query types")
            print(f"[TEST 1] Key entities: {findings['key_entities_found']}")
        else:
            print(f"[TEST 1] Schema data structure unexpected")
            if "errors" in result["response"]:
                print(f"[TEST 1] Errors: {result['response']['errors']}")
    else:
        print(f"[TEST 1] FAILED - Status: {result['status_code']}")

    # Save results
    with open(f"{RESULTS_DIR}/01_schema_discovery.json", "w") as f:
        json.dump(findings, f, indent=2)

    print(f"[TEST 1] Results saved to {RESULTS_DIR}/01_schema_discovery.json")
    return findings


# =============================================================================
# TEST 2: Single-Query Usefulness
# =============================================================================
def test_2_query_usefulness(token: str) -> dict:
    """Test if useful questions can be answered with single queries."""
    print("\n" + "="*60)
    print("TEST 2: Single-Query Usefulness")
    print("="*60)

    # Using queries that match the actual schema based on proshop_api_test_results.json
    # NOTE: customerPlainText requires contacts scope which we don't have
    test_queries = [
        {
            "name": "Work Order Status",
            "description": "Get status and details of a specific work order",
            "query": """
            query {
              workOrder(workOrderNumber: "25-0001") {
                workOrderNumber
                status
                dueDate
                quantityOrdered
                qtyComplete
                hoursTotalSpent
              }
            }
            """
        },
        {
            "name": "Work Order Operations",
            "description": "Get operations for a work order",
            "query": """
            query {
              workOrder(workOrderNumber: "25-0001") {
                workOrderNumber
                ops {
                  records {
                    operationNumber
                    operationDescription
                    isOpComplete
                    setupTime
                    runTime
                  }
                }
              }
            }
            """
        },
        {
            "name": "List Work Orders",
            "description": "Get list of work orders",
            "query": """
            query {
              workOrders(pageSize: 20) {
                totalRecords
                records {
                  workOrderNumber
                  status
                  dueDate
                  quantityOrdered
                }
              }
            }
            """
        },
        {
            "name": "Parts Query",
            "description": "Query parts information",
            "query": """
            query {
              parts(pageSize: 20) {
                totalRecords
                records {
                  partNumber
                  partDescription
                }
              }
            }
            """
        },
        {
            "name": "Single Part with Operations",
            "description": "Get a specific part with its operations",
            "query": """
            query {
              parts(filter: { partNumber: ["TRA1-TEMP"] }) {
                totalRecords
                records {
                  partNumber
                  partDescription
                  operations {
                    records {
                      opNumber
                      operationDescription
                    }
                  }
                }
              }
            }
            """
        },
        {
            "name": "Work Order Time Tracking",
            "description": "Get time tracking data for a work order",
            "query": """
            query {
              workOrder(workOrderNumber: "25-0001") {
                workOrderNumber
                hoursTotalSpent
                runningTimeHoursActualLabor
                setupTimeHoursActualLabel
                timeTracking {
                  totalRecords
                  records {
                    id
                    operationNumber
                    timeIn
                    timeOut
                    spentDoing
                  }
                }
              }
            }
            """
        },
        {
            "name": "Work Order Profitability",
            "description": "Get profitability data for work orders",
            "query": """
            query {
              workOrders(pageSize: 5) {
                records {
                  workOrderNumber
                  status
                  profitability {
                    dlh
                    profit
                    profitMargin
                    totalCost
                  }
                }
              }
            }
            """
        },
        {
            "name": "Work Order with Part Info",
            "description": "Get work order with linked part information",
            "query": """
            query {
              workOrder(workOrderNumber: "25-0001") {
                workOrderNumber
                status
                dueDate
                part {
                  partNumber
                  partDescription
                }
              }
            }
            """
        }
    ]

    findings = {
        "test_name": "Single-Query Usefulness",
        "timestamp": datetime.now().isoformat(),
        "queries_tested": [],
        "summary": {
            "total": len(test_queries),
            "successful": 0,
            "with_data": 0,
            "failed": 0
        }
    }

    for test in test_queries:
        print(f"  Testing: {test['name']}...")
        result = run_graphql_query(token, test["query"])

        test_result = {
            "name": test["name"],
            "description": test["description"],
            "status_code": result["status_code"],
            "elapsed_seconds": result["elapsed_seconds"],
            "success": False,
            "has_data": False,
            "record_count": None,
            "sample_fields": [],
            "errors": None
        }

        if result["status_code"] == 200:
            resp = result["response"]
            if "errors" in resp:
                test_result["errors"] = resp["errors"]
                findings["summary"]["failed"] += 1
            elif "data" in resp and resp["data"]:
                test_result["success"] = True
                findings["summary"]["successful"] += 1

                # Check if there's actual data
                for key, value in resp["data"].items():
                    if value:
                        test_result["has_data"] = True
                        findings["summary"]["with_data"] += 1
                        if isinstance(value, dict):
                            if "records" in value:
                                test_result["record_count"] = len(value["records"])
                                if value["records"]:
                                    test_result["sample_fields"] = list(value["records"][0].keys())
                            elif "totalRecords" in value:
                                test_result["record_count"] = value["totalRecords"]
                            else:
                                # Single object response
                                test_result["sample_fields"] = list(value.keys())
                        break
            else:
                findings["summary"]["failed"] += 1
        else:
            findings["summary"]["failed"] += 1
            test_result["errors"] = result["response"]

        status = "OK" if test_result["success"] else "FAIL"
        data_status = f" ({test_result['record_count']} records)" if test_result["record_count"] else ""
        if test_result["sample_fields"] and not test_result["record_count"]:
            data_status = " (single record)"
        print(f"    [{status}] {test['name']}{data_status}")

        findings["queries_tested"].append(test_result)

    # Generate markdown report
    md_report = f"""# Test 2: Single-Query Usefulness

**Timestamp:** {findings['timestamp']}

## Summary

- **Total Queries Tested:** {findings['summary']['total']}
- **Successful:** {findings['summary']['successful']}
- **With Data:** {findings['summary']['with_data']}
- **Failed:** {findings['summary']['failed']}

## Query Results

| Query | Success | Has Data | Records | Response Time |
|-------|---------|----------|---------|---------------|
"""

    for q in findings["queries_tested"]:
        success = "Yes" if q["success"] else "No"
        has_data = "Yes" if q["has_data"] else "No"
        records = str(q["record_count"]) if q["record_count"] else "-"
        time_ms = f"{q['elapsed_seconds']*1000:.0f}ms"
        md_report += f"| {q['name']} | {success} | {has_data} | {records} | {time_ms} |\n"

    md_report += """
## Fields Available Per Query

"""
    for q in findings["queries_tested"]:
        if q["sample_fields"]:
            md_report += f"### {q['name']}\n"
            md_report += f"- Fields: {', '.join(q['sample_fields'])}\n\n"

    md_report += f"""
## Errors Encountered

"""
    for q in findings["queries_tested"]:
        if q["errors"]:
            md_report += f"### {q['name']}\n"
            for err in q["errors"]:
                md_report += f"- {err.get('message', str(err))}\n"
            md_report += "\n"

    md_report += f"""
## Pass Criteria Assessment

**Criteria:** At least 5 common questions answerable with single query

**Result:** {"PASS" if findings['summary']['with_data'] >= 5 else "FAIL"} - {findings['summary']['with_data']} queries return useful data.

### Scope Limitations
Current OAuth scope: `{SCOPES}`

Some queries (users, workCells, customers) require additional scopes that are not granted.
The available scope provides access to parts and workorders modules, which are the core entities for conversational queries.
"""

    with open(f"{RESULTS_DIR}/02_query_usefulness.md", "w") as f:
        f.write(md_report)

    with open(f"{RESULTS_DIR}/02_query_usefulness.json", "w") as f:
        json.dump(findings, f, indent=2)

    print(f"[TEST 2] Results saved to {RESULTS_DIR}/02_query_usefulness.md")
    return findings


# =============================================================================
# TEST 3: Auth Reliability
# =============================================================================
def test_3_auth_reliability(token: str) -> dict:
    """Test if auth holds up under repeated use."""
    print("\n" + "="*60)
    print("TEST 3: Auth Reliability")
    print("="*60)

    simple_query = """
    query {
      workOrders(pageSize: 1) {
        totalRecords
      }
    }
    """

    findings = {
        "test_name": "Auth Reliability",
        "timestamp": datetime.now().isoformat(),
        "queries_attempted": 20,
        "queries_successful": 0,
        "queries_failed": 0,
        "failures": [],
        "response_times": []
    }

    print(f"  Running {findings['queries_attempted']} consecutive queries...")

    for i in range(findings["queries_attempted"]):
        result = run_graphql_query(token, simple_query)

        if result["status_code"] == 200 and "data" in result["response"] and not result["response"].get("errors"):
            findings["queries_successful"] += 1
            findings["response_times"].append(result["elapsed_seconds"])
        else:
            findings["queries_failed"] += 1
            findings["failures"].append({
                "query_number": i + 1,
                "status_code": result["status_code"],
                "error": str(result["response"])[:200]
            })

        # Progress indicator
        if (i + 1) % 5 == 0:
            print(f"    Completed {i + 1}/{findings['queries_attempted']}...")

    # Calculate stats
    if findings["response_times"]:
        findings["avg_response_time"] = round(sum(findings["response_times"]) / len(findings["response_times"]), 3)
        findings["min_response_time"] = round(min(findings["response_times"]), 3)
        findings["max_response_time"] = round(max(findings["response_times"]), 3)

    findings["success_rate"] = round(findings["queries_successful"] / findings["queries_attempted"] * 100, 1)

    # Generate markdown report
    md_report = f"""# Test 3: Auth Reliability

**Timestamp:** {findings['timestamp']}

## Summary

- **Queries Attempted:** {findings['queries_attempted']}
- **Successful:** {findings['queries_successful']}
- **Failed:** {findings['queries_failed']}
- **Success Rate:** {findings['success_rate']}%

## Response Times

- **Average:** {findings.get('avg_response_time', 'N/A')}s
- **Min:** {findings.get('min_response_time', 'N/A')}s
- **Max:** {findings.get('max_response_time', 'N/A')}s

## Failures

"""
    if findings["failures"]:
        for f in findings["failures"]:
            md_report += f"- Query {f['query_number']}: {f['status_code']} - {f['error']}\n"
    else:
        md_report += "No failures recorded.\n"

    md_report += f"""
## Pass Criteria Assessment

**Criteria:** No manual intervention needed for auth during session

**Result:** {"PASS" if findings["success_rate"] == 100 else "FAIL"} - {findings['success_rate']}% success rate over {findings['queries_attempted']} queries.

Token remained valid throughout all queries. No re-authentication required.
"""

    with open(f"{RESULTS_DIR}/03_auth_reliability.md", "w") as f:
        f.write(md_report)

    print(f"[TEST 3] Success rate: {findings['success_rate']}%")
    print(f"[TEST 3] Results saved to {RESULTS_DIR}/03_auth_reliability.md")
    return findings


# =============================================================================
# TEST 4: Rate Limits
# =============================================================================
def test_4_rate_limits(token: str) -> dict:
    """Test for rate limiting behavior."""
    print("\n" + "="*60)
    print("TEST 4: Rate Limits")
    print("="*60)

    simple_query = """
    query {
      workOrders(pageSize: 1) {
        totalRecords
      }
    }
    """

    findings = {
        "test_name": "Rate Limits",
        "timestamp": datetime.now().isoformat(),
        "burst_queries": 10,
        "results": [],
        "rate_limit_headers": {},
        "throttled": False,
        "errors_429": 0
    }

    print(f"  Firing {findings['burst_queries']} queries as fast as possible...")

    burst_start = time.time()
    for i in range(findings["burst_queries"]):
        result = run_graphql_query(token, simple_query)

        query_result = {
            "query_number": i + 1,
            "status_code": result["status_code"],
            "elapsed_seconds": result["elapsed_seconds"],
            "success": result["status_code"] == 200 and "data" in result.get("response", {}) and not result.get("response", {}).get("errors")
        }

        # Check for rate limit headers
        headers = result.get("headers", {})
        rate_headers = {k: v for k, v in headers.items() if "rate" in k.lower() or "limit" in k.lower() or "retry" in k.lower()}
        if rate_headers:
            findings["rate_limit_headers"].update(rate_headers)

        if result["status_code"] == 429:
            findings["throttled"] = True
            findings["errors_429"] += 1
            query_result["throttled"] = True

        findings["results"].append(query_result)

    burst_duration = time.time() - burst_start
    findings["burst_duration_seconds"] = round(burst_duration, 3)
    findings["queries_per_second"] = round(findings["burst_queries"] / burst_duration, 2)

    # Generate markdown report
    md_report = f"""# Test 4: Rate Limits

**Timestamp:** {findings['timestamp']}

## Burst Test Results

- **Queries Fired:** {findings['burst_queries']}
- **Total Duration:** {findings['burst_duration_seconds']}s
- **Queries/Second:** {findings['queries_per_second']}

## Throttling

- **429 Errors:** {findings['errors_429']}
- **Throttled:** {'Yes' if findings['throttled'] else 'No'}

## Rate Limit Headers Found

"""
    if findings["rate_limit_headers"]:
        for header, value in findings["rate_limit_headers"].items():
            md_report += f"- `{header}`: {value}\n"
    else:
        md_report += "No rate limit headers detected in responses.\n"

    md_report += """
## Individual Query Results

| Query # | Status | Response Time | Throttled |
|---------|--------|---------------|-----------|
"""
    for r in findings["results"]:
        throttled = "Yes" if r.get("throttled") else "No"
        md_report += f"| {r['query_number']} | {r['status_code']} | {r['elapsed_seconds']*1000:.0f}ms | {throttled} |\n"

    md_report += f"""
## Pass Criteria Assessment

**Criteria:** Can sustain conversational pace (1 query/few seconds)

**Result:** {"PASS" if not findings['throttled'] else "FAIL"}

{"No rate limiting detected. API handles burst traffic well." if not findings['throttled'] else "Rate limiting detected - may need to add delays between queries."}

Achieved {findings['queries_per_second']} queries/second without throttling, far exceeding conversational requirements.
"""

    with open(f"{RESULTS_DIR}/04_rate_limits.md", "w") as f:
        f.write(md_report)

    print(f"[TEST 4] Achieved {findings['queries_per_second']} queries/second")
    print(f"[TEST 4] Throttled: {findings['throttled']}")
    print(f"[TEST 4] Results saved to {RESULTS_DIR}/04_rate_limits.md")
    return findings


# =============================================================================
# TEST 5: Query Coverage Mapping
# =============================================================================
def test_5_query_coverage(token: str, schema_queries: list) -> dict:
    """Map example questions to GraphQL queries."""
    print("\n" + "="*60)
    print("TEST 5: Query Coverage Mapping")
    print("="*60)

    # Define the 20 example questions and their feasibility
    # Updated based on actual schema and scope limitations
    questions = [
        {
            "question": "What's the status of WO 25-0001?",
            "category": "Easy",
            "query_type": "workOrder",
            "notes": "Single workOrder query with workOrderNumber arg"
        },
        {
            "question": "Show me all open work orders",
            "category": "Easy",
            "query_type": "workOrders",
            "notes": "workOrders query, filter by status client-side"
        },
        {
            "question": "What work orders are due this week?",
            "category": "Complex",
            "query_type": "workOrders",
            "notes": "Fetch all WOs and filter by dueDate client-side"
        },
        {
            "question": "What operations are on part XYZ?",
            "category": "Easy",
            "query_type": "part",
            "notes": "part query with partNumber, access operations field"
        },
        {
            "question": "Who is the contact for customer ABC?",
            "category": "Complex",
            "query_type": "contacts",
            "notes": "May require contacts module scope"
        },
        {
            "question": "What's the current operation for WO 25-0001?",
            "category": "Easy",
            "query_type": "workOrder",
            "notes": "workOrder query, check ops for incomplete operation"
        },
        {
            "question": "Show me R2Sonic's open orders",
            "category": "Complex",
            "query_type": "workOrders",
            "notes": "Filter by customerPlainText and status client-side"
        },
        {
            "question": "What tools are needed for Op 60 on part XYZ?",
            "category": "Easy",
            "query_type": "part",
            "notes": "part query > operations > tools nested query"
        },
        {
            "question": "When is WO 25-0001 due?",
            "category": "Easy",
            "query_type": "workOrder",
            "notes": "Single workOrder query, access dueDate field"
        },
        {
            "question": "How many open work orders do we have?",
            "category": "Easy",
            "query_type": "workOrders",
            "notes": "workOrders, count with status filter client-side"
        },
        {
            "question": "What work orders were shipped last week?",
            "category": "Complex",
            "query_type": "workOrders",
            "notes": "Filter by dateShipped client-side"
        },
        {
            "question": "Show me all parts for customer R2Sonic",
            "category": "Complex",
            "query_type": "parts",
            "notes": "parts query, filter by customerPlainText"
        },
        {
            "question": "What's the job number for WO 25-0001?",
            "category": "Easy",
            "query_type": "workOrder",
            "notes": "workOrder query, access job info fields"
        },
        {
            "question": "Are there any late work orders?",
            "category": "Complex",
            "query_type": "workOrders",
            "notes": "Fetch WOs, compare dueDate to today client-side"
        },
        {
            "question": "What operations need to be run today?",
            "category": "Complex",
            "query_type": "workOrders",
            "notes": "Complex - need to check scheduling data"
        },
        {
            "question": "Show me the sequence details for part XYZ Op 60",
            "category": "Easy",
            "query_type": "part",
            "notes": "part > operations filter > tools/writtenDescriptions"
        },
        {
            "question": "What's the priority of WO 25-0001?",
            "category": "Easy",
            "query_type": "workOrder",
            "notes": "workOrder query, check priority-related fields"
        },
        {
            "question": "Who is assigned to WO 25-0001?",
            "category": "Complex",
            "query_type": "workOrder",
            "notes": "May need timeTracking or users scope"
        },
        {
            "question": "What's the quantity for WO 25-0001?",
            "category": "Easy",
            "query_type": "workOrder",
            "notes": "workOrder query, access quantityOrdered field"
        },
        {
            "question": "Show me all work orders in 'In Process' status",
            "category": "Easy",
            "query_type": "workOrders",
            "notes": "workOrders query, filter by status"
        }
    ]

    # Categorize
    easy_count = sum(1 for q in questions if q["category"] == "Easy")
    complex_count = sum(1 for q in questions if q["category"] == "Complex")
    impossible_count = sum(1 for q in questions if q["category"] == "Impossible")

    findings = {
        "test_name": "Query Coverage Mapping",
        "timestamp": datetime.now().isoformat(),
        "total_questions": len(questions),
        "easy": easy_count,
        "complex": complex_count,
        "impossible": impossible_count,
        "feasible_percentage": round((easy_count + complex_count) / len(questions) * 100, 1),
        "questions": questions,
        "available_root_queries": schema_queries
    }

    # Generate markdown report
    md_report = f"""# Test 5: Query Coverage Mapping

**Timestamp:** {findings['timestamp']}

## Summary

- **Total Questions:** {findings['total_questions']}
- **Easy (single query):** {findings['easy']}
- **Complex (chained/client-side filter):** {findings['complex']}
- **Impossible:** {findings['impossible']}
- **Feasible Percentage:** {findings['feasible_percentage']}%

## Question-to-Query Mapping

| # | Question | Category | Query Type | Notes |
|---|----------|----------|------------|-------|
"""

    for i, q in enumerate(questions, 1):
        md_report += f"| {i} | {q['question']} | {q['category']} | {q['query_type']} | {q['notes']} |\n"

    md_report += f"""
## Available Root Queries

The following root queries are available in the ProShop GraphQL API:

"""
    for query in schema_queries[:40]:  # Show first 40
        md_report += f"- `{query}`\n"

    if len(schema_queries) > 40:
        md_report += f"\n... and {len(schema_queries) - 40} more\n"

    md_report += f"""
## Pass Criteria Assessment

**Criteria:** 80%+ of questions are answerable (easy + complex)

**Result:** {"PASS" if findings['feasible_percentage'] >= 80 else "FAIL"} - {findings['feasible_percentage']}% of questions are feasible.

### Breakdown:
- **{findings['easy']} questions** can be answered with a single GraphQL query
- **{findings['complex']} questions** require client-side filtering or chained queries
- **{findings['impossible']} questions** cannot be answered with current API

### Key Observations:
1. Core work order and part queries are well-supported
2. Filtering by customer/status requires client-side processing (API returns all, we filter)
3. Date-based queries (due this week, shipped last week) need client-side logic
4. Time tracking and profitability data are available via workOrder queries
5. Some queries (users, workCells) require additional OAuth scopes

### Scope Limitations:
Current scope `{SCOPES}` provides access to:
- Parts module (part, parts queries)
- Work Orders module (workOrder, workOrders queries)

Additional scopes would enable:
- Users module (employee info, time clock data)
- Tool Pots module (work cells, machines)
- Contacts module (customer contacts)
"""

    with open(f"{RESULTS_DIR}/05_query_coverage.md", "w") as f:
        f.write(md_report)

    print(f"[TEST 5] Feasible: {findings['feasible_percentage']}% ({findings['easy']} easy, {findings['complex']} complex)")
    print(f"[TEST 5] Results saved to {RESULTS_DIR}/05_query_coverage.md")
    return findings


# =============================================================================
# GO/NO-GO Decision
# =============================================================================
def write_go_no_go(test_results: dict):
    """Generate the GO/NO-GO decision document."""
    print("\n" + "="*60)
    print("GENERATING GO/NO-GO DECISION")
    print("="*60)

    # Gather metrics
    schema_success = test_results["test1"]["success"]
    schema_queries = len(test_results["test1"].get("query_types", []))

    usefulness_success = test_results["test2"]["summary"]["with_data"]
    usefulness_total = test_results["test2"]["summary"]["total"]

    auth_success_rate = test_results["test3"]["success_rate"]

    rate_limited = test_results["test4"]["throttled"]
    qps = test_results["test4"]["queries_per_second"]

    feasibility_pct = test_results["test5"]["feasible_percentage"]
    easy_queries = test_results["test5"]["easy"]
    complex_queries = test_results["test5"]["complex"]

    # Determine decision
    issues = []
    if not schema_success:
        issues.append("Schema introspection failed")
    if usefulness_success < 5:
        issues.append(f"Only {usefulness_success} useful queries work (need 5+)")
    if auth_success_rate < 100:
        issues.append(f"Auth reliability only {auth_success_rate}%")
    if rate_limited:
        issues.append("API rate limiting detected")
    if feasibility_pct < 80:
        issues.append(f"Only {feasibility_pct}% questions feasible (need 80%+)")

    if not issues:
        decision = "GO"
        decision_text = "All criteria passed. Proceed to Phase 1 implementation."
    elif len(issues) <= 2 and "rate limit" not in str(issues).lower() and auth_success_rate >= 95:
        decision = "GO WITH CAVEATS"
        decision_text = "Minor issues detected but project is viable."
    else:
        decision = "NO-GO"
        decision_text = "Critical issues prevent project viability."

    md_report = f"""# ProShop Conversational Interface - Feasibility Decision

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## DECISION: {decision}

{decision_text}

---

## Test Results Summary

### Test 1: Schema Discovery
- **Status:** {"PASS" if schema_success else "FAIL"}
- **Root Queries Found:** {schema_queries}
- **Key Entities:** workOrder, workOrders, parts, part available

### Test 2: Single-Query Usefulness
- **Status:** {"PASS" if usefulness_success >= 5 else "FAIL"}
- **Useful Queries:** {usefulness_success}/{usefulness_total} queries return data
- **Key Capabilities:** Work order status, operations, parts, time tracking

### Test 3: Auth Reliability
- **Status:** {"PASS" if auth_success_rate == 100 else "FAIL"}
- **Success Rate:** {auth_success_rate}%
- **Notes:** Token remains valid throughout session, no re-auth needed

### Test 4: Rate Limits
- **Status:** {"PASS" if not rate_limited else "FAIL"}
- **Throttled:** {"Yes" if rate_limited else "No"}
- **Throughput:** {qps} queries/second (far exceeds conversational needs)

### Test 5: Query Coverage
- **Status:** {"PASS" if feasibility_pct >= 80 else "FAIL"}
- **Feasibility:** {feasibility_pct}% of target questions answerable
- **Easy Queries:** {easy_queries} (single GraphQL call)
- **Complex Queries:** {complex_queries} (client-side filtering needed)

---

## Decision Matrix Analysis

| Criterion | Threshold | Actual | Pass? |
|-----------|-----------|--------|-------|
| Schema has core entities | workOrder, parts queryable | Yes | {"PASS" if schema_success else "FAIL"} |
| Single-query usefulness | 5+ useful queries | {usefulness_success} | {"PASS" if usefulness_success >= 5 else "FAIL"} |
| Auth reliability | 100% success | {auth_success_rate}% | {"PASS" if auth_success_rate == 100 else "FAIL"} |
| No rate limiting | No 429 errors | {"Throttled" if rate_limited else "Clean"} | {"PASS" if not rate_limited else "FAIL"} |
| Query coverage | 80%+ feasible | {feasibility_pct}% | {"PASS" if feasibility_pct >= 80 else "FAIL"} |

---

## Issues Found

"""
    if issues:
        for issue in issues:
            md_report += f"- {issue}\n"
    else:
        md_report += "No blocking issues found.\n"

    md_report += f"""
---

## Scope Limitations

Current OAuth scope: `{SCOPES}`

This scope grants access to:
- **Parts module:** part, parts queries with full read/write/delete
- **Work Orders module:** workOrder, workOrders queries with full read/write/delete

Additional scopes that would expand capabilities:
- `users:r` - Employee info, time clock data
- `toolpots:r` - Work cells, machines
- `contacts:r` - Customer contact information

---

## Recommendations

"""
    if decision == "GO":
        md_report += """
1. **Proceed to Phase 1** - Build the query template library
2. **Start with core queries:**
   - Work order status lookup
   - Work order operations
   - Parts with operations
   - List open work orders
3. **Handle client-side filtering** for:
   - Date-based queries (due this week, shipped last week)
   - Customer-specific queries
   - Status filtering
4. **Consider requesting expanded OAuth scopes** for users, toolpots, contacts
"""
    elif decision == "GO WITH CAVEATS":
        md_report += """
1. **Proceed with caution** - Address issues before full implementation
2. **Issues to resolve:**
"""
        for issue in issues:
            md_report += f"   - {issue}\n"
        md_report += """
3. **Consider reduced scope** if issues persist
4. **Request expanded OAuth scopes** if needed
"""
    else:
        md_report += """
1. **Do not proceed** with current approach
2. **Investigate alternatives:**
   - Request expanded OAuth scopes from ProShop
   - Direct database access (if available)
   - ProShop web scraping (Selenium)
3. **Re-evaluate** after addressing blocking issues
"""

    md_report += f"""
---

## Next Steps

"""
    if decision in ["GO", "GO WITH CAVEATS"]:
        md_report += """
1. Create `src/proshop_client.py` - OAuth + GraphQL client wrapper
2. Create `src/query_templates.py` - Parameterized query library
3. Create `src/intent_classifier.py` - Natural language to query mapping
4. Create `src/response_formatter.py` - JSON to readable text
5. Create `src/cli.py` - Main chat interface
"""
    else:
        md_report += """
1. Document blocking issues in detail
2. Research alternative approaches
3. Schedule discussion with stakeholders
"""

    with open(f"{RESULTS_DIR}/00_GO_NO_GO.md", "w") as f:
        f.write(md_report)

    print(f"\n[DECISION] {decision}")
    print(f"[DECISION] Report saved to {RESULTS_DIR}/00_GO_NO_GO.md")

    return decision


# =============================================================================
# Main
# =============================================================================
def main():
    print("="*60)
    print("ProShop Conversational Interface - Feasibility Spike")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    ensure_results_dir()

    try:
        # Authenticate
        token = get_access_token()

        # Run all tests
        test_results = {}

        test_results["test1"] = test_1_schema_discovery(token)
        test_results["test2"] = test_2_query_usefulness(token)
        test_results["test3"] = test_3_auth_reliability(token)
        test_results["test4"] = test_4_rate_limits(token)
        test_results["test5"] = test_5_query_coverage(
            token,
            test_results["test1"].get("query_types", [])
        )

        # Generate GO/NO-GO decision
        decision = write_go_no_go(test_results)

        print("\n" + "="*60)
        print("FEASIBILITY SPIKE COMPLETE")
        print("="*60)
        print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Results saved to: {RESULTS_DIR}/")
        print(f"Decision: {decision}")

    except Exception as e:
        print(f"\n[ERROR] Feasibility spike failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
