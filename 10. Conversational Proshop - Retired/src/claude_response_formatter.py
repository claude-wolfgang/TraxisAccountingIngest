"""
Claude-Powered Response Formatter for ProShop Conversational Interface.
Replaces ASCII table formatting with natural language responses from Claude.

Takes the raw JSON data from a ProShop query and has Claude summarize it
in a conversational, shop-floor-friendly way.
"""

import json
import os
from typing import Any, Optional, List, Dict
import anthropic


# =============================================================================
# Configuration
# =============================================================================

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a helpful assistant for Traxis Manufacturing, a 5-person CNC precision machining shop.
You're answering questions about their ProShop ERP data. Keep responses:

- SHORT and scannable (shop floor workers are busy)
- Use plain language, not jargon
- Bold the most important info (work order numbers, statuses, due dates)
- For lists of work orders, use a compact format - not verbose paragraphs
- Flag anything urgent (late orders, approaching due dates) clearly
- If data is empty or null, say so plainly instead of showing "N/A"
- Round hours to 1 decimal place
- Format dates as "Mon DD" (e.g., "Jan 30") - skip the year unless it's not the current year
- If a work order is late, call it out prominently
- Don't add fluff or pleasantries - just the info they need
- Use markdown formatting (bold, bullet points) for readability

ProShop status values and what they mean:
- "Active" = currently being worked on (users call this "open")
- "Manufacturing Complete" = all machining done, awaiting QC/shipping
- "Complete" = fully done
- "Invoiced" = billed to customer
- "Shipped" = sent to customer
- "Canceled" = canceled

When showing operation details:
- setupTime and runTime from ProShop are in SECONDS, convert to hours/minutes
- isOpComplete: true/false indicates if that step is done"""


# =============================================================================
# Template context hints (helps Claude understand the data shape)
# =============================================================================

TEMPLATE_HINTS = {
    "work_order_status": "This is a single work order's status and details.",
    "work_order_operations": "This is the list of manufacturing operations (steps) on a work order. The ops.records array contains each operation.",
    "work_order_current_op": "This shows the current (first incomplete) operation. The 'current_operation' field has the active op, or all ops may be complete.",
    "work_order_time_tracking": "This is time tracking data showing hours spent on the work order, with individual time entries.",
    "work_order_due_date": "This is the due date info for a work order. Check if it's past due.",
    "work_order_quantity": "This is the quantity ordered vs completed for a work order.",
    "list_work_orders": "This is a list of work orders. Show as a compact list.",
    "list_work_orders_by_status": "This is a filtered list of work orders by status. Show as a compact list.",
    "work_orders_due_this_week": "These are work orders due this week. Highlight any that are urgent.",
    "late_work_orders": "These are LATE/overdue work orders. This is urgent info - emphasize it.",
    "open_work_order_count": "This is a count of open work orders. The 'count' field has the number.",
    "largest_active_order": "This is the single largest active work order by quantity.",
    "work_order_profitability": "This is profitability data for work orders including profit margins and costs.",
    "part_info": "This is information about a specific part (the data is an array of matching parts).",
    "part_operations": "This is the master routing - all operations defined on a part.",
    "part_operation_details": "This is detailed operation info including tools and written instructions/descriptions.",
    "list_parts": "This is a list of all parts in the system.",
}


# =============================================================================
# Formatter
# =============================================================================

def format_response_claude(
    template_name: str,
    data: Any,
    user_query: str,
    api_key: Optional[str] = None,
    conversation_context: Optional[List[Dict]] = None,
) -> str:
    """
    Format query results using Claude for natural language output.

    Args:
        template_name: Which query template produced this data
        data: The raw JSON data from the ProShop query
        user_query: The original user question (for context)
        api_key: Optional Anthropic API key
        conversation_context: Optional prior conversation for context

    Returns:
        A natural language response string
    """
    # Handle help separately - no API call needed
    if template_name == "help":
        return _format_help()

    # Handle empty/null data
    if data is None:
        return "No data found. Please check the work order or part number and try again."

    client = anthropic.Anthropic(api_key=api_key)

    # Build the prompt with the data
    hint = TEMPLATE_HINTS.get(template_name, "")
    data_str = json.dumps(data, indent=2, default=str)

    # Truncate very large data to avoid token waste
    if len(data_str) > 8000:
        data_str = data_str[:8000] + "\n... (truncated)"

    prompt = f"""The user asked: "{user_query}"

Query type: {template_name}
{f'Context: {hint}' if hint else ''}

Here is the data from ProShop ERP:

```json
{data_str}
```

Provide a concise, readable answer to their question based on this data."""

    # Build messages
    messages = []
    if conversation_context:
        # Include recent conversation for context
        messages.extend(conversation_context[-4:])
    messages.append({"role": "user", "content": prompt})

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    return response.content[0].text


def format_error_claude(error: Exception) -> str:
    """Format an error message. No API call needed for errors."""
    error_msg = str(error)

    if "INVALID_PERMISSIONS" in error_msg:
        return "Permission denied - this query needs additional API access that hasn't been enabled yet."
    if "not found" in error_msg.lower():
        return "Couldn't find that. Double-check the work order or part number?"
    if "authentication" in error_msg.lower():
        return "Authentication failed - credentials may need to be refreshed."
    if "rate" in error_msg.lower() and "limit" in error_msg.lower():
        return "Too many requests - give it a few seconds and try again."

    return f"Something went wrong: {error_msg}"


def _format_help() -> str:
    """Static help text - no API call needed."""
    return """**ProShop Assistant** - Ask me anything about work orders and parts!

**Work Orders:**
- "What's the status of 25-0001?"
- "Show me all open work orders"
- "What's due this week?"
- "Anything running late?"
- "What ops are on 25-0001?"
- "Where is 25-0001 right now?" (current operation)
- "How much time on 25-0001?"
- "What's our biggest job?"
- "Show me profitability"

**Parts:**
- "What operations are on part TRA1-TEMP?"
- "Show me part TRA1-TEMP"
- "Tools for Op 60 on TRA1-TEMP"
- "List all parts"

**Tips:**
- I remember our conversation - ask follow-up questions naturally
- "What about its operations?" works after asking about a WO
- Type **quit** or **exit** to leave"""
