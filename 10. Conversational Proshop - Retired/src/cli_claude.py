#!/usr/bin/env python3
"""
ProShop Conversational Interface - Claude-Powered CLI
Replaces regex intent classification with Claude tool-use,
adds conversation memory, and produces natural language responses.
"""

import sys
import os
import json
import time
from typing import Optional

# Fix Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

# Load API key from the mobile app .env if not already set
if not os.environ.get("ANTHROPIC_API_KEY"):
    env_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "11. Proshop Mobile App", "proshop-mobile-backend", ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]
                    break

from proshop_client import ProShopClient, clear_cache, get_cache_stats
from query_templates import execute_template, get_template, list_templates, QUERY_TEMPLATES
from claude_intent_classifier import classify_intent_claude
from claude_response_formatter import format_response_claude, format_error_claude
from conversation_manager import ConversationManager


# =============================================================================
# CLI Configuration
# =============================================================================

BANNER = """
============================================================
         ProShop Conversational Interface
                  (Claude-Powered)

  Ask questions in plain English about work orders, parts,
  operations, and more. I understand follow-up questions!

  Type 'help' for examples, 'quit' to exit
============================================================
"""

PROMPT = "\nYou: "


# =============================================================================
# Query Processing
# =============================================================================

def process_query(
    client: ProShopClient,
    user_input: str,
    conversation: ConversationManager,
    debug: bool = False,
) -> str:
    """
    Process a natural language query using Claude for intent classification
    and response formatting, with conversation memory.

    Args:
        client: Authenticated ProShop client
        user_input: The user's natural language query
        conversation: Conversation history manager
        debug: If True, show additional debug info

    Returns:
        Formatted response string
    """
    # Handle special commands (no API call needed)
    input_lower = user_input.lower().strip()

    if input_lower in ["help", "?", "h"]:
        from claude_response_formatter import _format_help
        return _format_help()

    if input_lower.startswith("raw "):
        actual_query = user_input[4:].strip()
        intent = classify_intent_claude(
            actual_query,
            conversation_history=conversation.get_history_for_classifier(),
        )
        template = get_template(intent.template)
        if template and template.get("query"):
            return (
                f"Template: {intent.template}\n"
                f"Variables: {intent.variables}\n\n"
                f"GraphQL Query:\n{template['query']}"
            )
        return "No query template for this intent."

    if input_lower == "templates":
        templates = list_templates()
        lines = ["Available Query Templates:", ""]
        for t in templates:
            lines.append(f"  {t['name']}: {t['description']}")
            if t.get("example"):
                lines.append(f"    Example: {t['example']}")
        return "\n".join(lines)

    if input_lower in ["cache", "cache stats"]:
        stats = get_cache_stats()
        return f"Cache: {stats['valid']} valid entries, {stats['expired']} expired ({stats['total']} total)"

    if input_lower in ["clear cache", "cache clear", "refresh"]:
        clear_cache()
        return "Cache cleared. Next queries will fetch fresh data."

    if input_lower in ["clear", "new", "reset"]:
        conversation.clear()
        return "Conversation cleared. Starting fresh."

    # Step 1: Classify intent using Claude (with conversation context)
    t0 = time.time()
    intent = classify_intent_claude(
        user_input,
        conversation_history=conversation.get_history_for_classifier(),
    )
    classify_time = time.time() - t0

    if debug:
        print(f"\n[DEBUG] Template: {intent.template}")
        print(f"[DEBUG] Variables: {intent.variables}")
        print(f"[DEBUG] Confidence: {intent.confidence:.2f}")
        print(f"[DEBUG] Classification time: {classify_time:.2f}s")

    # Check if clarification is needed
    if intent.clarification_needed:
        return intent.clarification_needed

    # Handle help (no API call needed)
    if intent.template == "help":
        from claude_response_formatter import _format_help
        return _format_help()

    # Warn about slow queries
    template = QUERY_TEMPLATES.get(intent.template, {})
    if template.get("slow_query"):
        print("  [Searching all work orders, this may take a moment...]")

    # Step 2: Execute the ProShop query
    try:
        t0 = time.time()
        result = execute_template(client, intent.template, intent.variables)
        query_time = time.time() - t0

        if debug:
            raw_str = json.dumps(result, indent=2, default=str)
            print(f"\n[DEBUG] Query time: {query_time:.2f}s")
            print(f"[DEBUG] Raw result:\n{raw_str[:500]}...")

        # Step 3: Format response using Claude (with conversation context)
        t0 = time.time()
        response = format_response_claude(
            template_name=intent.template,
            data=result,
            user_query=user_input,
            conversation_context=conversation.get_history_for_classifier(),
        )
        format_time = time.time() - t0

        if debug:
            print(f"[DEBUG] Format time: {format_time:.2f}s")
            print(f"[DEBUG] Total time: {classify_time + query_time + format_time:.2f}s")

        # Step 4: Record in conversation history
        conversation.add_user_message(user_input)
        conversation.add_assistant_message(response)

        return response

    except Exception as e:
        if debug:
            import traceback
            traceback.print_exc()
        return format_error_claude(e)


# =============================================================================
# Main CLI Loop
# =============================================================================

def main():
    """Main CLI entry point."""
    print(BANNER)

    # Initialize ProShop client
    print("Connecting to ProShop...")
    client = ProShopClient()

    if not client.authenticate():
        print("\nFailed to connect to ProShop. Please check credentials.")
        sys.exit(1)

    print("Connected!")

    # Check for Anthropic API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nWarning: ANTHROPIC_API_KEY not set. Claude features will not work.")
        print("Set it with: set ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    print("Claude AI ready.\n")

    # Initialize conversation manager
    conversation = ConversationManager(max_turns=20)

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
            response = process_query(client, user_input, conversation, debug=debug_mode)
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
    """Execute a single query. Useful for scripting or testing."""
    client = ProShopClient()
    if not client.authenticate():
        return "Failed to authenticate with ProShop"

    conversation = ConversationManager()
    return process_query(client, query, conversation, debug=debug)


if __name__ == "__main__":
    # Check if a query was passed as argument
    args = [a for a in sys.argv[1:] if a not in ["--debug", "-d"]]
    debug = "--debug" in sys.argv or "-d" in sys.argv

    if args:
        # Single query mode
        query = " ".join(args)
        print(single_query(query, debug=debug))
    else:
        # Interactive mode
        main()
