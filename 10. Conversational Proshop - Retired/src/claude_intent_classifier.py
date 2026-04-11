"""
Claude API Tool-Use Intent Classifier for ProShop Conversational Interface.
Replaces regex-based pattern matching with Claude's natural language understanding.

Uses Claude's tool_use feature: we define each query type as a "tool" and let
Claude pick the right one based on the user's natural language input.
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import anthropic

# Reuse the same Intent dataclass for drop-in compatibility
from intent_classifier import Intent


# =============================================================================
# Configuration
# =============================================================================

# Use Haiku for speed and cost (~$0.001 per classification)
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a query router for a manufacturing shop's ERP system (ProShop).
Your job is to understand what the user is asking about and call the right tool to look it up.

Key context:
- Work order numbers look like: 25-0001, 26-0012 (YY-NNNN format)
- Part numbers look like: TRA1-TEMP, TRA1-0042, R2S-HOUSING
- This is a 5-person CNC precision machining shop (Traxis Manufacturing)
- "Open" work orders means Active status
- "WO" is short for work order
- "Op" or "ops" means operations (manufacturing steps)

Always call exactly one tool. If the user's request is unclear or just a greeting,
call the show_help tool."""


# =============================================================================
# Tool Definitions (one per query template)
# =============================================================================

TOOLS = [
    {
        "name": "work_order_status",
        "description": "Get the status and key details of a specific work order. Use when the user asks about a work order's status, info, or details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "woNumber": {
                    "type": "string",
                    "description": "The work order number, e.g. '25-0001'"
                }
            },
            "required": ["woNumber"]
        }
    },
    {
        "name": "work_order_operations",
        "description": "List all operations (manufacturing steps) on a specific work order. Use when the user asks what ops/operations are on a work order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "woNumber": {
                    "type": "string",
                    "description": "The work order number, e.g. '25-0001'"
                }
            },
            "required": ["woNumber"]
        }
    },
    {
        "name": "work_order_current_op",
        "description": "Find the current (first incomplete) operation on a work order. Use when the user asks 'where is' a work order, what step it's on, or its current operation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "woNumber": {
                    "type": "string",
                    "description": "The work order number, e.g. '25-0001'"
                }
            },
            "required": ["woNumber"]
        }
    },
    {
        "name": "work_order_time_tracking",
        "description": "Get time tracking data (hours spent, setup time, run time) for a work order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "woNumber": {
                    "type": "string",
                    "description": "The work order number, e.g. '25-0001'"
                }
            },
            "required": ["woNumber"]
        }
    },
    {
        "name": "work_order_due_date",
        "description": "Get the due date for a specific work order. Use when the user asks when something is due or ships.",
        "input_schema": {
            "type": "object",
            "properties": {
                "woNumber": {
                    "type": "string",
                    "description": "The work order number, e.g. '25-0001'"
                }
            },
            "required": ["woNumber"]
        }
    },
    {
        "name": "work_order_quantity",
        "description": "Get quantity ordered and completed for a work order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "woNumber": {
                    "type": "string",
                    "description": "The work order number, e.g. '25-0001'"
                }
            },
            "required": ["woNumber"]
        }
    },
    {
        "name": "list_work_orders",
        "description": "List all work orders from the last 12 months. Use when the user asks to see all work orders or jobs without a specific filter.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_work_orders_by_status",
        "description": "List work orders filtered by status (open, complete, shipped, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "The status to filter by: 'open', 'active', 'pending', 'complete', 'closed', 'shipped', 'invoiced', 'canceled'",
                    "enum": ["open", "active", "pending", "complete", "closed", "shipped", "invoiced", "canceled"]
                }
            },
            "required": ["status"]
        }
    },
    {
        "name": "work_orders_due_this_week",
        "description": "List work orders that are due this week.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "late_work_orders",
        "description": "List work orders that are past due / overdue / late.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "open_work_order_count",
        "description": "Count how many open/active work orders there are.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "largest_active_order",
        "description": "Find the largest active work order by quantity ordered.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "work_order_profitability",
        "description": "Show profitability data (profit, margin, cost) for recent work orders.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "part_info",
        "description": "Get information about a specific part by part number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "partNumber": {
                    "type": "string",
                    "description": "The part number, e.g. 'TRA1-TEMP'"
                }
            },
            "required": ["partNumber"]
        }
    },
    {
        "name": "part_operations",
        "description": "List all operations defined on a specific part (the master routing).",
        "input_schema": {
            "type": "object",
            "properties": {
                "partNumber": {
                    "type": "string",
                    "description": "The part number, e.g. 'TRA1-TEMP'"
                }
            },
            "required": ["partNumber"]
        }
    },
    {
        "name": "part_operation_details",
        "description": "Get detailed operation info including tools and written descriptions/instructions for a part. Optionally filter to a specific operation number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "partNumber": {
                    "type": "string",
                    "description": "The part number, e.g. 'TRA1-TEMP'"
                },
                "opNumber": {
                    "type": "string",
                    "description": "Optional: specific operation number to get details for, e.g. '60'"
                }
            },
            "required": ["partNumber"]
        }
    },
    {
        "name": "list_parts",
        "description": "List all parts in the system.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "show_help",
        "description": "Show available commands and example queries. Use when the user asks for help, what they can do, or their request is unclear.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
]

# Map tool names to template names (most are 1:1, except show_help -> help)
TOOL_TO_TEMPLATE = {tool["name"]: tool["name"] for tool in TOOLS}
TOOL_TO_TEMPLATE["show_help"] = "help"


# =============================================================================
# Claude Intent Classification
# =============================================================================

def classify_intent_claude(
    query: str,
    api_key: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None,
) -> Intent:
    """
    Classify a natural language query using Claude's tool-use capability.

    Args:
        query: The user's natural language query
        api_key: Optional Anthropic API key (falls back to ANTHROPIC_API_KEY env var)
        conversation_history: Optional list of prior messages for context

    Returns:
        An Intent object compatible with the existing system
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Build messages - include conversation history if available
    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": query})

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_choice={"type": "any"},  # Force tool use
        messages=messages,
    )

    # Extract the tool call
    for block in response.content:
        if block.type == "tool_use":
            tool_name = block.name
            tool_input = block.input

            template_name = TOOL_TO_TEMPLATE.get(tool_name, tool_name)

            # Convert partNumber to array format expected by GraphQL
            variables = dict(tool_input)
            if "partNumber" in variables:
                variables["partNumber"] = [variables["partNumber"]]

            return Intent(
                template=template_name,
                variables=variables,
                confidence=0.95,  # Claude is generally high confidence
                raw_query=query,
            )

    # Fallback if no tool was called (shouldn't happen with tool_choice=any)
    return Intent(
        template="help",
        variables={},
        confidence=0.3,
        raw_query=query,
        clarification_needed="I couldn't understand that query. Try 'help' for examples.",
    )


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    test_queries = [
        # Standard queries (should match easily)
        "What's the status of WO 25-0001?",
        "Show me all open work orders",
        "What work orders are due this week?",
        "What operations are on part TRA1-TEMP?",
        "What's the current operation for WO 25-0001?",
        "How much time has been spent on WO 25-0001?",
        "When is WO 25-0001 due?",
        "How many open work orders do we have?",
        "Are there any late work orders?",
        "Show me the tools for Op 60 on part TRA1-TEMP",
        "help",
        "25-0001",  # Just a WO number - regex classifier guesses work_order_status

        # HARD queries that regex would fail on:
        "what's going on with twenty-five dash zero zero zero one",
        "is that R2Sonic housing job done yet",
        "whats the statis of work ordder 25-0001",  # typos!
        "how are we doing on time for that job 26-0003",
        "pull up the ops list for 25-0001",
        "anything running behind schedule?",
        "how many jobs we got going right now",
        "what's our biggest job",
    ]

    print("Claude Intent Classification Tests")
    print("=" * 60)

    for query in test_queries:
        try:
            intent = classify_intent_claude(query)
            print(f"\nQuery: {query}")
            print(f"  Template: {intent.template}")
            print(f"  Variables: {intent.variables}")
            print(f"  Confidence: {intent.confidence:.2f}")
            if intent.clarification_needed:
                print(f"  Clarification: {intent.clarification_needed}")
        except Exception as e:
            print(f"\nQuery: {query}")
            print(f"  ERROR: {e}")
