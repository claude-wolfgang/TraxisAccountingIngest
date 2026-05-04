"""Lookup helper for vendor_map.json.

Match a scraped vendor name (e.g. "DB Roberts" or "Hadco Metal LLC")
against the bootstrapped vendor_map and return the default contact email
plus the rep's first name (for personalized email greetings).
"""

import json
import re
from pathlib import Path

VENDOR_MAP_PATH = (
    Path(__file__).resolve().parents[3]
    / "35. Purchasing Automation"
    / "vendor_map.json"
)


def load_map():
    with open(VENDOR_MAP_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Strip top-level meta keys (those starting with _)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _normalize(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def find(scraped_name):
    """Return (vendor_entry, domain) for a scraped vendor name, or (None, None).

    Match strategy: normalize both sides (strip non-alphanum, lowercase),
    then check if the scraped name appears in the vendor's `name` or
    domain. Best-effort fuzzy — no external libs.
    """
    if not scraped_name:
        return None, None
    needle = _normalize(scraped_name)
    if not needle:
        return None, None

    vmap = load_map()
    for domain, entry in vmap.items():
        name_norm = _normalize(entry.get("name", ""))
        domain_norm = _normalize(domain)
        if needle in name_norm or name_norm in needle:
            return entry, domain
        if needle in domain_norm:
            return entry, domain
    return None, None


def default_email(vendor_entry):
    return vendor_entry.get("default") if vendor_entry else None


GENERIC_LOCALS = {
    "sales", "orders", "info", "support", "ar", "ap", "purchasing",
    "service", "invoice", "invoices", "noreply", "accounting", "billing",
    "contact", "hello", "admin", "office",
}


def first_name_of(email):
    """Best-effort first-name extraction from a sales-rep address.
    Only confident when local part has a dot ('jaime.gomez@x' -> 'Jaime').
    Returns '' for generic mailboxes or when split is ambiguous — caller
    should fall back to a no-name greeting in that case.
    """
    if not email or "@" not in email:
        return ""
    local = email.split("@", 1)[0].lower()
    if local in GENERIC_LOCALS:
        return ""
    # Generic dotted addresses: skip if first segment is a known generic
    if "." in local:
        first = local.split(".", 1)[0]
        if first in GENERIC_LOCALS:
            return ""
        return first[:1].upper() + first[1:]
    # No dot — can't reliably split (e.g. lrobinson, briannab) so skip
    return ""
