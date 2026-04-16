"""
Shop-convention tool description builder and PREV note formatter.

Description format example:
    #29(.1360)3xD DR 2FL 25/32" F/L KENNA GODRILL KC7325

PREV note format:
    PREV: GARR 1205H EDP#89321 #29 5xD 2FL 135pt Hardlube OAL 2.5 F/L 1.375 Shank .136
"""

# Coating names → ProShop enum values
COATING_MAP = {
    "tialn": "TIALN",
    "tialn": "TIALN",
    "tin-tialn": "TIALN",
    "ticn": "TICN",
    "tin": "OTHER",
    "altin": "TIALN",
    "dlc": "OTHER",
    "uncoated": "OTHER",
    "none": "OTHER",
    "hardlube": "OTHER",
    "balinit hardlube": "OTHER",
    "c7": "C7",
    "c11": "C11",
}

# Short manufacturer names for descriptions
MFG_SHORT = {
    "kennametal": "KENNA",
    "garr": "GARR",
    "harvey": "HARVEY",
    "osg": "OSG",
    "sandvik": "SANDVIK",
    "iscar": "ISCAR",
    "seco": "SECO",
    "guhring": "GUHRING",
    "mitsubishi": "MITSU",
    "nachi": "NACHI",
    "emuge": "EMUGE",
}


def inch_to_fraction(value, tolerance=0.005):
    """Convert decimal inches to nearest common fraction string.

    Returns fractional string like '25/32"' or None if no close match.
    """
    fractions = [
        (1, 64), (1, 32), (3, 64), (1, 16), (5, 64), (3, 32), (7, 64),
        (1, 8), (9, 64), (5, 32), (11, 64), (3, 16), (13, 64), (7, 32),
        (15, 64), (1, 4), (17, 64), (9, 32), (19, 64), (5, 16), (21, 64),
        (11, 32), (23, 64), (3, 8), (25, 64), (13, 32), (27, 64), (7, 16),
        (29, 64), (15, 32), (31, 64), (1, 2), (33, 64), (17, 32), (35, 64),
        (9, 16), (37, 64), (19, 32), (39, 64), (5, 8), (41, 64), (21, 32),
        (43, 64), (11, 16), (45, 64), (23, 32), (47, 64), (3, 4), (49, 64),
        (25, 32), (51, 64), (13, 16), (53, 64), (27, 32), (55, 64), (7, 8),
        (57, 64), (29, 32), (59, 64), (15, 16), (61, 64), (31, 32), (63, 64),
        (1, 1),
    ]
    for num, den in fractions:
        frac_val = num / den
        if abs(value - frac_val) < tolerance:
            if den == 1:
                return f'{num}"'
            # Simplify
            from math import gcd
            g = gcd(num, den)
            return f'{num // g}/{den // g}"'
    return None


def format_drill_description(
    size_name,
    diameter_inch,
    depth_ratio,
    num_flutes,
    flute_length_inch,
    manufacturer,
    product_line,
    grade,
):
    """Build a drill description in shop convention format.

    Example: #29(.1360)3xD DR 2FL 25/32" F/L KENNA GODRILL KC7325
    """
    # Diameter string
    dia_str = f".{diameter_inch:.4f}"[1:]  # .1360

    # Flute length as fraction
    fl_frac = inch_to_fraction(flute_length_inch)
    fl_str = fl_frac if fl_frac else f'{flute_length_inch:.3f}"'

    # Manufacturer short name
    mfg_short = MFG_SHORT.get(manufacturer.lower(), manufacturer.upper()[:6])

    parts = [
        f"{size_name}({dia_str})",
        f"{depth_ratio} DR",
        f"{num_flutes}FL",
        f'{fl_str} F/L',
        mfg_short,
        product_line.upper(),
        grade.upper(),
    ]
    return " ".join(parts)


def map_coating(coating_name):
    """Map a manufacturer coating name to ProShop enum value."""
    return COATING_MAP.get(coating_name.lower().strip(), "OTHER")


def build_prev_note(tool):
    """Build a PREV: line from an existing tool record dict.

    Format: PREV: GARR 1205H EDP#89321 #29 5xD 2FL 135pt Hardlube OAL 2.5 F/L 1.375 Shank .136
    """
    brands = tool.get("approvedBrands", {}).get("records", [])
    brand_name = brands[0].get("approvedBrand", "?") if brands else "?"
    edp = brands[0].get("vendorToolId", "?") if brands else "?"

    desc = tool.get("description", "")
    size = tool.get("size", "")
    oal = tool.get("overallLength", "")
    fl = tool.get("lengthOfCut", "")
    shank = tool.get("shankDiameter", "")

    # Extract key info from description for the PREV note
    parts = [f"PREV: {brand_name}"]
    if edp and edp != "?":
        parts.append(f"EDP#{edp}")
    if size:
        parts.append(size)
    # Try to extract depth ratio from description (e.g., "5xD")
    import re
    depth_match = re.search(r'(\d+x[Dd])', desc)
    if depth_match:
        parts.append(depth_match.group(1))
    # Flutes
    flute_match = re.search(r'(\d+)FL', desc, re.IGNORECASE)
    if flute_match:
        parts.append(f"{flute_match.group(1)}FL")
    # Point angle
    tip = tool.get("tipAngle", "")
    if tip:
        parts.append(f"{tip}pt")
    # Coating from description
    coating_desc = tool.get("coating", "")
    if coating_desc and coating_desc.lower() not in ("n", "other", ""):
        parts.append(coating_desc)
    elif "HLUBE" in desc.upper() or "HARDLUBE" in desc.upper():
        parts.append("Hardlube")

    parts.append(f"OAL {oal}")
    parts.append(f"F/L {fl}")
    parts.append(f"Shank {shank}")

    return " ".join(str(p) for p in parts)


def append_to_purchasing_notes(existing_notes, prev_note):
    """Append PREV note to existing purchasing notes without overwriting.

    Uses ' | ' as separator. Preserves all existing content including
    kiosk notes, line breaks, etc.
    """
    existing = (existing_notes or "").strip()
    if not existing:
        return prev_note

    # Check if there's already a PREV note (avoid duplicating)
    if "PREV:" in existing:
        return existing

    # Find the first line/sentence to append after
    # If there are newlines (kiosk notes etc.), insert before them
    lines = existing.split("\n")
    if len(lines) > 1:
        # Append PREV to first line, keep remaining lines
        lines[0] = f"{lines[0]} | {prev_note}"
        return "\n".join(lines)
    else:
        return f"{existing} | {prev_note}"
