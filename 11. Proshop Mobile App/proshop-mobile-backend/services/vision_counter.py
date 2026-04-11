"""
Vision-based part counting using Claude's vision API.
Sends a camera frame to Claude and gets back a part count.
"""

import json
import logging
import os
import re
from typing import Dict, Any

import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

COUNTING_PROMPT = """You are a manufacturing part counter. Count the number of discrete parts/objects visible in this image.

Rules:
- Count individual distinct parts, components, or manufactured items
- If parts are stacked or overlapping, estimate the total count
- If no countable parts are visible, return count 0
- Be specific about what you counted in the description

{context}

Respond with ONLY this JSON (no markdown, no backticks):
{{"count": <integer>, "confidence": "<high|medium|low>", "description": "<what you counted, 10 words max>"}}"""


def count_parts(image_base64: str, context: str = "") -> Dict[str, Any]:
    """
    Send an image to Claude Vision and get a part count.

    Args:
        image_base64: Base64-encoded JPEG image data (no data: prefix)
        context: Optional hint like "aluminum spacers" or "WO 25-0294 expects 50"

    Returns:
        Dict with count, confidence, description, error
    """
    if not ANTHROPIC_API_KEY:
        return {
            "count": 0,
            "confidence": "low",
            "description": "",
            "error": "ANTHROPIC_API_KEY not set",
        }

    # Strip data URL prefix if present
    if "," in image_base64[:100]:
        image_base64 = image_base64.split(",", 1)[1]

    context_line = f"Context from the user: {context}" if context else ""
    prompt = COUNTING_PROMPT.format(context=context_line)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        raw = response.content[0].text.strip()
        logger.info(f"Vision response: {raw}")
        return _parse_response(raw)

    except anthropic.AuthenticationError:
        return {
            "count": 0,
            "confidence": "low",
            "description": "",
            "error": "Invalid Anthropic API key",
        }
    except Exception as e:
        logger.error(f"Vision counting error: {e}")
        return {
            "count": 0,
            "confidence": "low",
            "description": "",
            "error": str(e),
        }


def _parse_response(raw: str) -> Dict[str, Any]:
    """Parse Claude's JSON response with multiple fallback strategies."""

    # Strategy 1: Direct JSON parse
    try:
        data = json.loads(raw)
        return _normalize(data)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract JSON from markdown code block
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if md_match:
        try:
            data = json.loads(md_match.group(1))
            return _normalize(data)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find first {...} in text
    brace_match = re.search(r"\{[^{}]*\}", raw)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            return _normalize(data)
        except json.JSONDecodeError:
            pass

    # Strategy 4: Regex extraction of count/confidence
    count_match = re.search(r'"?count"?\s*[:=]\s*(\d+)', raw)
    conf_match = re.search(r'"?confidence"?\s*[:=]\s*"?(high|medium|low)"?', raw, re.IGNORECASE)
    if count_match:
        return {
            "count": int(count_match.group(1)),
            "confidence": conf_match.group(1).lower() if conf_match else "low",
            "description": "Parsed from text response",
            "error": None,
        }

    # Give up
    return {
        "count": 0,
        "confidence": "low",
        "description": raw[:100],
        "error": "Could not parse vision response",
    }


def _normalize(data: dict) -> Dict[str, Any]:
    """Normalize parsed JSON into expected format."""
    count = int(data.get("count", 0))
    confidence = str(data.get("confidence", "low")).lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    description = str(data.get("description", ""))
    return {
        "count": count,
        "confidence": confidence,
        "description": description,
        "error": None,
    }
