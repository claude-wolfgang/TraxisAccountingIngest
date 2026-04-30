"""
Shop-convention tool description builder, PREV note formatter, and enum mappings.

Description format examples:
    Drill:  #29(.1360)3xD DR 2FL 25/32" F/L KENNA GODRILL KC7325
    Endmill: 1/2" 4FL 1" F/L EM ISCAR TIALN
    Insert: 16ERB 1.25 ISO Threading Insert ISCAR IC908
    Tap:    1/4-20 3FL FORM TAP EMUGE TIALN

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
    "walter": "WALTER",
    "kyocera": "KYOCERA",
    "widia": "WIDIA",
    "ingersoll": "INGER",
    "yg-1": "YG-1",
    "dormer pramet": "DORMER",
}

# Tool material names → ProShop enum values
MATERIAL_MAP = {
    "carbide": "CARB",
    "solid carbide": "CARB",
    "cemented carbide": "CARB",
    "hss": "HSS",
    "high speed steel": "HSS",
    "cobalt": "COBALT",
    "cobalt hss": "COBALT",
    "hss-co": "COBALT",
    "hss cobalt": "COBALT",
    "cermet": "OTHER",
    "ceramic": "OTHER",
    "cbn": "OTHER",
    "pcd": "OTHER",
    "tool steel": "TOOL_ST",
}

# Insert inscribed circle → ProShop enum values
INSCRIBED_CIRCLE_MAP = {
    "1/2": "_12",
    "0.5": "_12",
    "12.7": "_12",
    "1/4": "_14",
    "0.25": "_14",
    "6.35": "_14",
    "3/8": "_38",
    "0.375": "_38",
    "9.53": "_38",
    "5/16": "_516",
    "0.3125": "_516",
    "7.94": "_516",
    "5mm": "_5MM",
    "5": "_5MM",
}

# Insert shape → ProShop enum values
INSERT_SHAPE_MAP = {
    "triangle": "T",
    "trigon": "T",
    "triangular": "T",
    "diamond": "C",
    "rhombic": "C",
    "80": "C",
    "square": "W",
    "round": "OTHER",
    "pentagon": "OTHER",
    "hexagon": "OTHER",
    "octagon": "OTHER",
}


def map_material(material_name):
    """Map a manufacturer material name to ProShop enum value."""
    if not material_name:
        return None
    return MATERIAL_MAP.get(material_name.lower().strip(), "OTHER")


def map_inscribed_circle(ic_value):
    """Map an inscribed circle value to ProShop enum value."""
    if not ic_value:
        return None
    val = str(ic_value).strip().rstrip('"').rstrip("mm").strip()
    return INSCRIBED_CIRCLE_MAP.get(val, "OTHER")


def map_insert_shape(shape_name):
    """Map an insert shape name to ProShop enum value."""
    if not shape_name:
        return None
    return INSERT_SHAPE_MAP.get(shape_name.lower().strip(), "OTHER")


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
    mfg_short = MFG_SHORT.get(manufacturer.lower(), manufacturer.upper()[:6])

    parts = []
    if size_name and diameter_inch:
        dia_str = f".{diameter_inch:.4f}"[1:]
        parts.append(f"{size_name}({dia_str})")
    elif diameter_inch:
        dia_frac = inch_to_fraction(diameter_inch)
        parts.append(dia_frac if dia_frac else f'{diameter_inch:.4f}"')
    if depth_ratio:
        parts.append(f"{depth_ratio} DR")
    else:
        parts.append("DR")
    if num_flutes:
        parts.append(f"{int(num_flutes)}FL")
    if flute_length_inch:
        fl_frac = inch_to_fraction(flute_length_inch)
        fl_str = fl_frac if fl_frac else f'{flute_length_inch:.3f}"'
        parts.append(f"{fl_str} F/L")
    parts.append(mfg_short)
    if product_line:
        parts.append(product_line.upper())
    if grade:
        parts.append(grade.upper())
    return " ".join(parts)


def format_endmill_description(diameter_inch, num_flutes, flute_length_inch,
                               manufacturer, coating=None, corner_radius=None):
    """Build an endmill description in shop convention format."""
    dia_frac = inch_to_fraction(diameter_inch) if diameter_inch else None
    dia_str = dia_frac if dia_frac else (f'{diameter_inch:.4f}"' if diameter_inch else "?")

    fl_frac = inch_to_fraction(flute_length_inch) if flute_length_inch else None
    fl_str = fl_frac if fl_frac else (f'{flute_length_inch:.3f}"' if flute_length_inch else "?")

    mfg_short = MFG_SHORT.get(manufacturer.lower(), manufacturer.upper()[:6])

    parts = [dia_str]
    if num_flutes:
        parts.append(f"{int(num_flutes)}FL")
    parts.append(f"{fl_str} F/L EM")
    if corner_radius:
        parts.append(f"CR{corner_radius:.3f}")
    parts.append(mfg_short)
    if coating and coating.upper() not in ("OTHER", "NONE", "UNCOATED"):
        parts.append(coating.upper())
    return " ".join(parts)


def format_insert_description(catalog_number, manufacturer, grade=None,
                              description_hint=None):
    """Build an insert description in shop convention format.

    Example: 16ERB 1.25 ISO IC908 Threading Insert ISCAR
    """
    mfg_short = MFG_SHORT.get(manufacturer.lower(), manufacturer.upper()[:6])
    parts = [catalog_number or "INSERT"]
    if description_hint and not catalog_number:
        parts = [description_hint]
    if mfg_short not in " ".join(parts).upper():
        parts.append(mfg_short)
    if grade and grade.upper() not in " ".join(parts).upper():
        parts.append(grade.upper())
    return " ".join(parts)


def format_tap_description(size_str, pitch_or_tpi, num_flutes, manufacturer,
                           coating=None, tap_type=None):
    """Build a tap description in shop convention format."""
    mfg_short = MFG_SHORT.get(manufacturer.lower(), manufacturer.upper()[:6])
    parts = [size_str or "?"]
    if pitch_or_tpi:
        parts[0] = f"{size_str}-{pitch_or_tpi}"
    if num_flutes:
        parts.append(f"{int(num_flutes)}FL")
    parts.append(tap_type.upper() if tap_type else "TAP")
    parts.append(mfg_short)
    if coating and coating.upper() not in ("OTHER", "NONE", "UNCOATED"):
        parts.append(coating.upper())
    return " ".join(parts)


def build_description(tool_type, specs, manufacturer):
    """Router — pick the right description formatter based on tool type."""
    s = specs or {}
    coating = s.get("coating")

    if tool_type == "endmill":
        return format_endmill_description(
            s.get("cutDiameter"), s.get("numberOfFlutes"),
            s.get("lengthOfCut"), manufacturer, coating,
            s.get("cornerRadius"),
        )
    elif tool_type in ("insert", "threading_insert"):
        brand = s.get("_brand", {})
        return format_insert_description(
            brand.get("catalog_number"), manufacturer,
            grade=None, description_hint=s.get("_description_hint"),
        )
    elif tool_type == "tap":
        return format_tap_description(
            s.get("_size_str"), s.get("pitch") or s.get("threadsPerInch"),
            s.get("numberOfFlutes"), manufacturer, coating,
            s.get("_tap_type"),
        )
    elif tool_type == "drill":
        return format_drill_description(
            s.get("_size_name", ""),
            s.get("cutDiameter", 0),
            s.get("_depth_ratio", ""),
            s.get("numberOfFlutes", 2),
            s.get("lengthOfCut", 0),
            manufacturer,
            s.get("_product_line", ""),
            s.get("_grade", ""),
        )
    else:
        # Generic fallback
        parts = []
        brand = s.get("_brand", {})
        hint = s.get("_description_hint")
        if hint:
            parts.append(hint)
        elif brand.get("catalog_number"):
            parts.append(brand["catalog_number"])
        mfg_short = MFG_SHORT.get(manufacturer.lower(), manufacturer.upper()[:6])
        if mfg_short not in " ".join(parts).upper():
            parts.append(mfg_short)
        if coating and coating.upper() not in ("OTHER", "NONE", "UNCOATED"):
            parts.append(coating.upper())
        return " ".join(parts) if parts else f"Tool {manufacturer.upper()}"


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
