# Project 10: Conversational ProShop -- RETIRED

**Retired:** 2026-03-28
**Absorbed into:** Project 25 (Agent Exploration) -- `agent.py`

## What Was Ported
- Single work order queries (get_work_order)
- Time tracking queries (get_work_order_time_tracking)
- Profitability queries (get_work_order_profitability)
- Part info and part operations queries
- Status filtering with mapping (open/active/complete/late/due this week)
- Conversation memory (ClaudeSDKClient stateful sessions)
- ProShop domain knowledge (WO format, time units, status aliases)

## Why
Project 25's agent.py covers everything this project did plus FOCAS machine
monitoring and audit history. The Claude Agent SDK approach (tool selection by
the model) replaces the template-based query router, handling edge cases and
follow-up questions more naturally.

## Reference Value
`src/query_templates.py` remains useful as a reference for ProShop GraphQL
field names and query patterns.
