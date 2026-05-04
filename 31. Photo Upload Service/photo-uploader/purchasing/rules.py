"""Auto-approve rule evaluation for the P35 purchasing queue.

Resolution order per field: items[id] -> categories[cat] -> defaults.
A field set on the item-level overrides only that field; everything else
falls through.

Phase 1 only honors `amount_threshold`. Phase 2 will add `min_interval_days`
once Selenium can scrape ProShop for the last-ordered date per item.
"""

import json
from pathlib import Path

RULES_PATH = Path(__file__).parent / "rules.json"


def load_rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve(rules, entity_id):
    """Walk item -> category -> defaults; return the merged effective rule."""
    defaults = rules.get("defaults", {})
    cats = rules.get("categories", {})
    items = rules.get("items", {})

    item_rule = items.get(entity_id, {})
    cat_name = item_rule.get("category")
    cat_rule = cats.get(cat_name, {}) if cat_name else {}

    return {
        "amount_threshold": item_rule.get("amount_threshold",
                            cat_rule.get("amount_threshold",
                            defaults.get("amount_threshold", 0))),
        "min_interval_days": item_rule.get("min_interval_days",
                             cat_rule.get("min_interval_days",
                             defaults.get("min_interval_days", 0))),
        "category": cat_name,
        "notes": item_rule.get("notes", ""),
    }


def should_auto_approve(entity_id, qty, unit_cost, rules=None):
    """Phase 1 evaluation.

    Returns (auto_approve: bool, reason: str). Reason is human-readable —
    surfaced in the queue row so Wolfgang knows why it auto-fired or why
    it was held.
    """
    rules = rules or load_rules()
    rule = resolve(rules, entity_id)

    if unit_cost is None:
        return False, "no unit_cost on page — manual review required"

    try:
        total = float(qty) * float(unit_cost)
    except (TypeError, ValueError):
        return False, "qty or unit_cost not numeric"

    threshold = rule["amount_threshold"]
    if threshold <= 0:
        return False, "no auto-approve threshold configured (defaults to manual)"

    if total <= threshold:
        return True, f"total ${total:.2f} <= threshold ${threshold:.2f}"
    return False, f"total ${total:.2f} > threshold ${threshold:.2f} — manual review"
