"""
Naming Enforcer — silently rename setups to PART:OP convention.

Pattern: ^[A-Z0-9_-]+:\d+$  (e.g. TRA1-TEMP:60)

Part number is derived from the document name using the same regex
patterns as TraxisPostProcessor. Setup renaming happens silently
with no user-facing prompts or dialogs.
"""

import adsk.core
import adsk.cam
import re

from tc_config import (
    get_naming_pattern, get_part_number_patterns,
    get_op_start, get_op_increment, get_skip_keywords,
)


def _log(msg):
    try:
        adsk.core.Application.get().log(f"[TraxisCapture:Naming] {msg}")
    except Exception:
        pass


def get_part_number_from_doc(document):
    """Detect part number from document attributes or filename.

    Priority:
    1. Document attribute 'Traxis:PartNumber'
    2. Document attribute 'TraxisCapture:part_number'
    3. Parse from document name via regex patterns
    """
    # Check Traxis attribute (set by TraxisPostProcessor)
    try:
        attr = document.attributes.itemByName('Traxis', 'PartNumber')
        if attr and attr.value:
            return attr.value
    except Exception:
        pass

    # Check TraxisCapture attribute
    try:
        attr = document.attributes.itemByName('TraxisCapture', 'part_number')
        if attr and attr.value:
            return attr.value
    except Exception:
        pass

    # Parse from document name
    try:
        name = document.name or ""
        for pattern in get_part_number_patterns():
            match = pattern.match(name)
            if match:
                return match.group(1).upper()
    except Exception:
        pass

    return None


def derive_conforming_name(setup, part_number, op_number):
    """Build a conforming name: PART:OP (e.g. TRA1-TEMP:60)."""
    if not part_number:
        return None
    return f"{part_number}:{op_number}"


def enforce_naming(cam, document):
    """Check all setups and silently rename any that don't conform.

    Returns list of corrections made: [{"from": old, "to": new}, ...]
    """
    if cam is None:
        return []

    pattern = get_naming_pattern()
    part_number = get_part_number_from_doc(document)
    if not part_number:
        _log("No part number detected — skipping naming enforcement")
        return []

    skip_kw = get_skip_keywords()
    corrections = []
    part_op_index = 0

    for i in range(cam.setups.count):
        setup = cam.setups.item(i)
        name_lower = setup.name.lower()

        # Skip fixture/non-part setups
        if any(kw in name_lower for kw in skip_kw):
            continue

        part_op_index += 1
        op_number = get_op_start() + (part_op_index - 1) * get_op_increment()

        if pattern.match(setup.name):
            continue  # Already conforming

        original = setup.name
        corrected = derive_conforming_name(setup, part_number, op_number)
        if corrected is None:
            continue

        try:
            setup.name = corrected
            corrections.append({"from": original, "to": corrected})
            _log(f"Renamed '{original}' -> '{corrected}'")
        except Exception as e:
            _log(f"Could not rename '{original}': {e}")

    # Save part number for future use
    if part_number and corrections:
        try:
            document.attributes.add(
                'TraxisCapture', 'part_number', part_number)
        except Exception:
            pass

    return corrections
