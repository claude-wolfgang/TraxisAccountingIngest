"""
AI-Powered Chat Service using Claude API.
Claude acts as a ProShop assistant that can query the ERP system using tools.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import anthropic

from graphql.client import get_client
from graphql.queries import execute_template, QUERY_TEMPLATES

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are ProShop Assistant, an AI helper for Traxis Manufacturing's shop floor.
You help machinists, shop managers, and operators query their ProShop ERP system using natural language.

You have access to tools that query ProShop's database. Use them to answer questions about:
- Work orders (status, operations, due dates, quantities, time tracking)
- Late/overdue work orders
- Work orders due this week
- Open work order counts

IMPORTANT CONTEXT:
- Work order numbers look like: 25-0001, 26-0045 (YY-NNNN format)
- The "25-" prefix means year 2025, "26-" means 2026
- Statuses: Active, Manufacturing Complete, Complete, Invoiced, Shipped, Canceled
- "Open" means Active or Manufacturing Complete
- Parts queries are currently unavailable due to API scope restrictions

RESPONSE STYLE:
- Be concise and direct — these are busy shop floor workers
- Lead with the most important info
- Use numbers and dates prominently
- If a work order is late, flag it clearly
- Don't explain what tools you're using — just give the answer
- For lists, summarize key stats first, then show details"""

# Define tools that Claude can use to query ProShop
TOOLS = [
    {
        "name": "get_work_order",
        "description": "Get status and details of a specific work order. Returns: WO number, status, due date, quantity ordered, quantity complete, hours spent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number": {
                    "type": "string",
                    "description": "Work order number in format YY-NNNN (e.g., '25-0001', '26-0045')"
                }
            },
            "required": ["wo_number"]
        }
    },
    {
        "name": "get_work_order_operations",
        "description": "Get the list of operations (manufacturing steps) for a specific work order. Returns each operation's number, description, completion status, setup time, and run time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number": {
                    "type": "string",
                    "description": "Work order number (e.g., '25-0001')"
                }
            },
            "required": ["wo_number"]
        }
    },
    {
        "name": "get_current_operation",
        "description": "Get the current (first incomplete) operation for a work order — shows where the job is in the manufacturing process.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number": {
                    "type": "string",
                    "description": "Work order number (e.g., '25-0001')"
                }
            },
            "required": ["wo_number"]
        }
    },
    {
        "name": "get_time_tracking",
        "description": "Get time tracking data for a work order — total hours, setup hours, run hours, and individual time entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wo_number": {
                    "type": "string",
                    "description": "Work order number (e.g., '25-0001')"
                }
            },
            "required": ["wo_number"]
        }
    },
    {
        "name": "list_work_orders",
        "description": "List all work orders from the last 12 months. Can optionally filter by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optional status filter: 'open', 'active', 'complete', 'shipped', 'invoiced', 'canceled'",
                    "enum": ["open", "active", "complete", "shipped", "invoiced", "canceled"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_late_work_orders",
        "description": "Get all work orders that are past their due date and not yet complete. These are overdue/late jobs.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_due_this_week",
        "description": "Get all work orders due this week (between today and end of the week).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_open_count",
        "description": "Get the count of currently open (Active + Manufacturing Complete) work orders from the last 12 months.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_largest_active_order",
        "description": "Find the largest currently active work order by quantity ordered.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_profitability",
        "description": "Get profitability data for recent work orders — DLH, profit, margin, and total cost.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


def _execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Any:
    """Execute a ProShop query tool and return the result."""
    client = get_client()

    tool_to_template = {
        "get_work_order": ("work_order_status", lambda i: {"woNumber": i["wo_number"]}),
        "get_work_order_operations": ("work_order_operations", lambda i: {"woNumber": i["wo_number"]}),
        "get_current_operation": ("work_order_current_op", lambda i: {"woNumber": i["wo_number"]}),
        "get_time_tracking": ("work_order_time_tracking", lambda i: {"woNumber": i["wo_number"]}),
        "list_work_orders": ("list_work_orders_by_status" if "status" in tool_input and tool_input["status"] else "list_work_orders",
                             lambda i: {"status": i.get("status", "")} if i.get("status") else {}),
        "get_late_work_orders": ("late_work_orders", lambda i: {}),
        "get_due_this_week": ("work_orders_due_this_week", lambda i: {}),
        "get_open_count": ("open_work_order_count", lambda i: {}),
        "get_largest_active_order": ("largest_active_order", lambda i: {}),
        "get_profitability": ("work_order_profitability", lambda i: {}),
    }

    if tool_name not in tool_to_template:
        return {"error": f"Unknown tool: {tool_name}"}

    template_name, var_fn = tool_to_template[tool_name]
    variables = var_fn(tool_input)

    try:
        result = execute_template(client, template_name, variables)
        # Truncate large results to avoid token overflow
        result_str = json.dumps(result, default=str)
        if len(result_str) > 8000:
            # For lists, limit records
            if isinstance(result, dict) and "records" in result:
                result["records"] = result["records"][:30]
                result["_truncated"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


def ai_chat(message: str, conversation_history: list = None) -> Dict[str, Any]:
    """
    Process a chat message using Claude AI with ProShop tools.

    Returns:
        Dict with 'response' (text), 'tool_calls' (list of tools used), 'error' (if any)
    """
    if not ANTHROPIC_API_KEY:
        return {
            "response": "AI chat is not configured. Please set the ANTHROPIC_API_KEY environment variable.\n\n"
                        "Get your API key at: https://console.anthropic.com/\n"
                        "Then add to your .env file: ANTHROPIC_API_KEY=sk-ant-...",
            "tool_calls": [],
            "ai_powered": False,
        }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build messages
    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": message})

    tool_calls_made = []

    try:
        # Initial request to Claude
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Handle tool use loop (Claude may call multiple tools)
        while response.stop_reason == "tool_use":
            # Extract tool use blocks
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            # Execute each tool
            tool_results = []
            for tool_use in tool_use_blocks:
                logger.info(f"AI calling tool: {tool_use.name}({json.dumps(tool_use.input)})")
                tool_calls_made.append({"tool": tool_use.name, "input": tool_use.input})

                result = _execute_tool(tool_use.name, tool_use.input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result, default=str),
                })

            # Send tool results back to Claude
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

        # Extract final text response
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        final_response = "\n".join(text_blocks) if text_blocks else "I couldn't generate a response."

        return {
            "response": final_response,
            "tool_calls": tool_calls_made,
            "ai_powered": True,
        }

    except anthropic.AuthenticationError:
        return {
            "response": "Invalid Anthropic API key. Please check your ANTHROPIC_API_KEY in the .env file.",
            "tool_calls": [],
            "ai_powered": False,
        }
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return {
            "response": f"AI error: {str(e)}",
            "tool_calls": [],
            "ai_powered": False,
        }
