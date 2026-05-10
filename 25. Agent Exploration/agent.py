"""
Traxis Manufacturing Data Quality Agent.

Claude-powered agent with MCP tools for querying ProShop ERP, FOCAS machine
monitoring, and audit history via natural language.

Usage:
    python agent.py "which jobs are overrunning?"     # One-shot query
    python agent.py                                    # Interactive mode (stateful)
"""

import os
import sys
import asyncio
from datetime import datetime

import config
# Ensure the SDK picks up the API key
if config.ANTHROPIC_API_KEY:
    os.environ.setdefault("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY)

from claude_agent_sdk import (
    query,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from mcp_tools import (
    create_proshop_server, create_focas_server, create_audit_server,
    create_reminders_server,
)

TRAXIS_SYSTEM_PROMPT = """\
You are a data quality analyst for Traxis Manufacturing, a CNC machine shop in Austin, TX.

You have access to three data sources via MCP tools:
1. **ProShop ERP** (proshop tools) - Work orders, operations, scheduling, hours tracking
2. **FOCAS Machine Monitoring** (focas tools) - Real-time machine status, utilization, alarms
3. **Audit Database** (audit tools) - Historical audit results and trend data

## Shop Context
- ~68 active work orders at any time, ~490 operations
- 8 mills + 2 lathes. FOCAS-connected: M2, M3, M6, M8 (mills), T2 (lathe)
- Mill-1 (Haas VF-5), Mill-4/5/7 (Robodrills) have no FOCAS monitoring
- Target shop rate: $197/hr. Effective rate has been ~$165/hr due to overruns
- Historical overrun rate: ~64% of jobs exceed quoted hours by ~19% average

## Machine ID Mapping
| ProShop Name | FOCAS ID | Machine |
|---|---|---|
| Mill-2 | M2 | FANUC Mill 2 |
| Mill-3 | M3 | FANUC Mill 3 |
| Mill-6 | M6 | FANUC Mill 6 |
| Mill-8 | M8 | Hyundai-Wia KF5600II |
| Lathe-2 | T2 | YCM NTC1600LY |

## ProShop Domain Knowledge
- WO numbers: YY-NNNN format (e.g. 25-0001 = year 2025, first job)
- Part numbers: TRA1-TEMP, TRA1-0042, R2S-HOUSING (case-sensitive in API)
- "WO" = work order, "op"/"ops" = operations
- Status values: Active, Complete, Manufacturing Complete, Invoiced, Shipped, Canceled
- Common aliases: "open"/"active" = Active, "complete" = Complete/MfgComplete/Invoiced
- setupTime and runTime from ProShop ops are in SECONDS, not hours
- Dates: show as "Mon DD" unless different year

## Tool Selection
- Single WO question ("what's 25-0001?") -> use get_work_order (fast, targeted)
- Time spent on a WO -> use get_work_order_time_tracking
- Profitability/margins -> use get_work_order_profitability
- Part info -> use get_part_info or get_part_operations
- Filter by status/due date ("what's late?", "due this week?") -> use search_work_orders
- All active WOs (broad analysis) -> use get_active_work_orders
- Overrun analysis -> use get_completed_work_orders
- Machine status -> use FOCAS tools
- Historical trends -> use audit tools

## Response Style
- Keep responses SHORT and scannable -- shop floor workers are busy
- Lead with the answer, then supporting detail
- Use tables for multi-row data
- Be specific with numbers: round hours to 1 decimal, percentages to 1 decimal
- Flag actionable issues: overdue WOs, uncertified operations, low utilization
- FOCAS data may be stale if running on the Dropbox sync PC (not the collector at 10.1.1.71)
"""

ALLOWED_TOOLS = [
    "mcp__proshop__check_proshop_health",
    "mcp__proshop__get_active_work_orders",
    "mcp__proshop__get_completed_work_orders",
    "mcp__proshop__get_work_cells",
    "mcp__proshop__get_work_order",
    "mcp__proshop__get_work_order_time_tracking",
    "mcp__proshop__get_work_order_profitability",
    "mcp__proshop__get_part_info",
    "mcp__proshop__get_part_operations",
    "mcp__proshop__search_work_orders",
    "mcp__focas__check_focas_health",
    "mcp__focas__get_machine_utilization",
    "mcp__focas__get_recent_alarms",
    "mcp__focas__get_active_programs",
    "mcp__audit__run_full_audit",
    "mcp__audit__get_latest_audit",
    "mcp__audit__get_audit_history",
    "mcp__audit__get_metric_trend",
    "mcp__reminders__schedule_reminder",
    "mcp__reminders__list_reminders",
    "mcp__reminders__cancel_reminder",
]


def _make_options():
    """Build ClaudeAgentOptions with all MCP servers and tools."""
    now = datetime.now().strftime("%A, %B %d %Y %I:%M %p")
    prompt = TRAXIS_SYSTEM_PROMPT + f"\nCurrent date/time: {now}\n"
    return ClaudeAgentOptions(
        model="claude-sonnet-4-6",
        system_prompt=prompt,
        mcp_servers={
            "proshop": create_proshop_server(),
            "focas": create_focas_server(),
            "audit": create_audit_server(),
            "reminders": create_reminders_server(),
        },
        allowed_tools=ALLOWED_TOOLS,
    )


async def run_query(prompt):
    """Execute a single stateless query against the Traxis agent."""
    options = _make_options()

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)


async def interactive():
    """Run a stateful interactive session. Conversation context is preserved
    across turns so follow-up questions work naturally."""
    print("Traxis Data Quality Agent (stateful session)")
    print("Ask questions about work orders, machines, audit results, etc.")
    print("Follow-up questions work -- context is preserved between turns.")
    print("Type 'quit' or 'exit' to stop.\n")

    options = _make_options()

    async with ClaudeSDKClient(options) as client:
        while True:
            try:
                prompt = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not prompt:
                continue
            if prompt.lower() in ("quit", "exit", "q"):
                break

            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text)
                elif isinstance(message, ResultMessage):
                    # Response complete for this turn
                    pass
            print()


def main():
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        asyncio.run(run_query(prompt))
    else:
        asyncio.run(interactive())


if __name__ == "__main__":
    main()
