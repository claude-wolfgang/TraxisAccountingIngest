"""
Chat endpoint — natural language query interface.
Uses Claude AI when ANTHROPIC_API_KEY is set, falls back to pattern matching.
"""

import time
import os
from fastapi import APIRouter

from graphql.client import get_client
from graphql.queries import execute_template
from services.intent_classifier import classify_intent, get_suggestions
from services.response_formatter import format_response, format_error, format_help
from services.ai_chat import ai_chat, ANTHROPIC_API_KEY
from models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _pattern_chat(message: str) -> ChatResponse:
    """Fallback: regex pattern-based chat (no AI needed)."""
    start = time.time()

    if message.lower() in ["help", "?", "h"]:
        return ChatResponse(response=format_help(), template="help", confidence=1.0, meta={"query_time_ms": 0})

    intent = classify_intent(message)

    if intent.clarification_needed:
        suggestions = get_suggestions(message)
        text = intent.clarification_needed + "\n\nTry something like:\n"
        for s in suggestions:
            text += f"  - {s}\n"
        return ChatResponse(
            response=text, template=intent.template, confidence=intent.confidence,
            meta={"query_time_ms": round((time.time() - start) * 1000)},
        )

    if intent.template == "help":
        return ChatResponse(response=format_help(), template="help", confidence=intent.confidence, meta={"query_time_ms": 0})

    client = get_client()
    try:
        result = execute_template(client, intent.template, intent.variables)
        formatted = format_response(intent.template, result)
        return ChatResponse(
            response=formatted, template=intent.template, confidence=intent.confidence,
            data=result, meta={"query_time_ms": round((time.time() - start) * 1000)},
        )
    except Exception as e:
        return ChatResponse(
            success=False, response=format_error(e), template=intent.template,
            confidence=intent.confidence, meta={"query_time_ms": round((time.time() - start) * 1000)},
        )


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a natural language query about ProShop data.

    If ANTHROPIC_API_KEY is set, uses Claude AI for intelligent responses.
    Otherwise falls back to pattern matching.
    """
    start = time.time()
    message = request.message.strip()

    if not message:
        return ChatResponse(response="Please enter a question.", confidence=0.0)

    # Use AI chat if API key is configured
    if ANTHROPIC_API_KEY:
        result = ai_chat(message)
        return ChatResponse(
            success=True,
            response=result["response"],
            template=None,
            confidence=1.0 if result["ai_powered"] else 0.5,
            meta={
                "query_time_ms": round((time.time() - start) * 1000),
                "ai_powered": result["ai_powered"],
                "tools_used": [t["tool"] for t in result.get("tool_calls", [])],
            },
        )

    # Fallback to pattern matching
    return _pattern_chat(message)
