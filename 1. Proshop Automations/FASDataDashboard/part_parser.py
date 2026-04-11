"""
Part number extraction from CNC program comments.

Traxis part number formats:
  - 3847-C    (number + dash + letter revision)
  - 3847      (number only, typically 4-5 digits)
  - PN-3847-C (prefixed with PN- or PN:)
  - 10983     (5-digit, newer numbering)
"""

import re

# Pattern: optional PN prefix, then 4-5 digit number, optional dash+letter revision
_PART_RE = re.compile(
    r"(?:PN[-:])?(\d{4,5})(-[A-Z]{1,3})?",
    re.IGNORECASE,
)

# Words that, if immediately before a number, mean it's NOT a part number
_SKIP_PREFIXES = {"OP", "TOOL", "RPM", "FEED", "SPEED", "SUB", "MAIN", "T", "N", "O"}


def extract_part_number(comment: str | None) -> str | None:
    """
    Extract part number from CNC program comment.

    Args:
        comment: Raw comment string (with or without parentheses).

    Returns:
        Part number string (e.g. "3847-C") or None if not found.

    Examples:
        "(3847-C FINISH MILL)" -> "3847-C"
        "PN-3847 OP20"         -> "3847"
        "ROUGH CYCLE"          -> None
        "10983 P1 v21"         -> "10983"
    """
    if not comment:
        return None

    text = comment.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    if not text:
        return None

    for match in _PART_RE.finditer(text):
        number = match.group(1)
        revision = match.group(2) or ""

        # Check if preceded by a skip word (e.g. OP20, TOOL1234)
        start = match.start()
        if start > 0:
            before = text[:start].rstrip("-: ")
            prefix_word = before.split()[-1].upper() if before else ""
            if prefix_word in _SKIP_PREFIXES:
                continue

        return number + revision.upper()

    return None


if __name__ == "__main__":
    # Quick self-test
    tests = [
        ("(3847-C FINISH MILL)", "3847-C"),
        ("3847-C FINISH MILL", "3847-C"),
        ("PN-3847 OP20", "3847"),
        ("PN:10983-AB OP20 FINISH", "10983-AB"),
        ("ROUGH CYCLE", None),
        ("10983 P1 v21", "10983"),
        ("(OP20 3847-C)", "3847-C"),
        ("", None),
        (None, None),
        ("(FINISH MILL)", None),
        ("(3847-C)", "3847-C"),
        ("O1234 (3847 FINISH)", "3847"),
    ]
    passed = 0
    for comment, expected in tests:
        result = extract_part_number(comment)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            print(f"  {status}: extract_part_number({comment!r}) = {result!r}, expected {expected!r}")
        else:
            passed += 1
    print(f"{passed}/{len(tests)} tests passed")
