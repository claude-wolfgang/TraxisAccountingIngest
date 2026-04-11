#!/usr/bin/env python3
"""
Comparison Test: Regex Intent Classifier vs Claude Tool-Use Classifier

Runs the same set of queries through both classifiers and shows results
side by side. Tests three categories:
  1. Standard queries - both should handle fine
  2. Edge cases - regex might struggle
  3. Hard queries - regex will fail, Claude should handle
"""

import sys
import os
import time

# Load API key from the mobile app .env if not already set
if not os.environ.get("ANTHROPIC_API_KEY"):
    env_path = os.path.join(
        os.path.dirname(__file__), "..",
        "11. Proshop Mobile App", "proshop-mobile-backend", ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]
                    break

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from intent_classifier import classify_intent as classify_regex
from claude_intent_classifier import classify_intent_claude as classify_claude


# =============================================================================
# Test Cases
# =============================================================================

TEST_CASES = [
    # --------------------------------------------------
    # Category 1: Standard queries (both should work)
    # --------------------------------------------------
    {
        "category": "STANDARD",
        "query": "What's the status of WO 25-0001?",
        "expected_template": "work_order_status",
        "expected_vars": {"woNumber": "25-0001"},
    },
    {
        "category": "STANDARD",
        "query": "Show me all open work orders",
        "expected_template": "list_work_orders_by_status",
        "expected_vars": {"status": "open"},
    },
    {
        "category": "STANDARD",
        "query": "What work orders are due this week?",
        "expected_template": "work_orders_due_this_week",
        "expected_vars": {},
    },
    {
        "category": "STANDARD",
        "query": "What operations are on WO 25-0001?",
        "expected_template": "work_order_operations",
        "expected_vars": {"woNumber": "25-0001"},
    },
    {
        "category": "STANDARD",
        "query": "Are there any late work orders?",
        "expected_template": "late_work_orders",
        "expected_vars": {},
    },
    {
        "category": "STANDARD",
        "query": "How much time has been spent on WO 25-0001?",
        "expected_template": "work_order_time_tracking",
        "expected_vars": {"woNumber": "25-0001"},
    },
    {
        "category": "STANDARD",
        "query": "When is WO 25-0001 due?",
        "expected_template": "work_order_due_date",
        "expected_vars": {"woNumber": "25-0001"},
    },
    {
        "category": "STANDARD",
        "query": "How many open work orders do we have?",
        "expected_template": "open_work_order_count",
        "expected_vars": {},
    },
    {
        "category": "STANDARD",
        "query": "What operations are on part TRA1-TEMP?",
        "expected_template": "part_operations",
        "expected_vars": {"partNumber": ["TRA1-TEMP"]},
    },
    {
        "category": "STANDARD",
        "query": "Show me work order profitability",
        "expected_template": "work_order_profitability",
        "expected_vars": {},
    },

    # --------------------------------------------------
    # Category 2: Edge cases (regex might get wrong)
    # --------------------------------------------------
    {
        "category": "EDGE CASE",
        "query": "25-0001",
        "expected_template": "work_order_status",
        "expected_vars": {"woNumber": "25-0001"},
        "note": "Just a WO number, no other context",
    },
    {
        "category": "EDGE CASE",
        "query": "What's the quantity for WO 25-0001?",
        "expected_template": "work_order_quantity",
        "expected_vars": {"woNumber": "25-0001"},
    },
    {
        "category": "EDGE CASE",
        "query": "show me the largest active order",
        "expected_template": "largest_active_order",
        "expected_vars": {},
    },
    {
        "category": "EDGE CASE",
        "query": "Show me the details for Op 60 on part TRA1-TEMP",
        "expected_template": "part_operation_details",
        "expected_vars": {"partNumber": ["TRA1-TEMP"], "opNumber": "60"},
    },
    {
        "category": "EDGE CASE",
        "query": "where is 26-0003 right now",
        "expected_template": "work_order_current_op",
        "expected_vars": {"woNumber": "26-0003"},
        "note": "Colloquial phrasing for current operation",
    },

    # --------------------------------------------------
    # Category 3: HARD queries (regex WILL fail)
    # --------------------------------------------------
    {
        "category": "HARD",
        "query": "whats the statis of work ordder 25-0001",
        "expected_template": "work_order_status",
        "expected_vars": {"woNumber": "25-0001"},
        "note": "Multiple typos",
    },
    {
        "category": "HARD",
        "query": "pull up the ops list for 25-0001",
        "expected_template": "work_order_operations",
        "expected_vars": {"woNumber": "25-0001"},
        "note": "Slang phrasing",
    },
    {
        "category": "HARD",
        "query": "anything running behind schedule?",
        "expected_template": "late_work_orders",
        "expected_vars": {},
        "note": "No keywords like 'late' or 'overdue'",
    },
    {
        "category": "HARD",
        "query": "how many jobs we got going right now",
        "expected_template": "open_work_order_count",
        "expected_vars": {},
        "note": "'jobs' instead of 'work orders', casual speech",
    },
    {
        "category": "HARD",
        "query": "what's our biggest job",
        "expected_template": "largest_active_order",
        "expected_vars": {},
        "note": "'biggest job' instead of 'largest active order'",
    },
    {
        "category": "HARD",
        "query": "how are we doing on time for 26-0003",
        "expected_template": "work_order_time_tracking",
        "expected_vars": {"woNumber": "26-0003"},
        "note": "Indirect phrasing for time tracking",
    },
    {
        "category": "HARD",
        "query": "is job 25-0001 done yet",
        "expected_template": "work_order_status",
        "expected_vars": {"woNumber": "25-0001"},
        "note": "'job' instead of 'WO', 'done' for status",
    },
    {
        "category": "HARD",
        "query": "when does 26-0005 need to ship",
        "expected_template": "work_order_due_date",
        "expected_vars": {"woNumber": "26-0005"},
        "note": "'need to ship' instead of 'due'",
    },
    {
        "category": "HARD",
        "query": "show me everything we've shipped recently",
        "expected_template": "list_work_orders_by_status",
        "expected_vars": {"status": "shipped"},
        "note": "Implies status filter from context",
    },
    {
        "category": "HARD",
        "query": "what do I need to work on next",
        "expected_template": "work_orders_due_this_week",
        "expected_vars": {},
        "note": "Shop floor question about priorities",
    },
]


# =============================================================================
# Scoring
# =============================================================================

def check_result(intent, expected_template, expected_vars):
    """Check if an intent matches the expected result. Returns (template_ok, vars_ok)."""
    template_ok = intent.template == expected_template

    # For variables, check that key values match
    vars_ok = True
    for key, expected_val in expected_vars.items():
        actual_val = intent.variables.get(key)
        if actual_val != expected_val:
            # Allow string vs list mismatch for partNumber
            if key == "partNumber" and isinstance(expected_val, list):
                if isinstance(actual_val, list) and len(actual_val) > 0:
                    vars_ok = actual_val[0].upper() == expected_val[0].upper()
                elif isinstance(actual_val, str):
                    vars_ok = actual_val.upper() == expected_val[0].upper()
                else:
                    vars_ok = False
            else:
                vars_ok = False

    return template_ok, vars_ok


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 80)
    print("  CLASSIFIER COMPARISON: Regex vs Claude Tool-Use")
    print("=" * 80)

    regex_scores = {"template": 0, "vars": 0, "total": 0}
    claude_scores = {"template": 0, "vars": 0, "total": 0}
    total_tests = len(TEST_CASES)
    claude_times = []

    current_category = None

    for i, test in enumerate(TEST_CASES, 1):
        # Print category header
        if test["category"] != current_category:
            current_category = test["category"]
            print(f"\n{'-' * 80}")
            print(f"  {current_category} QUERIES")
            print(f"{'-' * 80}")

        query = test["query"]
        expected_t = test["expected_template"]
        expected_v = test["expected_vars"]
        note = test.get("note", "")

        print(f"\n[{i}/{total_tests}] \"{query}\"")
        if note:
            print(f"  Note: {note}")
        print(f"  Expected: template={expected_t}, vars={expected_v}")

        # --- Regex classifier ---
        regex_intent = classify_regex(query)
        r_tok, r_vok = check_result(regex_intent, expected_t, expected_v)
        regex_scores["template"] += int(r_tok)
        regex_scores["vars"] += int(r_vok)
        regex_scores["total"] += int(r_tok and r_vok)

        r_status = "PASS" if (r_tok and r_vok) else "FAIL"
        r_detail = ""
        if not r_tok:
            r_detail += f" (got template={regex_intent.template})"
        if not r_vok:
            r_detail += f" (got vars={regex_intent.variables})"

        print(f"  Regex:  {r_status}{r_detail}")

        # --- Claude classifier ---
        try:
            t0 = time.time()
            claude_intent = classify_claude(query)
            elapsed = time.time() - t0
            claude_times.append(elapsed)

            c_tok, c_vok = check_result(claude_intent, expected_t, expected_v)
            claude_scores["template"] += int(c_tok)
            claude_scores["vars"] += int(c_vok)
            claude_scores["total"] += int(c_tok and c_vok)

            c_status = "PASS" if (c_tok and c_vok) else "FAIL"
            c_detail = ""
            if not c_tok:
                c_detail += f" (got template={claude_intent.template})"
            if not c_vok:
                c_detail += f" (got vars={claude_intent.variables})"

            print(f"  Claude: {c_status}{c_detail}  [{elapsed:.2f}s]")

        except Exception as e:
            print(f"  Claude: ERROR - {e}")
            claude_times.append(0)

    # --- Summary ---
    print(f"\n{'=' * 80}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 80}")

    # Count by category
    categories = {}
    for test in TEST_CASES:
        cat = test["category"]
        if cat not in categories:
            categories[cat] = {"count": 0}
        categories[cat]["count"] += 1

    print(f"\n  Total test cases: {total_tests}")
    for cat, info in categories.items():
        print(f"    {cat}: {info['count']}")

    print(f"\n  {'Metric':<25} {'Regex':>10} {'Claude':>10}")
    print(f"  {'-' * 45}")
    print(f"  {'Template correct':<25} {regex_scores['template']:>7}/{total_tests}  {claude_scores['template']:>7}/{total_tests}")
    print(f"  {'Variables correct':<25} {regex_scores['vars']:>7}/{total_tests}  {claude_scores['vars']:>7}/{total_tests}")
    print(f"  {'Both correct (score)':<25} {regex_scores['total']:>7}/{total_tests}  {claude_scores['total']:>7}/{total_tests}")

    regex_pct = (regex_scores['total'] / total_tests) * 100
    claude_pct = (claude_scores['total'] / total_tests) * 100
    print(f"\n  {'Accuracy':<25} {regex_pct:>9.0f}%  {claude_pct:>9.0f}%")

    if claude_times:
        avg_time = sum(claude_times) / len(claude_times)
        print(f"\n  Claude avg response time: {avg_time:.2f}s")
        print(f"  Claude est. cost/query:  ~$0.001 (Haiku)")

    improvement = claude_scores['total'] - regex_scores['total']
    if improvement > 0:
        print(f"\n  Claude correctly handled {improvement} MORE queries than regex.")
    elif improvement == 0:
        print(f"\n  Both classifiers scored the same.")
    else:
        print(f"\n  Regex handled {-improvement} more queries than Claude.")

    print()


if __name__ == "__main__":
    main()
