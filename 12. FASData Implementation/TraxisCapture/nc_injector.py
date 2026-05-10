"""
NC Injector — post-process NC files to inject CAPTURE tags after SEQ headers.

After Fusion's post-processor completes, this module locates the output NC
file and injects CAPTURE metadata tags. This approach survives post-processor
updates and works with ANY post — no .cps modifications needed.

CAPTURE tags injected after each SEQ header block:
  (CAPTURE:SESSION=2026-03-03_abc123)
  (CAPTURE:OP_ID=adaptive2d_001)
  (CAPTURE:TOOL_ID=1-2FL-EM)

FocasMonitor parses these via Focas.ParseCaptureTags() when the machine
executes the corresponding block.
"""

import os
import re
import glob


def _log(msg):
    try:
        import adsk.core
        adsk.core.Application.get().log(f"[TraxisCapture:NCInject] {msg}")
    except Exception:
        pass


# Pattern to identify SEQ header lines:
#   (SEQ # TOOL_DESC T# OOH #.#### HOLDER holder_desc ...)
SEQ_PATTERN = re.compile(r'^\(SEQ\s+', re.IGNORECASE)


def build_capture_block(session_id, op_id, tool_id,
                        extra_tags=None):
    """Build CAPTURE tag lines for injection.

    Args:
        session_id: Programming session identifier
        op_id: Operation identifier (e.g. "adaptive2d_001")
        tool_id: Tool identifier (e.g. "1-2FL-EM")
        extra_tags: Optional dict of additional tag key-value pairs

    Returns:
        list of strings (lines to inject)
    """
    lines = [
        f"(CAPTURE:SESSION={session_id})",
        f"(CAPTURE:OP_ID={op_id})",
        f"(CAPTURE:TOOL_ID={tool_id})",
    ]
    if extra_tags:
        for key, value in extra_tags.items():
            lines.append(f"(CAPTURE:{key}={value})")
    return lines


def _make_op_id(op_data):
    """Create an operation ID from operation data."""
    op_type = op_data.get("type", "unknown")
    seq = op_data.get("sequence", 0)
    # Clean the type string for use in ID
    clean_type = re.sub(r'[^a-zA-Z0-9_]', '', str(op_type))
    return f"{clean_type}_{seq:03d}"


def _make_tool_id(op_data):
    """Create a tool ID from operation data."""
    tid = op_data.get("tool_id") or op_data.get("tool_description", "")
    if tid:
        # Replace spaces with hyphens, remove problematic chars
        return re.sub(r'[^a-zA-Z0-9_/-]', '-', str(tid)).strip('-')
    return f"T{op_data.get('tool_number', 0)}"


def inject_capture_tags(nc_file_path, session_id, snapshot_b):
    """Inject CAPTURE tags into an NC file after SEQ header blocks.

    Args:
        nc_file_path: Path to the NC file to modify
        session_id: Programming session ID
        snapshot_b: The post-completion snapshot (for operation data)

    Returns:
        int: Number of CAPTURE blocks injected
    """
    if not os.path.isfile(nc_file_path):
        _log(f"NC file not found: {nc_file_path}")
        return 0

    try:
        with open(nc_file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        _log(f"Could not read NC file: {e}")
        return 0

    # Build a lookup of operations by sequence for tag data
    op_lookup = {}
    if snapshot_b and "setups" in snapshot_b:
        for setup in snapshot_b["setups"]:
            for op in setup.get("operations", []):
                seq = op.get("sequence", 0)
                op_lookup[seq] = op

    # Find SEQ lines and inject after them
    new_lines = []
    injected = 0
    seq_counter = 0

    for line in lines:
        new_lines.append(line)

        if SEQ_PATTERN.match(line.strip()):
            # Found a SEQ header — inject CAPTURE block after it
            op_data = op_lookup.get(seq_counter, {})
            op_id = _make_op_id(op_data) if op_data else f"seq_{seq_counter:03d}"
            tool_id = _make_tool_id(op_data) if op_data else f"T{seq_counter}"

            # Build extra tags from snapshot data
            extra = {}
            if op_data:
                passes = op_data.get("passes", {})
                feeds = op_data.get("feeds", {})
                if passes.get("stepover") is not None:
                    extra["TOOLPATH_STEPOVER"] = f"{passes['stepover']:.4f}"
                if feeds.get("spindle_rpm") is not None:
                    extra["SPINDLE_RPM"] = f"{feeds['spindle_rpm']}"
                if feeds.get("cutting_feedrate_ipm") is not None:
                    extra["FEED_IPM"] = f"{feeds['cutting_feedrate_ipm']:.1f}"

            capture_lines = build_capture_block(
                session_id, op_id, tool_id, extra if extra else None)
            for cl in capture_lines:
                new_lines.append(cl + "\n")

            injected += 1
            seq_counter += 1

    if injected == 0:
        # No SEQ headers found — inject a single block near the top
        _log("No SEQ headers found — injecting single CAPTURE block at top")
        op_data = op_lookup.get(0, {})
        op_id = _make_op_id(op_data) if op_data else "program_000"
        tool_id = _make_tool_id(op_data) if op_data else "T0"
        capture_lines = build_capture_block(session_id, op_id, tool_id)

        # Find insertion point (after % and O-line if present)
        insert_at = 0
        for i, line in enumerate(new_lines):
            stripped = line.strip()
            if stripped.startswith('%') or stripped.startswith('O'):
                insert_at = i + 1
            elif stripped.startswith('(PART:') or stripped.startswith('(OP:'):
                insert_at = i + 1
            else:
                break

        for j, cl in enumerate(capture_lines):
            new_lines.insert(insert_at + j, cl + "\n")
        injected = 1

    # Write back
    try:
        with open(nc_file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        _log(f"Injected {injected} CAPTURE block(s) into {nc_file_path}")
    except Exception as e:
        _log(f"Could not write NC file: {e}")
        return 0

    return injected


def find_recent_nc_files(output_folder, max_age_seconds=60):
    """Find NC files recently created/modified in the output folder.

    Args:
        output_folder: Directory to search
        max_age_seconds: Maximum file age in seconds

    Returns:
        list of file paths
    """
    import time
    now = time.time()
    results = []

    if not os.path.isdir(output_folder):
        return results

    for pattern in ["*.nc", "*.NC", "*.tap", "*.TAP"]:
        for path in glob.glob(os.path.join(output_folder, pattern)):
            try:
                mtime = os.path.getmtime(path)
                if (now - mtime) <= max_age_seconds:
                    results.append(path)
            except Exception:
                continue

    return sorted(results, key=os.path.getmtime, reverse=True)
