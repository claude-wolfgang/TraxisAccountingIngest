"""
Snapshot — serialize full CAM state to a JSON-serializable dict.

Captures setups, operations, tools, feeds/speeds, passes, and linking
parameters. All values converted from cm to inches (/ 2.54).

Called at two moments:
  - Snapshot A: when document is opened (baseline)
  - Snapshot B: after post completes (final state)
"""

import adsk.core
import adsk.fusion
import adsk.cam
from datetime import datetime


# CM to inches conversion factor
CM_TO_IN = 1.0 / 2.54


def _safe_float(value, to_inches=False):
    """Safely convert a value to float, optionally converting cm -> inches."""
    try:
        v = float(value)
        if to_inches:
            v *= CM_TO_IN
        return round(v, 6)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    """Safely convert a value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value):
    """Safely convert to string."""
    try:
        return str(value) if value is not None else None
    except Exception:
        return None


def _read_param(op, name, to_inches=False):
    """Read a named parameter from an operation, returning its value."""
    try:
        param = op.parameters.itemByName(name)
        if param is None:
            return None
        val = param.expression
        # Try numeric value first
        try:
            v = float(param.value)
            if to_inches:
                v *= CM_TO_IN
            return round(v, 6)
        except (TypeError, ValueError):
            return val
    except Exception:
        return None


def _read_param_expression(op, name):
    """Read a parameter's expression string."""
    try:
        param = op.parameters.itemByName(name)
        if param is None:
            return None
        return param.expression
    except Exception:
        return None


def _extract_tool_data(op):
    """Extract tool information from an operation."""
    try:
        tool = op.tool
        if tool is None:
            return {}
        return {
            "tool_id": _safe_str(tool.description) or _safe_str(tool.name),
            "tool_description": _safe_str(tool.description),
            "tool_type": _safe_str(tool.type),
            "tool_diameter_in": _safe_float(tool.diameter, to_inches=True),
            "tool_number": _safe_int(tool.number),
            "tool_bodyLength_in": _safe_float(
                getattr(tool, 'bodyLength', None), to_inches=True),
            "tool_fluteLength_in": _safe_float(
                getattr(tool, 'fluteLength', None), to_inches=True),
            "tool_numberOfFlutes": _safe_int(
                getattr(tool, 'numberOfFlutes', None)),
            "tool_productId": _safe_str(
                getattr(tool, 'productId', None)),
        }
    except Exception:
        return {}


def _extract_passes(op):
    """Extract pass parameters from an operation."""
    return {
        "stepover": _read_param(op, "stepover", to_inches=True),
        "stepdown": _read_param(op, "stepdown", to_inches=True),
        "finishing_stepover": _read_param(
            op, "finishing_stepover", to_inches=True),
        "finishing_stepdown": _read_param(
            op, "finishing_stepdown", to_inches=True),
        "finishing_passes": _read_param(op, "numberOfStepdowns"),
        "stock_to_leave": _read_param(
            op, "stock_to_leave", to_inches=True),
        "stock_to_leave_axial": _read_param(
            op, "stock_to_leave_axial", to_inches=True),
        "stock_to_leave_radial": _read_param(
            op, "stock_to_leave_radial", to_inches=True),
        "tolerance": _read_param(op, "tolerance", to_inches=True),
    }


def _extract_feeds(op):
    """Extract feed and speed parameters from an operation."""
    return {
        "cutting_feedrate": _read_param(op, "tool_feedCutting"),
        "entry_feedrate": _read_param(op, "tool_feedEntry"),
        "exit_feedrate": _read_param(op, "tool_feedExit"),
        "plunge_feedrate": _read_param(op, "tool_feedPlunge"),
        "ramp_feedrate": _read_param(op, "tool_feedRamp"),
        "spindle_rpm": _read_param(op, "tool_spindleSpeed"),
        "surface_speed": _read_param(op, "tool_surfaceSpeed"),
        "feed_per_tooth": _read_param(op, "tool_feedPerTooth"),
        "cutting_feedrate_ipm": _read_param(
            op, "tool_feedCutting", to_inches=True),
    }


def _extract_linking(op):
    """Extract linking/transition parameters from an operation."""
    return {
        "ramp_angle": _read_param(op, "rampAngle"),
        "ramp_type": _read_param_expression(op, "rampType"),
        "entry_type": _read_param_expression(op, "entryType"),
        "lead_in_radius": _read_param(
            op, "leadInRadius", to_inches=True),
        "lead_out_radius": _read_param(
            op, "leadOutRadius", to_inches=True),
        "retract_height": _read_param(
            op, "retractHeight", to_inches=True),
        "clearance_height": _read_param(
            op, "clearanceHeight", to_inches=True),
    }


def _extract_operation(op, seq_num):
    """Extract full operation data."""
    tool_data = _extract_tool_data(op)
    passes = _extract_passes(op)
    feeds = _extract_feeds(op)
    linking = _extract_linking(op)

    # Get operation type string
    op_type = ""
    try:
        strategy = op.strategy
        if strategy:
            op_type = _safe_str(strategy.name) or ""
    except Exception:
        pass
    if not op_type:
        try:
            op_type = _safe_str(op.type) or ""
        except Exception:
            pass

    return {
        "name": _safe_str(op.name),
        "type": op_type,
        "sequence": seq_num,
        "is_suppressed": getattr(op, 'isSuppressed', False),
        **tool_data,
        "passes": passes,
        "feeds": feeds,
        "linking": linking,
    }


def _get_all_operations(item):
    """Recursively collect all operations from a setup or folder."""
    ops = []
    try:
        # Check if it's a folder with children
        if hasattr(item, 'allOperations'):
            for i in range(item.allOperations.count):
                ops.append(item.allOperations.item(i))
        elif hasattr(item, 'children'):
            for i in range(item.children.count):
                child = item.children.item(i)
                ops.extend(_get_all_operations(child))
        elif hasattr(item, 'operations'):
            for i in range(item.operations.count):
                ops.append(item.operations.item(i))
    except Exception:
        pass
    return ops


def _extract_setup(setup, setup_index):
    """Extract full setup data including all operations."""
    # WCS origin
    wcs_origin = [0.0, 0.0, 0.0]
    try:
        wcs = setup.workCoordinateSystem
        if wcs:
            origin = wcs.origin
            if origin:
                wcs_origin = [
                    _safe_float(origin.x, to_inches=True),
                    _safe_float(origin.y, to_inches=True),
                    _safe_float(origin.z, to_inches=True),
                ]
    except Exception:
        pass

    # Collect operations
    all_ops = _get_all_operations(setup)
    operations = []
    for seq, op in enumerate(all_ops):
        try:
            operations.append(_extract_operation(op, seq))
        except Exception:
            continue

    return {
        "name": _safe_str(setup.name),
        "index": setup_index,
        "wcs_origin": wcs_origin,
        "operation_count": len(operations),
        "operations": operations,
    }


def take_snapshot(session_id, origin=None):
    """Take a full snapshot of the current CAM state.

    Args:
        session_id: Session identifier string
        origin: Document origin type (toolpath/prior_program/fresh)

    Returns:
        dict: Full CAM state snapshot, or None if no CAM data available
    """
    try:
        app = adsk.core.Application.get()
        doc = app.activeDocument
        if doc is None:
            return None

        cam = adsk.cam.CAM.cast(
            doc.products.itemByProductType('CAMProductType'))
        if cam is None:
            return None

        # Read origin from document attributes if not provided
        if origin is None:
            try:
                attr = doc.attributes.itemByName('TraxisCapture', 'origin')
                origin = attr.value if attr else "unknown"
            except Exception:
                origin = "unknown"

        # Extract all setups
        setups = []
        for i in range(cam.setups.count):
            try:
                setup = cam.setups.item(i)
                setups.append(_extract_setup(setup, i))
            except Exception:
                continue

        snapshot = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "document": _safe_str(doc.name),
            "origin": origin,
            "setups": setups,
        }

        return snapshot

    except Exception:
        return None
