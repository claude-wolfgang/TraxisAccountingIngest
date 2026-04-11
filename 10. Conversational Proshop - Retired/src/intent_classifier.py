"""
Intent Classifier for ProShop Conversational Interface.
Maps natural language queries to query templates and extracts parameters.
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class Intent:
    """Represents a classified intent with extracted parameters."""
    template: str
    variables: Dict[str, Any]
    confidence: float
    raw_query: str
    clarification_needed: Optional[str] = None


# =============================================================================
# Pattern Definitions
# =============================================================================

# Work order number patterns
WO_PATTERNS = [
    r'\b(\d{2}-\d{4})\b',                    # 25-0001
    r'\bwo\s*#?\s*(\d{2}-\d{4})\b',          # WO 25-0001, WO# 25-0001
    r'\bwork\s*order\s*#?\s*(\d{2}-\d{4})\b', # work order 25-0001
]

# Part number patterns
PART_PATTERNS = [
    r'\bpart\s+([A-Z0-9]+-[A-Z0-9]+(?:-[A-Z0-9]+)?)\b',  # part TRA1-TEMP
    r'\b([A-Z]{2,4}\d*-[A-Z0-9]+(?:-[A-Z0-9]+)?)\b',     # TRA1-TEMP pattern
]

# Operation number patterns
OP_PATTERNS = [
    r'\bop\s*#?\s*(\d+)\b',                  # op 60, op# 60
    r'\boperation\s*#?\s*(\d+)\b',           # operation 60
    r'\bop\.?\s*(\d+)\b',                    # op. 60
]

# Status patterns
STATUS_KEYWORDS = {
    "open": ["open", "active", "in progress", "in-progress", "started"],
    "pending": ["pending", "waiting", "queued"],
    "complete": ["complete", "completed", "done", "finished"],
    "closed": ["closed"],
    "shipped": ["shipped", "delivered"],
}


# =============================================================================
# Intent Patterns
# =============================================================================

INTENT_PATTERNS = [
    # Profitability (must come before work order status to avoid partial match)
    {
        "patterns": [
            r"profitability",
            r"profit\s+margin",
            r"how\s+profitable",
            r"work\s*order\s+profitability",
            r"show.*profitability",
        ],
        "template": "work_order_profitability",
        "requires": [],
    },

    # Work Order Status
    {
        "patterns": [
            r"(status|info|details?)\s*(of|for|on)?\s*(wo|work\s*order)",
            r"(wo|work\s*order).*?(status|info|details?)",
            r"what('s|\s+is)\s+(the\s+)?status\s+of",
            r"show\s+me\s+(wo|work\s*order)",
            r"get\s+(wo|work\s*order)",
        ],
        "template": "work_order_status",
        "requires": ["woNumber"],
    },

    # Work Order Operations
    {
        "patterns": [
            r"(operations?|ops?)\s*(on|for|of)\s*(wo|work\s*order)",
            r"(operations?|ops?)\s*(on|for|of)\s*\d{2}-\d{4}",
            r"show\s+me\s+(the\s+)?(operations?|ops?)\s*(on|for)",
            r"(wo|work\s*order).*?(operations?|ops?)",
            r"what\s+(operations?|ops?)\s+(are\s+)?(on|for)",
        ],
        "template": "work_order_operations",
        "requires": ["woNumber"],
    },

    # Current Operation
    {
        "patterns": [
            r"current\s+(operation|op)",
            r"what('s|\s+is)\s+(the\s+)?current\s+(operation|op)",
            r"where\s+is\s+(wo|work\s*order)",
            r"what\s+step\s+is",
        ],
        "template": "work_order_current_op",
        "requires": ["woNumber"],
    },

    # Time Tracking
    {
        "patterns": [
            r"(time|hours?)\s+(spent|tracked|on)",
            r"how\s+much\s+time",
            r"time\s+tracking",
        ],
        "template": "work_order_time_tracking",
        "requires": ["woNumber"],
    },

    # Due Date
    {
        "patterns": [
            r"when\s+is.*?due",
            r"due\s+date",
            r"when\s+does.*?ship",
            r"deadline\s+for",
        ],
        "template": "work_order_due_date",
        "requires": ["woNumber"],
    },

    # Quantity
    {
        "patterns": [
            r"(quantity|qty|how\s+many)\s+(for|on|of)",
            r"what('s|\s+is)\s+(the\s+)?(quantity|qty)",
        ],
        "template": "work_order_quantity",
        "requires": ["woNumber"],
    },

    # Late Work Orders
    {
        "patterns": [
            r"(late|overdue|past\s+due)\s*(work\s*orders?|wo)?",
            r"(any|are\s+there)\s+(late|overdue)",
            r"what('s|\s+is)\s+late",
        ],
        "template": "late_work_orders",
        "requires": [],
    },

    # Due This Week
    {
        "patterns": [
            r"due\s+this\s+week",
            r"what.*?due\s+this\s+week",
            r"this\s+week('s)?\s+work",
        ],
        "template": "work_orders_due_this_week",
        "requires": [],
    },

    # Open Work Order Count
    {
        "patterns": [
            r"how\s+many\s+(open|active)",
            r"count\s+(of\s+)?(open|active)",
            r"number\s+of\s+(open|active)",
        ],
        "template": "open_work_order_count",
        "requires": [],
    },

    # Largest Active Order
    {
        "patterns": [
            r"(largest|biggest|most)\s+(active|open)\s*(order|wo|work\s*order)?",
            r"(largest|biggest|most)\s+(order|wo|work\s*order).*?(active|open)",
            r"(active|open)\s*(order|wo|work\s*order).*?(largest|biggest|most)",
            r"(largest|biggest)\s+quantity",
        ],
        "template": "largest_active_order",
        "requires": [],
    },

    # List Work Orders by Status
    {
        "patterns": [
            r"(show|list|get)\s+(me\s+)?(all\s+)?(open|in\s+process|pending|complete|closed|shipped)\s+(work\s*orders?|wo|jobs?)",
            r"(all|show)\s+(work\s*orders?|wo|jobs?)\s+(that\s+are\s+)?(open|in\s+process|pending|complete|closed|shipped)",
            r"(work\s*orders?|wo|jobs?)\s+(in|with)\s+.*(status|state)",
        ],
        "template": "list_work_orders_by_status",
        "requires": ["status"],
    },

    # List All Work Orders
    {
        "patterns": [
            r"(show|list|get)\s+(me\s+)?(all\s+)?(work\s*orders?|wo|jobs?)",
            r"all\s+(work\s*orders?|wo|jobs?)",
            r"what\s+(work\s*orders?|wo|jobs?)\s+do\s+we\s+have",
        ],
        "template": "list_work_orders",
        "requires": [],
    },

    # Part Operations
    {
        "patterns": [
            r"(operations?|ops?)\s*(on|for|of)\s*part",
            r"part.*?(operations?|ops?)",
            r"what\s+(operations?|ops?)\s+(are\s+)?(on|for)\s+part",
        ],
        "template": "part_operations",
        "requires": ["partNumber"],
    },

    # Part Operation Details (with specific op)
    {
        "patterns": [
            r"(details?|info|sequence)\s*(for|of|on)\s*(op|operation)",
            r"(tools?|tooling)\s*(for|on|needed)",
            r"show\s+me\s+(op|operation)\s*\d+",
        ],
        "template": "part_operation_details",
        "requires": ["partNumber", "opNumber"],
    },

    # Part Info
    {
        "patterns": [
            r"(show|get|info|details?)\s*(me\s+)?part",
            r"what\s+is\s+part",
            r"part\s+info",
        ],
        "template": "part_info",
        "requires": ["partNumber"],
    },

    # List Parts
    {
        "patterns": [
            r"(show|list|get)\s+(me\s+)?(all\s+)?parts?$",
            r"all\s+parts",
            r"what\s+parts\s+do\s+we\s+have",
        ],
        "template": "list_parts",
        "requires": [],
    },

    # Help
    {
        "patterns": [
            r"^help$",
            r"what\s+can\s+you\s+do",
            r"how\s+do\s+i",
            r"show\s+(me\s+)?examples?",
            r"what\s+can\s+i\s+ask",
        ],
        "template": "help",
        "requires": [],
    },
]


# =============================================================================
# Extraction Functions
# =============================================================================

def extract_wo_number(text: str) -> Optional[str]:
    """Extract work order number from text."""
    for pattern in WO_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_part_number(text: str) -> Optional[str]:
    """Extract part number from text."""
    for pattern in PART_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def extract_op_number(text: str) -> Optional[str]:
    """Extract operation number from text."""
    for pattern in OP_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_status(text: str) -> Optional[str]:
    """Extract status from text."""
    text_lower = text.lower()
    for status, keywords in STATUS_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return status
    return None


# =============================================================================
# Intent Classification
# =============================================================================

def classify_intent(query: str) -> Intent:
    """
    Classify a natural language query into an intent with extracted parameters.

    Args:
        query: The user's natural language query

    Returns:
        An Intent object with the classified template and extracted variables
    """
    query_lower = query.lower().strip()
    best_match = None
    best_confidence = 0.0

    # Try to match against intent patterns
    for intent_def in INTENT_PATTERNS:
        for pattern in intent_def["patterns"]:
            if re.search(pattern, query_lower):
                confidence = 0.8  # Base confidence for pattern match

                # Check if we have required parameters
                variables = {}
                missing = []

                for req in intent_def["requires"]:
                    if req == "woNumber":
                        wo = extract_wo_number(query)
                        if wo:
                            variables["woNumber"] = wo
                            confidence += 0.1
                        else:
                            missing.append("work order number")

                    elif req == "partNumber":
                        part = extract_part_number(query)
                        if part:
                            variables["partNumber"] = [part]  # API expects array
                            confidence += 0.1
                        else:
                            missing.append("part number")

                    elif req == "opNumber":
                        op = extract_op_number(query)
                        if op:
                            variables["opNumber"] = op
                            confidence += 0.05
                        # op number is often optional

                    elif req == "status":
                        status = extract_status(query)
                        if status:
                            variables["status"] = status
                            confidence += 0.1
                        else:
                            missing.append("status")

                if confidence > best_confidence:
                    clarification = None
                    if missing:
                        clarification = f"Please provide: {', '.join(missing)}"

                    best_match = Intent(
                        template=intent_def["template"],
                        variables=variables,
                        confidence=confidence,
                        raw_query=query,
                        clarification_needed=clarification if missing and intent_def["requires"] else None
                    )
                    best_confidence = confidence

    # If no pattern matched, try to guess based on extracted entities
    if not best_match:
        variables = {}
        wo = extract_wo_number(query)
        part = extract_part_number(query)

        if wo:
            variables["woNumber"] = wo
            return Intent(
                template="work_order_status",
                variables=variables,
                confidence=0.5,
                raw_query=query,
            )
        elif part:
            variables["partNumber"] = [part]
            return Intent(
                template="part_info",
                variables=variables,
                confidence=0.5,
                raw_query=query,
            )
        else:
            # Fallback to help
            return Intent(
                template="help",
                variables={},
                confidence=0.3,
                raw_query=query,
                clarification_needed="I'm not sure what you're asking. Try 'help' to see examples."
            )

    return best_match


def get_suggestions(query: str) -> List[str]:
    """Get suggested queries based on partial input."""
    query_lower = query.lower()
    suggestions = []

    if "wo" in query_lower or "work" in query_lower:
        suggestions.extend([
            "What's the status of WO 25-0001?",
            "Show me all open work orders",
            "What operations are on WO 25-0001?",
        ])

    if "part" in query_lower:
        suggestions.extend([
            "What operations are on part TRA1-TEMP?",
            "Show me part TRA1-TEMP",
        ])

    if "due" in query_lower:
        suggestions.extend([
            "What work orders are due this week?",
            "When is WO 25-0001 due?",
            "Are there any late work orders?",
        ])

    if not suggestions:
        suggestions = [
            "What's the status of WO 25-0001?",
            "Show me all open work orders",
            "What operations are on part TRA1-TEMP?",
            "Are there any late work orders?",
        ]

    return suggestions[:4]


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    # Test queries
    test_queries = [
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
        "25-0001",  # Just a WO number
        "something random",  # Should fallback
    ]

    print("Intent Classification Tests\n" + "="*50)
    for query in test_queries:
        intent = classify_intent(query)
        print(f"\nQuery: {query}")
        print(f"  Template: {intent.template}")
        print(f"  Variables: {intent.variables}")
        print(f"  Confidence: {intent.confidence:.2f}")
        if intent.clarification_needed:
            print(f"  Clarification: {intent.clarification_needed}")
