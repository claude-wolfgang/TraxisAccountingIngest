"""
Manufacturer website scrapers for tool specifications.

Registry pattern — add new scrapers by adding to SCRAPERS dict.
Currently supports: Kennametal

When Claude Code drives the workflow, it can bypass scraping entirely
by passing specs via --specs-json on the CLI. Standalone CLI uses
requests + html.parser as best-effort fallback.
"""

import json
import os
import re
from html.parser import HTMLParser

import requests


class _KennametalSpecParser(HTMLParser):
    """Extract specs from Kennametal product page HTML.

    Kennametal pages embed product data in structured table rows
    with label/value pairs. This parser extracts them.
    """

    def __init__(self):
        super().__init__()
        self._in_spec_label = False
        self._in_spec_value = False
        self._current_label = ""
        self._specs = {}
        self._capture_text = ""
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        # Kennametal uses data attributes and specific class patterns
        if "spec-label" in cls or "attribute-label" in cls:
            self._in_spec_label = True
            self._capture_text = ""
        elif "spec-value" in cls or "attribute-value" in cls:
            self._in_spec_value = True
            self._capture_text = ""

    def handle_data(self, data):
        if self._in_spec_label or self._in_spec_value:
            self._capture_text += data.strip()

    def handle_endtag(self, tag):
        if self._in_spec_label:
            self._current_label = self._capture_text.strip()
            self._in_spec_label = False
        elif self._in_spec_value and self._current_label:
            self._specs[self._current_label] = self._capture_text.strip()
            self._in_spec_value = False
            self._current_label = ""

    @property
    def specs(self):
        return self._specs


def scrape_kennametal(url):
    """Scrape a Kennametal product page for tool specifications.

    Args:
        url: Full URL to a Kennametal product page

    Returns:
        dict with standardized spec keys, or partial dict if scraping
        is incomplete (manufacturer pages change structure over time).
    """
    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return {"error": f"Failed to fetch page: {e}", "url": url}

    # Try structured parsing first
    parser = _KennametalSpecParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    result = {"url": url, "source": "kennametal"}

    # Extract catalog number from URL or page content
    cat_match = re.search(r'B\d{3}A\d{5}[A-Z]+', html)
    if cat_match:
        result["catalog_number"] = cat_match.group(0)

    # Extract grade (e.g., KC7325)
    grade_match = re.search(r'KC\d{4}', html)
    if grade_match:
        result["grade"] = grade_match.group(0)

    # Extract dimensions from page — look for common patterns
    # Kennametal pages often have dimensions in mm with inch equivalents
    dim_patterns = {
        "diameter_mm": [
            r'[Dd]rill\s*[Dd]iameter[^0-9]*?(\d+\.?\d*)\s*mm',
            r'D1[^0-9]*?(\d+\.?\d*)\s*mm',
        ],
        "oal_mm": [
            r'[Oo]verall\s*[Ll]ength[^0-9]*?(\d+\.?\d*)\s*mm',
            r'(?:OAL|L\b)[^0-9]*?(\d+\.?\d*)\s*mm',
        ],
        "flute_length_mm": [
            r'[Ff]lute\s*[Ll]ength[^0-9]*?(\d+\.?\d*)\s*mm',
            r'L3[^0-9]*?(\d+\.?\d*)\s*mm',
        ],
        "shank_diameter_mm": [
            r'[Ss]hank\s*[Dd]iameter[^0-9]*?(\d+\.?\d*)\s*mm',
            r'(?:D|DS)[^0-9]*?(\d+\.?\d*)\s*mm',
        ],
    }

    for key, patterns in dim_patterns.items():
        for pat in patterns:
            match = re.search(pat, html)
            if match:
                result[key] = float(match.group(1))
                # Convert mm to inches
                inch_key = key.replace("_mm", "_inch")
                result[inch_key] = round(float(match.group(1)) / 25.4, 4)
                break

    # Helix angle
    helix_match = re.search(r'[Hh]elix\s*[Aa]ngle[^0-9]*?(\d+)', html)
    if helix_match:
        result["helix_angle"] = float(helix_match.group(1))

    # Coating
    if "TiN-TiAlN" in html or "TiAlN" in html:
        result["coating"] = "TiAlN"
    elif "TiCN" in html:
        result["coating"] = "TiCN"
    elif "TiN" in html:
        result["coating"] = "TiN"

    # Number of flutes (GOdrill is always 2, but check)
    flute_match = re.search(r'(\d)\s*[Ff]lute', html)
    if flute_match:
        result["num_flutes"] = int(flute_match.group(1))

    # Product image URL
    img_match = re.search(r'(https://images\.kennametal\.com/is/image/Kennametal/\d+)', html)
    if img_match:
        result["image_url"] = img_match.group(1)

    # Material number (Kennametal's internal ID)
    mat_match = re.search(r'[Mm]aterial\s*[Nn]umber[^0-9]*?(\d{7})', html)
    if mat_match:
        result["material_number"] = mat_match.group(1)

    return result


# Scraper registry — add new manufacturers here
SCRAPERS = {
    "kennametal": scrape_kennametal,
}


def scrape_manufacturer(manufacturer, url):
    """Route to the appropriate manufacturer scraper.

    Returns spec dict, or empty dict if no scraper exists for this manufacturer.
    """
    scraper = SCRAPERS.get(manufacturer.lower())
    if scraper:
        return scraper(url)
    return {"error": f"No scraper available for '{manufacturer}'", "url": url}


def download_product_image(image_url, save_path):
    """Download a product image for manual ProShop upload.

    Returns the saved file path, or None on failure.
    """
    try:
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return save_path
    except Exception as e:
        print(f"Failed to download image: {e}")
        return None
