"""
Diff Engine — compare Snapshot A vs Snapshot B to produce structured deltas.

Handles three document origin types:
  - toolpath:      Toolpath-generated baseline -> toolpath_delta
  - prior_program: Previous version of same part -> version_delta
  - fresh:         No baseline -> new_baseline (Snapshot B only)

Matches operations by name, compares field-by-field, categorizes changes,
and calculates fidelity score.
"""

# Fields to compare, grouped by category
PASS_FIELDS = [
    "stepover", "stepdown", "finishing_stepover", "finishing_stepdown",
    "finishing_passes", "stock_to_leave", "stock_to_leave_axial",
    "stock_to_leave_radial", "tolerance",
]

FEED_FIELDS = [
    "cutting_feedrate", "entry_feedrate", "exit_feedrate",
    "plunge_feedrate", "ramp_feedrate", "spindle_rpm",
    "surface_speed", "feed_per_tooth", "cutting_feedrate_ipm",
]

LINKING_FIELDS = [
    "ramp_angle", "ramp_type", "entry_type",
    "lead_in_radius", "lead_out_radius",
    "retract_height", "clearance_height",
]

TOOL_FIELDS = [
    "tool_id", "tool_diameter_in", "tool_number",
    "tool_bodyLength_in", "tool_fluteLength_in",
    "tool_numberOfFlutes",
]

# Map of category -> field list
CATEGORIES = {
    "passes": PASS_FIELDS,
    "feeds": FEED_FIELDS,
    "linking": LINKING_FIELDS,
    "tool": TOOL_FIELDS,
}


def _get_nested(data, field):
    """Get a value from nested dict using dot notation or category keys."""
    if data is None:
        return None

    # Check top-level first
    if field in data:
        return data[field]

    # Check nested categories (passes, feeds, linking)
    for cat in ["passes", "feeds", "linking"]:
        sub = data.get(cat)
        if isinstance(sub, dict) and field in sub:
            return sub[field]

    return None


def _values_differ(a, b):
    """Compare two values, treating None as missing."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    # Numeric comparison with tolerance
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) > 1e-6
    except (TypeError, ValueError):
        return str(a) != str(b)


def _categorize_field(field):
    """Determine which category a field belongs to."""
    for cat, fields in CATEGORIES.items():
        if field in fields:
            return cat
    return "other"


def _compare_operations(op_a, op_b):
    """Compare two operations field-by-field.

    Returns list of changes: [{"field": ..., "from": ..., "to": ..., "category": ...}]
    """
    changes = []

    # Compare all tracked fields
    all_fields = PASS_FIELDS + FEED_FIELDS + LINKING_FIELDS + TOOL_FIELDS
    for field in all_fields:
        val_a = _get_nested(op_a, field)
        val_b = _get_nested(op_b, field)

        if _values_differ(val_a, val_b):
            changes.append({
                "field": field,
                "from": val_a,
                "to": val_b,
                "category": _categorize_field(field),
            })

    return changes


def _match_operations(setups_a, setups_b):
    """Match operations between snapshots A and B by name.

    Returns: (matched, added, removed)
      matched: [(op_a, op_b), ...]
      added: [op_b, ...] — in B but not in A
      removed: [op_a, ...] — in A but not in B
    """
    # Build lookup by operation name
    ops_a = {}
    for setup in (setups_a or []):
        for op in setup.get("operations", []):
            name = op.get("name", "")
            if name:
                ops_a[name] = op

    ops_b = {}
    for setup in (setups_b or []):
        for op in setup.get("operations", []):
            name = op.get("name", "")
            if name:
                ops_b[name] = op

    matched = []
    added = []
    removed = []

    # Find matches and additions
    for name, op_b in ops_b.items():
        if name in ops_a:
            matched.append((ops_a[name], op_b))
        else:
            added.append(op_b)

    # Find removals
    for name, op_a in ops_a.items():
        if name not in ops_b:
            removed.append(op_a)

    return matched, added, removed


def _check_reorder(setups_a, setups_b):
    """Check if operation order changed between snapshots."""
    names_a = []
    for setup in (setups_a or []):
        for op in setup.get("operations", []):
            names_a.append(op.get("name", ""))

    names_b = []
    for setup in (setups_b or []):
        for op in setup.get("operations", []):
            names_b.append(op.get("name", ""))

    # Compare order of common operations
    common = [n for n in names_a if n in set(names_b)]
    common_in_b = [n for n in names_b if n in set(names_a)]
    return common != common_in_b


def _check_setup_name_changes(setups_a, setups_b):
    """Detect setup name changes by index."""
    changes = []
    max_idx = max(len(setups_a or []), len(setups_b or []))
    for i in range(max_idx):
        name_a = setups_a[i]["name"] if i < len(setups_a or []) else None
        name_b = setups_b[i]["name"] if i < len(setups_b or []) else None
        if name_a and name_b and name_a != name_b:
            changes.append({"from": name_a, "to": name_b})
    return changes


def compute_diff(snapshot_a, snapshot_b, origin):
    """Compute structured diff between two snapshots.

    Args:
        snapshot_a: Baseline snapshot (may be None for fresh origin)
        snapshot_b: Final snapshot (after post)
        origin: Document origin type

    Returns:
        dict: Structured diff record per the brief's schema
    """
    # Determine diff type from origin
    diff_type_map = {
        "toolpath": "toolpath_delta",
        "prior_program": "version_delta",
        "fresh": "new_baseline",
    }
    diff_type = diff_type_map.get(origin, "unknown")

    # Handle fresh origin — no baseline to compare
    if origin == "fresh" or snapshot_a is None:
        total_ops = 0
        if snapshot_b:
            for setup in snapshot_b.get("setups", []):
                total_ops += len(setup.get("operations", []))
        return {
            "diff_type": diff_type,
            "fidelity_score": None,  # N/A for new baselines
            "delta": {
                "operations_added": [],
                "operations_removed": [],
                "operations_modified": [],
                "operations_reordered": False,
                "setup_names_changed": [],
            },
            "total_operations_a": 0,
            "total_operations_b": total_ops,
        }

    if snapshot_b is None:
        # Post never happened — no diff to compute
        total_ops = 0
        if snapshot_a:
            for setup in snapshot_a.get("setups", []):
                total_ops += len(setup.get("operations", []))
        return {
            "diff_type": "no_post",
            "fidelity_score": None,
            "delta": {
                "operations_added": [],
                "operations_removed": [],
                "operations_modified": [],
                "operations_reordered": False,
                "setup_names_changed": [],
            },
            "total_operations_a": total_ops,
            "total_operations_b": 0,
        }

    setups_a = snapshot_a.get("setups", [])
    setups_b = snapshot_b.get("setups", [])

    # Match operations
    matched, added, removed = _match_operations(setups_a, setups_b)

    # Compare matched operations
    modified = []
    unchanged_count = 0
    for op_a, op_b in matched:
        changes = _compare_operations(op_a, op_b)
        if changes:
            modified.append({
                "operation": op_b.get("name", ""),
                "tool_id": op_b.get("tool_id", ""),
                "changes": changes,
            })
        else:
            unchanged_count += 1

    # Count total operations in final snapshot
    total_final = len(matched) + len(added)

    # Fidelity score
    if total_final > 0:
        fidelity_score = round((unchanged_count / total_final) * 100, 1)
    else:
        fidelity_score = 100.0

    # Check for reordering and setup name changes
    reordered = _check_reorder(setups_a, setups_b)
    setup_name_changes = _check_setup_name_changes(setups_a, setups_b)

    # Build added/removed summaries
    added_summary = [
        {
            "operation": op.get("name", ""),
            "tool_id": op.get("tool_id", ""),
            "type": op.get("type", ""),
        }
        for op in added
    ]
    removed_summary = [
        {
            "operation": op.get("name", ""),
            "tool_id": op.get("tool_id", ""),
            "type": op.get("type", ""),
        }
        for op in removed
    ]

    return {
        "diff_type": diff_type,
        "fidelity_score": fidelity_score,
        "delta": {
            "operations_added": added_summary,
            "operations_removed": removed_summary,
            "operations_modified": modified,
            "operations_reordered": reordered,
            "setup_names_changed": setup_name_changes,
        },
        "total_operations_a": sum(
            len(s.get("operations", [])) for s in setups_a),
        "total_operations_b": total_final,
        "unchanged_count": unchanged_count,
    }
