#!/usr/bin/env python3
"""
ProShop Conversational Interface - Command Line Interface
A natural language interface for querying ProShop ERP.
"""

import sys
import json
from typing import Optional

from proshop_client import ProShopClient, clear_cache, get_cache_stats
from query_templates import execute_template, get_template, list_templates, QUERY_TEMPLATES
from intent_classifier import classify_intent, get_suggestions
from response_formatter import format_response, format_error, format_help


# =============================================================================
# CLI Configuration
# =============================================================================

BANNER = """
============================================================
         ProShop Conversational Interface

  Ask questions in plain English about work orders, parts,
  operations, and more.

  Type 'help' for examples, 'quit' to exit
============================================================
"""

PROMPT = "\nYou: "


# =============================================================================
# Query Processing
# =============================================================================

def process_query(client: ProShopClient, user_input: str, debug: bool = False) -> str:
    """
    Process a natural language query and return the formatted response.

    Args:
        client: Authenticated ProShop client
        user_input: The user's natural language query
        debug: If True, show additional debug info

    Returns:
        Formatted response string
    """
    # Handle special commands
    input_lower = user_input.lower().strip()

    if input_lower in ["help", "?", "h"]:
        return format_help()

    if input_lower.startswith("raw "):
        # Show raw GraphQL for the query
        actual_query = user_input[4:].strip()
        intent = classify_intent(actual_query)
        template = get_template(intent.template)
        if template and template.get("query"):
            return f"Template: {intent.template}\nVariables: {intent.variables}\n\nGraphQL Query:\n{template['query']}"
        return "No query template for this intent."

    if input_lower == "templates":
        templates = list_templates()
        lines = ["Available Query Templates:", ""]
        for t in templates:
            lines.append(f"  {t['name']}: {t['description']}")
            if t.get('example'):
                lines.append(f"    Example: {t['example']}")
        return "\n".join(lines)

    if input_lower in ["cache", "cache stats"]:
        stats = get_cache_stats()
        return f"Cache: {stats['valid']} valid entries, {stats['expired']} expired ({stats['total']} total)"

    if input_lower in ["clear cache", "cache clear", "refresh"]:
        clear_cache()
        return "Cache cleared. Next queries will fetch fresh data."

    # Classify the intent
    intent = classify_intent(user_input)

    if debug:
        print(f"\n[DEBUG] Template: {intent.template}")
        print(f"[DEBUG] Variables: {intent.variables}")
        print(f"[DEBUG] Confidence: {intent.confidence:.2f}")

    # Check if clarification is needed
    if intent.clarification_needed:
        suggestions = get_suggestions(user_input)
        response = [intent.clarification_needed, "", "Try something like:"]
        for s in suggestions:
            response.append(f"  - {s}")
        return "\n".join(response)

    # Handle help specially (no API call needed)
    if intent.template == "help":
        return format_help()

    # Check if this is a slow query and warn user
    template = QUERY_TEMPLATES.get(intent.template, {})
    if template.get("slow_query"):
        print("  [Searching all work orders, this may take a moment...]")

    # Execute the query
    try:
        result = execute_template(client, intent.template, intent.variables)

        if debug:
            print(f"\n[DEBUG] Raw result:\n{json.dumps(result, indent=2, default=str)[:500]}...")

        return format_response(intent.template, result)

    except Exception as e:
        return format_error(e)


# =============================================================================
# Main CLI Loop
# =============================================================================

def main():
    """Main CLI entry point."""
    print(BANNER)

    # Initialize and authenticate client
    print("Connecting to ProShop...")
    client = ProShopClient()

    if not client.authenticate():
        print("\nFailed to connect to ProShop. Please check credentials.")
        print("Ensure PROSHOP_CLIENT_ID and PROSHOP_CLIENT_SECRET are set,")
        print("or update the defaults in proshop_client.py")
        sys.exit(1)

    print("Connected successfully!\n")

    # Check for debug mode
    debug_mode = "--debug" in sys.argv or "-d" in sys.argv

    if debug_mode:
        print("[DEBUG MODE ENABLED]\n")

    # Main loop
    while True:
        try:
            user_input = input(PROMPT).strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q", "bye"]:
                print("\nGoodbye!")
                break

            # Process and display response
            response = process_query(client, user_input, debug=debug_mode)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except EOFError:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            if debug_mode:
                import traceback
                traceback.print_exc()


# =============================================================================
# Single Query Mode
# =============================================================================

def single_query(query: str, debug: bool = False) -> str:
    """
    Execute a single query and return the result.
    Useful for scripting or testing.

    Args:
        query: The natural language query
        debug: If True, print debug info

    Returns:
        Formatted response string
    """
    client = ProShopClient()
    if not client.authenticate():
        return "Failed to authenticate with ProShop"

    return process_query(client, query, debug=debug)


if __name__ == "__main__":
    # Check if a query was passed as argument
    if len(sys.argv) > 1 and sys.argv[1] not in ["--debug", "-d"]:
        # Single query mode
        query = " ".join(arg for arg in sys.argv[1:] if arg not in ["--debug", "-d"])
        debug = "--debug" in sys.argv or "-d" in sys.argv
        print(single_query(query, debug=debug))
    else:
        # Interactive mode
        main()
