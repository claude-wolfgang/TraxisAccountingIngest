"""
AI-powered tool spec lookup using Anthropic API + web search.

Uses Claude Haiku with the web_search server-side tool to find manufacturer
tool specs from an EDP or catalog number, classify the tool type, and return
structured data ready for ProShop field mapping.
"""

import json
import re

import anthropic

from proshop_tools import get_anthropic_key


TOOL_GROUP_MAP = {
    "drill": "D",
    "endmill": "EM",
    "tap": "TP",
    "reamer": "RM",
    "insert": "TN",
    "holder": "TH",
    "boring_bar": "BB",
    "countersink": "CS",
    "counterbore": "CB",
    "thread_mill": "TM",
    "face_mill": "FM",
    "slitting_saw": "SS",
    "chamfer_mill": "CM",
    "spot_drill": "SD",
}

SYSTEM_PROMPT = """You are a cutting tool specifications expert. Your job is to search the web for a specific cutting tool product and extract its specifications into structured JSON.

INSTRUCTIONS:
1. Search for the tool using the manufacturer name and EDP/catalog number provided.
2. Check distributor sites (MSC Direct, Penn Tool Co, Grainger, Carbide Depot) if the manufacturer site is unavailable.
3. Identify the tool type (drill, endmill, tap, insert, reamer, holder, boring_bar, countersink, counterbore, thread_mill, face_mill, slitting_saw, chamfer_mill, spot_drill).
4. Extract all available specifications.
5. Return ONLY a JSON object — no other text before or after.

CRITICAL RULES:
- All linear dimensions must be in INCHES. Convert from mm if needed (1 inch = 25.4 mm).
- Do NOT guess or fabricate values. Omit any field you cannot confirm from the source.
- For coating, use the manufacturer's coating name (e.g., "TiAlN", "TiCN", "AlTiN", "TiN", "DLC", "uncoated").
- For toolMaterial, use: "Carbide", "HSS", "Cobalt HSS", "Cermet", "Ceramic", or "Tool Steel".
- The confidence field should be "high" if you found a definitive product page, "medium" if specs came from partial sources, "low" if mostly inferred.

RESPONSE FORMAT (JSON only):
{
  "tool_type": "drill|endmill|tap|insert|reamer|holder|boring_bar|countersink|counterbore|thread_mill|face_mill|slitting_saw|chamfer_mill|spot_drill",
  "specs": {
    "cutDiameter": <float inches or null>,
    "overallLength": <float inches or null>,
    "lengthOfCut": <float inches or null>,
    "shankDiameter": <float inches or null>,
    "numberOfFlutes": <int or null>,
    "helixAngle": <float degrees or null>,
    "cornerRadius": <float inches or null>,
    "coating": "<string or null>",
    "toolMaterial": "<string or null>",
    "tipAngle": "<string degrees or null>",
    "throughCoolant": <bool or null>,
    "insertInscribedCircle": "<string fraction like 3/8 or null>",
    "insertThickness": <float inches or null>,
    "insertShape": "<string: triangle, diamond, round, square, trigon, or null>",
    "numberOfCuttingCorners": <int or null>,
    "pitch": "<string mm pitch or null>",
    "fullProfile": <bool or null>,
    "threadsPerInch": "<string or null>",
    "threadType": "<string or null>",
    "centerCutting": "<string Yes/No or null>"
  },
  "brand": {
    "name": "<MANUFACTURER NAME UPPERCASE>",
    "catalog_number": "<manufacturer catalog/model number>",
    "edp": "<EDP number if different from catalog_number>"
  },
  "description_hint": "<short description suitable for a shop tool library>",
  "source_url": "<URL where specs were found>",
  "confidence": "high|medium|low"
}"""


def search_tool_specs(manufacturer, edp, catalog=None):
    """Search the web for tool specs and return structured data.

    Args:
        manufacturer: Manufacturer name (e.g., "iscar", "kennametal")
        edp: EDP or internal product number
        catalog: Optional catalog/model number (e.g., "16ERB 1.25 ISO IC908")

    Returns:
        dict with tool_type, specs, brand, description_hint, source_url, confidence.
        On failure, returns dict with "error" key.
    """
    api_key = get_anthropic_key()
    client = anthropic.Anthropic(api_key=api_key)

    search_term = catalog if catalog else edp
    user_message = (
        f"Find the complete specifications for this cutting tool:\n"
        f"  Manufacturer: {manufacturer}\n"
        f"  {'Catalog Number' if catalog else 'EDP/Product Number'}: {search_term}\n"
    )
    if catalog and edp:
        user_message += f"  EDP: {edp}\n"

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": user_message}],
        )
        return _parse_ai_response(response)
    except anthropic.APIError as e:
        return {"error": f"Anthropic API error: {e}"}
    except Exception as e:
        return {"error": f"Search failed: {e}"}


def _parse_ai_response(response):
    """Extract the JSON spec dict from Claude's response."""
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)

    full_text = "\n".join(text_parts)

    # Try to parse JSON from the response — handle code fences
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', full_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try parsing the entire text as JSON
        json_str = full_text.strip()

    try:
        result = json.loads(json_str)
        if "tool_type" not in result:
            return {"error": "AI response missing tool_type", "raw": full_text}
        return result
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        brace_match = re.search(r'\{.*\}', full_text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        return {"error": "Could not parse AI response as JSON", "raw": full_text}


def map_tool_group(tool_type):
    """Map an AI-determined tool type to a ProShop tool group letter.

    Returns the group letter string, or None if unmapped.
    """
    return TOOL_GROUP_MAP.get(tool_type.lower().strip().replace(" ", "_"))
