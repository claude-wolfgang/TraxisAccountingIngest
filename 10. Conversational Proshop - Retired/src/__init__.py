"""
ProShop Conversational Interface
A natural language interface for querying ProShop ERP.
"""

from .proshop_client import ProShopClient, get_client
from .query_templates import execute_template, get_template, list_templates
from .intent_classifier import classify_intent, Intent
from .response_formatter import format_response, format_error

__all__ = [
    "ProShopClient",
    "get_client",
    "execute_template",
    "get_template",
    "list_templates",
    "classify_intent",
    "Intent",
    "format_response",
    "format_error",
]
