"""
Pattern Accumulator — reads diff records, finds recurring corrections,
and generates writeback candidates for the Fusion tool library.

Scans all *_diff.jsonl files in the diffs directory. Aggregates corrections
by (field, tool_id, operation_type, material). When confidence threshold
is reached, promotes to writeback_candidates.jsonl.

Confidence levels:
  - low:    < 3 occurrences — log only
  - medium: 3-6 occurrences — flag for review
  - high:   > 6 occurrences — approved for tool library preset update

Runs after each session close via io_worker.
"""

import os
import json
import glob
from collections import defaultdict
from datetime import datetime

from tc_config import get_output_dir


def _log(msg):
    try:
        import adsk.core
        adsk.core.Application.get().log(
            f"[TraxisCapture:Patterns] {msg}")
    except Exception:
        pass


def _read_all_diffs(diffs_dir):
    """Read all diff JSONL files from the output directory.

    Returns list of diff records.
    """
    records = []
    pattern = os.path.join(diffs_dir, "*_diff.jsonl")
    for filepath in glob.glob(pattern):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            continue
    return records


def _extract_corrections(record):
    """Extract individual field corrections from a diff record.

    Returns list of correction dicts:
    [{
        "field": "passes.stepover",
        "from_value": 0.4,
        "to_value": 0.25,
        "tool_id": "1/2 4FL EM",
        "operation_type": "adaptive2d",
        "part": "TRA1-TEMP",
        "session_id": "2026-03-03_abc123",
        "origin": "toolpath",
    }]
    """
    corrections = []

    diff = record.get("diff", {})
    delta = diff.get("delta", {})
    origin = record.get("origin", "unknown")

    # Only toolpath and prior_program have meaningful corrections
    if origin not in ("toolpath", "prior_program"):
        return corrections

    part = record.get("document", "")
    session_id = record.get("session_id", "")

    for mod in delta.get("operations_modified", []):
        op_name = mod.get("operation", "")
        tool_id = mod.get("tool_id", "")

        # Try to determine operation type from snapshot data
        op_type = _find_op_type(record, op_name)

        for change in mod.get("changes", []):
            field = change.get("field", "")
            from_val = change.get("from")
            to_val = change.get("to")
            category = change.get("category", "other")

            corrections.append({
                "field": field,
                "category": category,
                "from_value": from_val,
                "to_value": to_val,
                "tool_id": tool_id,
                "operation_type": op_type,
                "part": part,
                "session_id": session_id,
                "origin": origin,
            })

    return corrections


def _find_op_type(record, op_name):
    """Find operation type from snapshot data."""
    for key in ("snapshot_b", "snapshot_a"):
        snapshot = record.get(key)
        if not snapshot:
            continue
        for setup in snapshot.get("setups", []):
            for op in setup.get("operations", []):
                if op.get("name") == op_name:
                    return op.get("type", "unknown")
    return "unknown"


def _get_confidence(count):
    """Determine confidence level from occurrence count."""
    if count >= 7:
        return "high"
    elif count >= 3:
        return "medium"
    else:
        return "low"


def accumulate_patterns():
    """Main accumulation routine.

    Reads all diffs, aggregates corrections, updates patterns.jsonl,
    and generates writeback_candidates.jsonl for medium+ confidence.
    """
    diffs_dir = get_output_dir()
    records = _read_all_diffs(diffs_dir)

    if not records:
        return

    # Aggregate corrections by (field, tool_id, operation_type)
    # Key: (field, tool_id, operation_type)
    # Value: list of correction instances
    aggregated = defaultdict(list)

    for record in records:
        corrections = _extract_corrections(record)
        for corr in corrections:
            key = (
                corr["field"],
                corr["tool_id"],
                corr["operation_type"],
            )
            aggregated[key].append(corr)

    # Build pattern records
    patterns = []
    writeback_candidates = []

    for key, instances in aggregated.items():
        field, tool_id, op_type = key
        count = len(instances)
        confidence = _get_confidence(count)

        # Determine the most common "to" value (what programmers correct to)
        to_values = defaultdict(int)
        from_values = defaultdict(int)
        jobs = set()
        for inst in instances:
            to_val = inst.get("to_value")
            from_val = inst.get("from_value")
            if to_val is not None:
                to_values[str(to_val)] += 1
            if from_val is not None:
                from_values[str(from_val)] += 1
            jobs.add(inst.get("part", ""))

        # Most common target value
        if to_values:
            programmer_value = max(to_values, key=to_values.get)
        else:
            programmer_value = None

        if from_values:
            toolpath_value = max(from_values, key=from_values.get)
        else:
            toolpath_value = None

        # Generate pattern ID
        pattern_id = _make_pattern_id(field, tool_id, op_type)

        pattern = {
            "pattern_id": pattern_id,
            "field": field,
            "tool_id": tool_id,
            "operation_type": op_type,
            "material": None,  # populated from ProShop lookup in future
            "toolpath_value": toolpath_value,
            "programmer_value": programmer_value,
            "occurrences": count,
            "jobs": sorted(jobs),
            "confidence": confidence,
            "last_seen": max(
                inst.get("session_id", "") for inst in instances),
        }
        patterns.append(pattern)

        # Medium+ confidence -> writeback candidate
        if confidence in ("medium", "high"):
            candidate = {
                "tool_id": tool_id,
                "tool_library": None,  # determined at writeback time
                "preset_field": field,
                "current_value": toolpath_value,
                "proposed_value": programmer_value,
                "confidence": confidence,
                "evidence_jobs": sorted(jobs),
                "occurrences": count,
                "status": "pending_approval",
                "pattern_id": pattern_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            writeback_candidates.append(candidate)

    # Write patterns.jsonl (full rewrite)
    patterns_path = os.path.join(diffs_dir, "patterns.jsonl")
    try:
        with open(patterns_path, 'w', encoding='utf-8') as f:
            for p in sorted(patterns, key=lambda x: -x["occurrences"]):
                f.write(json.dumps(p, default=str) + "\n")
        _log(f"Patterns updated: {len(patterns)} patterns")
    except Exception as e:
        _log(f"Error writing patterns: {e}")

    # Write writeback_candidates.jsonl
    # Preserve existing approved/written statuses
    candidates_path = os.path.join(diffs_dir, "writeback_candidates.jsonl")
    existing_statuses = _read_existing_statuses(candidates_path)

    try:
        with open(candidates_path, 'w', encoding='utf-8') as f:
            for c in writeback_candidates:
                # Preserve approved/written status from previous runs
                pid = c.get("pattern_id", "")
                if pid in existing_statuses:
                    prev = existing_statuses[pid]
                    if prev in ("approved", "written"):
                        c["status"] = prev
                f.write(json.dumps(c, default=str) + "\n")
        _log(f"Writeback candidates: {len(writeback_candidates)}")
    except Exception as e:
        _log(f"Error writing candidates: {e}")

    return patterns


def _make_pattern_id(field, tool_id, op_type):
    """Generate a deterministic pattern ID."""
    import re
    parts = [
        re.sub(r'[^a-z0-9]', '_', field.lower()),
        re.sub(r'[^a-z0-9]', '_', (tool_id or "").lower()),
        re.sub(r'[^a-z0-9]', '_', (op_type or "").lower()),
    ]
    return "_".join(p for p in parts if p)


def _read_existing_statuses(candidates_path):
    """Read existing candidate statuses to preserve approved/written."""
    statuses = {}
    if not os.path.isfile(candidates_path):
        return statuses
    try:
        with open(candidates_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    pid = rec.get("pattern_id", "")
                    status = rec.get("status", "")
                    if pid and status:
                        statuses[pid] = status
    except Exception:
        pass
    return statuses
