"""
ProShop Bridge for Fusion 360
v1.5.3 — Traxis Manufacturing

Unified add-in: WO browser + CAM export + push to ProShop.
Replaces ProShopConnector, EXPORT TO PROSHOP, and proshop_gui.

INSTALLATION:
1. Copy entire ProShopBridge folder to:
   %appdata%\Autodesk\Autodesk Fusion 360\API\AddIns\
2. In Fusion: Scripts and Add-Ins → Add-Ins → ProShopBridge → Run
3. Check "Run on Startup"

CREDENTIALS:
Reads from ~/.traxis.env (same file used by all Traxis automations)
"""

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import json
import os
import math
import threading
import urllib.request
import urllib.parse
import urllib.error
import ssl
import time
import webbrowser
import base64
import uuid
import tempfile
import subprocess
import queue
import re
import http.server
import socketserver
import logging
import logging.handlers

# ===========================================================================
# Global references (prevent garbage collection)
# ===========================================================================
_app = None
_ui = None
_handlers = []
_palette = None
_token = None
_token_expiry = 0
_response_queue = queue.Queue()
_push_result_queue = queue.Queue()
_push_state = None
RESPONSE_EVENT_ID = "proshopBridgeResponse"
PUSH_NEXT_EVENT_ID = "proshopBridgePushNext"

# Constants — unique IDs to avoid conflict with ProShopConnector
PALETTE_ID = "proshopBridgePalette"
PALETTE_NAME = "ProShop Bridge"
CMD_ID = "proshopBridgeCmd"
PANEL_ID = "proshopBridgePanel"

# ProShop connection
PROSHOP_HOST = "traxismfg.adionsystems.com"
GRAPHQL_URL = f"https://{PROSHOP_HOST}/api/graphql"
TOKEN_URL = f"https://{PROSHOP_HOST}/home/member/oauth/accesstoken"
PROSHOP_BASE_URL = f"https://{PROSHOP_HOST}/procnc"
SCOPES = "parts:rwdp+workorders:rwdp+users:r"

# Screenshot settings
SCREENSHOT_WIDTH = 960
SCREENSHOT_HEIGHT = 540

# Credential file paths
ENV_FILE_LOCAL = os.path.join(os.path.expanduser("~"), ".traxis.env")
ENV_FILE_SHARED = os.path.join(os.path.expanduser("~"), "Dropbox",
                                "MACHINE COMM Traxis", "Keys", ".traxis.env")


def _resolve_env_file():
    if os.path.exists(ENV_FILE_LOCAL):
        return ENV_FILE_LOCAL
    if os.path.exists(ENV_FILE_SHARED):
        return ENV_FILE_SHARED
    return ENV_FILE_LOCAL

ENV_FILE = _resolve_env_file()


_file_logger = None


def _init_file_logger():
    """Set up rotating file logger (called once on first log() call)."""
    global _file_logger
    if _file_logger is not None:
        return
    _file_logger = logging.getLogger("bridge_file")
    _file_logger.setLevel(logging.DEBUG)
    _file_logger.propagate = False
    # Guard: logging.getLogger returns the same object across module reloads,
    # so handlers from previous add-in toggles may still be attached.
    if _file_logger.handlers:
        return
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "bridge.log"),
            maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(threadName)-15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        _file_logger.addHandler(fh)
    except Exception:
        pass  # File logging unavailable — Fusion output still works


def log(msg):
    try:
        adsk.core.Application.get().log(f"[Bridge] {msg}")
    except Exception:
        pass
    try:
        _init_file_logger()
        _file_logger.info(msg)
    except Exception:
        pass


# ===========================================================================
# Credentials & Authentication
# ===========================================================================

def load_credentials():
    creds = {}
    if not os.path.exists(ENV_FILE):
        return creds
    try:
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    creds[key.strip()] = val.strip()
    except Exception as e:
        log(f"Error reading {ENV_FILE}: {e}")
    return creds


def get_token():
    global _token, _token_expiry
    if _token and time.time() < _token_expiry:
        return _token
    creds = load_credentials()
    client_id = creds.get("PROSHOP_CLIENT_ID", "")
    client_secret = creds.get("PROSHOP_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        log("Missing PROSHOP_CLIENT_ID or PROSHOP_CLIENT_SECRET in .traxis.env")
        return None
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": SCOPES
    }).encode("utf-8")
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(TOKEN_URL, data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded"
        })
        with urllib.request.urlopen(req, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            _token = result.get("access_token")
            expires_in = result.get("expires_in", 86400)
            _token_expiry = time.time() + expires_in - 300
            log("OAuth token acquired")
            return _token
    except Exception as e:
        log(f"Token error: {e}")
        return None


# ===========================================================================
# GraphQL API
# ===========================================================================

def graphql_query(query, variables=None):
    token = get_token()
    if not token:
        return {"errors": [{"message": "No auth token available. Check .traxis.env credentials."}]}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode("utf-8")
    ctx = ssl.create_default_context()
    req = urllib.request.Request(GRAPHQL_URL, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log(f"GraphQL HTTP {e.code}: {body[:300]}")
        return {"errors": [{"message": f"HTTP {e.code}: {body[:200]}"}]}
    except Exception as e:
        log(f"GraphQL error: {e}")
        return {"errors": [{"message": str(e)}]}


def fetch_work_orders(year=None):
    if not year:
        from datetime import datetime
        year = str(datetime.now().year)
    log(f"Fetching work orders for year={year}")
    query = """
    query($year: String) {
      workOrders(filter: {year: $year}, pageSize: 500) {
        totalRecords
        records {
          workOrderNumber
          status
          part { partNumber partName customerPartNumber }
          partRev
        }
      }
    }
    """
    result = graphql_query(query, {"year": year})
    if "errors" in result:
        log(f"GraphQL errors: {result['errors']}")
    elif "data" in result:
        wo_data = result.get("data", {}).get("workOrders", {})
        log(f"Year {year}: totalRecords={wo_data.get('totalRecords', '?')}, returned={len(wo_data.get('records', []))}")
    return result


def fetch_multi_year_work_orders():
    from datetime import datetime
    current_year = datetime.now().year
    years = [str(current_year), str(current_year - 1)]
    results = [None, None]
    def _fetch(idx, year):
        results[idx] = fetch_work_orders(year)
    threads = [threading.Thread(target=_fetch, args=(i, y)) for i, y in enumerate(years)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    all_records = []
    errors = []
    for result in results:
        if result and "errors" in result:
            errors.extend(result["errors"])
        elif result and "data" in result:
            records = result.get("data", {}).get("workOrders", {}).get("records", [])
            all_records.extend(records)
    log(f"Multi-year total: {len(all_records)} WOs from {years[0]} + {years[1]}")
    if errors and not all_records:
        return {"errors": errors}
    return {"data": {"workOrders": {"totalRecords": len(all_records), "records": all_records}}}


def fetch_single_wo(wo_number):
    query = """
    query($woNum: String!) {
      workOrder(workOrderNumber: $woNum) {
        workOrderNumber
        status
        part { partNumber partName customerPartNumber }
        partRev
        ops {
          records {
            operationNumber
            operationDescription
            proshopUrl
            isOpComplete
            setupTime
            runTime
          }
        }
      }
    }
    """
    return graphql_query(query, {"woNum": wo_number})


# ===========================================================================
# Document Context
# ===========================================================================

def get_document_context():
    doc_name = ""
    folder_name = ""
    project_name = ""
    try:
        doc = _app.activeDocument
        if doc:
            doc_name = doc.name or ""
            try:
                data_file = doc.dataFile
                if data_file:
                    folder = data_file.parentFolder
                    if folder:
                        folder_name = folder.name or ""
            except Exception:
                pass  # dataFile may not exist for unsaved documents
    except Exception:
        pass  # No active document
    try:
        project = _app.data.activeProject
        if project:
            project_name = project.name or ""
    except Exception:
        pass  # No active project
    log(f"Document context: doc='{doc_name}', folder='{folder_name}', project='{project_name}'")
    return doc_name, folder_name, project_name


def get_fusion_user():
    try:
        user = _app.currentUser
        if user:
            return user.displayName or ""
    except Exception:
        pass
    return ""


def _decompose_wcs(setup):
    """Extract origin and axes from setup's WCS Matrix3D.

    setup.workCoordinateSystem returns a Matrix3D, not a coordinate system
    object.  Use getAsCoordinateSystem() to decompose it.

    Returns (origin: Point3D, xAxis: Vector3D, yAxis: Vector3D, zAxis: Vector3D)
    or None on failure.
    """
    try:
        wcs = setup.workCoordinateSystem
        if not wcs:
            return None
        # Python API returns (Point3D, Vector3D, Vector3D, Vector3D)
        origin, x_axis, y_axis, z_axis = wcs.getAsCoordinateSystem()
        return origin, x_axis, y_axis, z_axis
    except Exception as e:
        log(f"Could not decompose WCS: {e}")
        return None


def _describe_setup_transition(prev_wcs, curr_wcs):
    """Describe how the part is re-oriented from one setup to the next.

    Uses face-mapping: tells the machinist which previous face now points
    in which direction (e.g. "Top &rarr; Front, Front &rarr; Bottom").

    Args:
        prev_wcs: (origin, xAxis, yAxis, zAxis) from _decompose_wcs
        curr_wcs: (origin, xAxis, yAxis, zAxis) from _decompose_wcs

    Returns:
        Human-readable HTML string or None.
    """
    if not prev_wcs or not curr_wcs:
        return None

    po, px, py, pz = prev_wcs
    co, cx, cy, cz = curr_wcs

    def dot(a, b):
        return a.x * b.x + a.y * b.y + a.z * b.z

    # R[i][j] = dot(curr_axis_i, prev_axis_j)
    # Column j tells us where previous axis j ends up in the current frame
    R = [
        [dot(cx, px), dot(cx, py), dot(cx, pz)],
        [dot(cy, px), dot(cy, py), dot(cy, pz)],
        [dot(cz, px), dot(cz, py), dot(cz, pz)]
    ]

    # From operator's perspective: facing +Y, +X to his right, +Z up
    FACES_POS = ["Right", "Back", "Top"]        # X+, Y+, Z+
    FACES_NEG = ["Left", "Front", "Bottom"]     # X-, Y-, Z-

    def face_name(axis_idx, sign):
        return FACES_POS[axis_idx] if sign > 0 else FACES_NEG[axis_idx]

    # Map each previous axis to its closest current axis
    mappings = []  # list of (prev_axis_idx, curr_axis_idx, sign)
    clean = True
    for j in range(3):
        col = [R[0][j], R[1][j], R[2][j]]
        abs_col = [abs(v) for v in col]
        max_i = abs_col.index(max(abs_col))
        if abs_col[max_i] < 0.9:
            clean = False
            break
        sign = 1 if col[max_i] > 0 else -1
        mappings.append((j, max_i, sign))

    # Compute rotation angle and axis (used for "in other words" summary)
    trace = R[0][0] + R[1][1] + R[2][2]
    cos_angle = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
    angle_rad = math.acos(cos_angle)
    angle_deg = round(math.degrees(angle_rad))

    def _rotation_summary():
        """Describe the rotation in machinist terms."""
        if angle_deg < 2:
            return None
        # Find rotation axis from skew-symmetric part of R
        ax = R[2][1] - R[1][2]
        ay = R[0][2] - R[2][0]
        az = R[1][0] - R[0][1]
        mag = math.sqrt(ax*ax + ay*ay + az*az)
        if mag < 0.001:
            # 180° — skew-symmetric method fails; use (R+I) eigenvector instead.
            # For 180° rotation about axis n: R = 2*n*n^T - I, so (R+I) = 2*n*n^T.
            # Any non-zero column of (R+I) is proportional to the rotation axis.
            rpi = [[R[i][j] + (1 if i == j else 0) for j in range(3)] for i in range(3)]
            best_col, best_norm = 0, 0
            for j in range(3):
                n = math.sqrt(rpi[0][j]**2 + rpi[1][j]**2 + rpi[2][j]**2)
                if n > best_norm:
                    best_norm = n
                    best_col = j
            if best_norm > 0.001:
                col = [rpi[i][best_col] / best_norm for i in range(3)]
                abs_c = [abs(c) for c in col]
                max_i = abs_c.index(max(abs_c))
                if abs_c[max_i] > 0.95:
                    axis_name = ["X", "Y", "Z"][max_i]
                    return f"flip about {axis_name} axis"
            return "flip 180&deg;"
        ax /= mag; ay /= mag; az /= mag
        abs_vals = [abs(ax), abs(ay), abs(az)]
        max_i = abs_vals.index(max(abs_vals))
        if abs_vals[max_i] > 0.9:
            axis_name = ["X", "Y", "Z"][max_i]
            a = angle_deg if [ax, ay, az][max_i] > 0 else -angle_deg
            return f"rotate {a}&deg; about {axis_name} axis"
        return f"rotate {angle_deg}&deg;"

    summary = _rotation_summary()

    # Compute rotation axis vector for visual rendering
    rot_axis = None
    if angle_deg >= 2:
        _ax = R[2][1] - R[1][2]
        _ay = R[0][2] - R[2][0]
        _az = R[1][0] - R[0][1]
        _mag = math.sqrt(_ax*_ax + _ay*_ay + _az*_az)
        if _mag > 0.001:
            rot_axis = (_ax/_mag, _ay/_mag, _az/_mag)
        elif angle_deg > 170:
            rpi = [[R[i][j] + (1 if i == j else 0) for j in range(3)] for i in range(3)]
            best_col, best_norm = 0, 0
            for j in range(3):
                n2 = math.sqrt(rpi[0][j]**2 + rpi[1][j]**2 + rpi[2][j]**2)
                if n2 > best_norm:
                    best_norm = n2
                    best_col = j
            if best_norm > 0.001:
                rot_axis = tuple(rpi[i][best_col] / best_norm for i in range(3))

    base = {"summary": summary, "rotation_axis": rot_axis, "rotation_angle": angle_deg}

    if not clean:
        text = summary or f"rotate {angle_deg}&deg;"
        return {**base, "text": f"Non-orthogonal reorientation &mdash; {text} (check model)",
                "face_map": None}

    # Identity — no change
    if all(m[0] == m[1] and m[2] == 1 for m in mappings):
        return {"text": "Same orientation", "summary": None,
                "rotation_axis": None, "rotation_angle": 0, "face_map": None}

    # Build complete face map: position → what identity is now there
    face_map = {}
    for prev_idx, curr_idx, sign in mappings:
        prev_pos_face = FACES_POS[prev_idx]
        prev_neg_face = FACES_NEG[prev_idx]
        curr_pos_name = FACES_POS[curr_idx]
        curr_neg_name = FACES_NEG[curr_idx]
        if sign > 0:
            face_map[curr_pos_name] = prev_pos_face
            face_map[curr_neg_name] = prev_neg_face
        else:
            face_map[curr_pos_name] = prev_neg_face
            face_map[curr_neg_name] = prev_pos_face

    text = summary or f"reoriented {angle_deg}&deg;"
    return {**base, "text": text, "face_map": face_map}


def _render_orientation_cube_svg(highlights=None, size=100, rotation_axis=None, rotation_angle=0):
    """Render an isometric cube as inline SVG with optional face highlights.

    Args:
        highlights: dict mapping face position names to hex colors,
                    e.g. {"Top": "#4CAF50", "Front": "#2196F3"}
        size: pixel dimensions (square)
        rotation_axis: optional (x,y,z) unit vector — draws axis spear + curved arrow
        rotation_angle: rotation in degrees (used for arc sweep)

    Returns:
        Inline SVG string.
    """
    if highlights is None:
        highlights = {}

    s = size * 0.33
    cx = size / 2
    cy = size / 2
    COS30 = 0.866
    SIN30 = 0.5

    def proj(x, y, z):
        px = (x - y) * COS30 * s + cx
        py = (x + y) * SIN30 * s - z * s + cy
        return (round(px, 1), round(py, 1))

    # 8 vertices indexed as x*4 + y*2 + z
    # 0=(0,0,0) 1=(0,0,1) 2=(0,1,0) 3=(0,1,1) 4=(1,0,0) 5=(1,0,1) 6=(1,1,0) 7=(1,1,1)
    V = [proj(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]

    def pts(*indices):
        return " ".join(f"{V[i][0]},{V[i][1]}" for i in indices)

    def hex_rgba(hx, alpha):
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        return f"rgba({r},{g},{b},{alpha})"

    # Faces: (vertex indices, is_front_facing_in_iso_view)
    FACES = [
        ("Bottom", [0, 4, 6, 2], False),
        ("Back",   [2, 6, 7, 3], False),
        ("Left",   [0, 2, 3, 1], False),
        ("Top",    [1, 5, 7, 3], True),
        ("Front",  [0, 4, 5, 1], True),
        ("Right",  [4, 6, 7, 5], True),
    ]
    lines = [f'<svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg" '
             f'style="display:inline-block;vertical-align:middle;">']

    # Draw back faces first, then front faces (painter's algorithm)
    for name, verts, front in FACES:
        color = highlights.get(name)
        if color:
            fill = hex_rgba(color, 0.55 if front else 0.35)
            stroke = color
            sw = "2" if front else "1.5"
        else:
            fill = "rgba(230,230,230,0.4)" if front else "rgba(200,200,200,0.08)"
            stroke = "#555" if front else "#aaa"
            sw = "1" if front else "0.75"
        lines.append(f'<polygon points="{pts(*verts)}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    lines.append("</svg>")
    return "\n".join(lines)


def _render_transition_visual(transition):
    """Render Before/After orientation cubes with rotation caption.

    Args:
        transition: dict with 'text', optional 'face_map' dict, and optional 'summary'.

    Returns:
        HTML string, or empty string if no transition.
    """
    if not transition:
        return ""

    face_map = transition.get("face_map")
    summary = transition.get("summary", "")
    TOP_COLOR = "#4CAF50"
    FRONT_COLOR = "#2196F3"

    rot_axis = transition.get("rotation_axis")
    rot_angle = transition.get("rotation_angle", 0)
    before = _render_orientation_cube_svg({"Top": TOP_COLOR, "Front": FRONT_COLOR},
                                          rotation_axis=rot_axis, rotation_angle=rot_angle)

    if face_map:
        inv_map = {v: k for k, v in face_map.items()}
        after_hl = {inv_map.get("Top", "Top"): TOP_COLOR,
                    inv_map.get("Front", "Front"): FRONT_COLOR}
        after = _render_orientation_cube_svg(after_hl)
    else:
        after = _render_orientation_cube_svg({"Top": TOP_COLOR, "Front": FRONT_COLOR})

    h = []
    h.append('<div style="margin:6px 0 10px 0;">')
    h.append('  <div style="font-weight:bold; font-size:12px; margin-bottom:4px;">From Previous Op:</div>')
    h.append('  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">')
    h.append(f'    <div style="text-align:center;">'
             f'<div style="font-size:10px;font-weight:bold;color:#666;">BEFORE</div>{before}</div>')
    h.append(f'    <div style="font-size:22px;color:#666;padding:0 2px;">&rarr;</div>')
    h.append(f'    <div style="text-align:center;">'
             f'<div style="font-size:10px;font-weight:bold;color:#666;">AFTER</div>{after}</div>')
    h.append('  </div>')
    h.append(f'  <div style="font-size:10px;color:#555;margin-top:3px;">')
    h.append(f'    <span style="color:{TOP_COLOR};">&#9632;</span>&nbsp;Top&ensp;'
             f'<span style="color:{FRONT_COLOR};">&#9632;</span>&nbsp;Front')
    if summary:
        h.append(f'&ensp;&mdash;&ensp;{summary}')
    h.append('  </div>')
    h.append('</div>')
    return "\n".join(h)


def get_cam_product():
    """Return the CAM product from the active document, or None."""
    try:
        doc = _app.activeDocument
        if doc:
            return adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))
    except Exception:
        pass
    return None


# ===========================================================================
# CAM Data Extraction (from EXPORT TO PROSHOP script)
# ===========================================================================

def _is_op_suppressed(op):
    """True if the op itself or any ancestor folder/pattern is suppressed."""
    try:
        if bool(getattr(op, 'isSuppressed', False)):
            return True
    except Exception:
        pass
    try:
        node = getattr(op, 'parent', None)
        # Bound the walk in case parent traversal loops or never terminates.
        for _ in range(16):
            if node is None:
                break
            if bool(getattr(node, 'isSuppressed', False)):
                return True
            node = getattr(node, 'parent', None)
    except Exception:
        pass
    return False


def _filter_active(operations, setup_name):
    active_ops = []
    skipped_names = []
    for op in operations:
        if _is_op_suppressed(op):
            try:
                skipped_names.append(getattr(op, 'name', '?'))
            except Exception:
                skipped_names.append('?')
        else:
            active_ops.append(op)
    if skipped_names:
        try:
            log(f"Skipped {len(skipped_names)} suppressed op(s) in setup '{setup_name}': {', '.join(skipped_names)}")
        except Exception:
            pass
    return active_ops


def get_all_operations(setup):
    operations = []
    try:
        if hasattr(setup, 'allOperations') and setup.allOperations:
            for i in range(setup.allOperations.count):
                operations.append(setup.allOperations.item(i))
            return _filter_active(operations, getattr(setup, 'name', '?'))
    except Exception:
        pass
    try:
        for i in range(setup.operations.count):
            operations.append(setup.operations.item(i))
    except Exception:
        pass
    try:
        for i in range(setup.folders.count):
            folder = setup.folders.item(i)
            operations.extend(_ops_from_folder(folder))
    except Exception:
        pass
    try:
        if hasattr(setup, 'patterns'):
            for i in range(setup.patterns.count):
                operations.extend(_ops_from_pattern(setup.patterns.item(i)))
    except Exception:
        pass
    return _filter_active(operations, getattr(setup, 'name', '?'))


def _ops_from_folder(folder):
    ops = []
    try:
        for i in range(folder.operations.count):
            ops.append(folder.operations.item(i))
    except Exception:
        pass
    try:
        for i in range(folder.folders.count):
            ops.extend(_ops_from_folder(folder.folders.item(i)))
    except Exception:
        pass
    try:
        if hasattr(folder, 'patterns'):
            for i in range(folder.patterns.count):
                ops.extend(_ops_from_pattern(folder.patterns.item(i)))
    except Exception:
        pass
    return ops


def _ops_from_pattern(pattern):
    ops = []
    try:
        if hasattr(pattern, 'operations'):
            for i in range(pattern.operations.count):
                ops.append(pattern.operations.item(i))
    except Exception:
        pass
    if not ops:
        try:
            if hasattr(pattern, 'allOperations'):
                for i in range(pattern.allOperations.count):
                    ops.append(pattern.allOperations.item(i))
        except Exception:
            pass
    if not ops:
        try:
            if hasattr(pattern, 'name') and hasattr(pattern, 'parameters'):
                ops.append(pattern)
        except Exception:
            pass
    return ops


def _param_value(operation, param_name):
    try:
        param = operation.parameters.itemByName(param_name)
        if param:
            val = param.value
            return val.value if hasattr(val, 'value') else val
    except Exception:
        pass
    return None


def _param_expr(operation, param_name):
    try:
        param = operation.parameters.itemByName(param_name)
        if param:
            expr = param.expression
            if expr:
                if (expr.startswith("'") and expr.endswith("'")) or \
                   (expr.startswith('"') and expr.endswith('"')):
                    return expr[1:-1]
                return expr
    except Exception:
        pass
    return None


def _get_op_type(operation):
    try:
        strategy = operation.parameters.itemByName('strategy')
        if strategy:
            return strategy.expression
    except Exception:
        pass
    return operation.objectType.split('::')[-1]


def extract_tool_data(operation):
    try:
        tool_data = {
            'number': _param_value(operation, 'tool_number'),
            'description': _param_expr(operation, 'tool_description'),
            'comment': _param_expr(operation, 'tool_comment'),
            'type': _param_expr(operation, 'tool_type'),
            'diameter': _param_value(operation, 'tool_diameter'),
            'flute_length': _param_value(operation, 'tool_fluteLength'),
            'overall_length': _param_value(operation, 'tool_overallLength'),
            'body_length': _param_value(operation, 'tool_bodyLength'),
            'shoulder_length': _param_value(operation, 'tool_shoulderLength'),
            'shaft_diameter': _param_value(operation, 'tool_shaftDiameter'),
            'number_of_flutes': _param_value(operation, 'tool_numberOfFlutes'),
            'holder_description': _param_expr(operation, 'tool_holderDescription'),
            'holder_id': _param_expr(operation, 'tool_holderId'),
            'product_id': _param_expr(operation, 'tool_productId'),
            'product_link': _param_expr(operation, 'tool_productLink'),
            'vendor': _param_expr(operation, 'tool_vendor'),
            'coolant': _param_expr(operation, 'tool_coolant')
        }
        if tool_data['number'] is None and tool_data['diameter'] is None:
            return None
        return tool_data
    except Exception:
        return None


def extract_operation_data(operation, sequence_num):
    try:
        op_type = _get_op_type(operation)
        is_manual_nc = 'manual' in op_type.lower() or 'ManualNCOperation' in operation.objectType
        manual_nc_comment = ""
        op_name = operation.name
        if is_manual_nc and '[' in op_name and ']' in op_name:
            manual_nc_comment = op_name[op_name.find('[') + 1:op_name.find(']')]
        if is_manual_nc and not manual_nc_comment:
            for pn in ['nc_comment', 'comment', 'manualNC_comment', 'manual_nc_comment',
                        'notes', 'operation_comment', 'job_description']:
                c = _param_expr(operation, pn)
                if c:
                    manual_nc_comment = c
                    break
        if is_manual_nc and not manual_nc_comment:
            try:
                if hasattr(operation, 'comment') and operation.comment:
                    manual_nc_comment = operation.comment
            except Exception:
                pass
        return {
            'sequence': sequence_num,
            'name': operation.name,
            'type': op_type,
            'is_manual_nc': is_manual_nc,
            'manual_nc_comment': manual_nc_comment,
            'tool': extract_tool_data(operation),
            'parameters': {},
            'machining_time': None,
            'notes': _param_expr(operation, 'notes') or ''
        }
    except Exception:
        return None


def get_stock_info(setup):
    stock_data = {}
    for param_name in ['job_stockMode', 'job_stockOffsetSides',
                        'job_stockOffsetTop', 'job_stockOffsetBottom']:
        try:
            param = setup.parameters.itemByName(param_name)
            if param:
                clean = param_name.replace('job_stock', '').replace('_', ' ').strip()
                if clean == 'Mode':
                    mode_expr = param.expression or ""
                    # Skip unresolved conditional expressions
                    if '?' not in mode_expr or '==' not in mode_expr:
                        stock_data['mode'] = mode_expr.strip("'\"")
                    continue
                else:
                    stock_data[clean.lower()] = param.value.value if hasattr(param.value, 'value') else param.expression
        except Exception:
            pass
    return stock_data


def is_turning_setup(setup):
    try:
        setup_type = setup.operationType
        # CAMOperationTypes enum doesn't exist in Fusion 360 Python 3.14.
        # Use integer comparison: 0=Milling, 1=Turning, 2=Cutting
        if hasattr(adsk.cam, 'CAMOperationTypes') and hasattr(adsk.cam.CAMOperationTypes, 'TurningOperation'):
            return setup_type == adsk.cam.CAMOperationTypes.TurningOperation
        # Direct integer comparison
        result = (setup_type == 1)
        if result:
            log(f"Setup '{setup.name}' detected as turning (operationType={setup_type})")
        return result
    except Exception:
        pass
    return False


def get_wcs_info(setup):
    wcs_data = {}
    def _pval(param):
        if param is None:
            return None
        try:
            val = param.value
            return float(val.value) if hasattr(val, 'value') else float(val)
        except Exception:
            return None
    def _pexpr(param):
        if param is None:
            return None
        try:
            expr = param.expression
            if not expr:
                return None
            # Skip unresolved conditional expressions (ternary formulas)
            if '?' in expr and '==' in expr:
                return None
            if expr.startswith("'") or expr.startswith('"'):
                expr = expr[1:-1]
            return expr
        except Exception:
            return None
    try:
        wcs_num = _pval(setup.parameters.itemByName('job_workOffset'))
        if wcs_num is not None:
            wcs_num = int(wcs_num)
            if 1 <= wcs_num <= 6:
                wcs_data['gcode'] = f"G{53 + wcs_num}"
            elif wcs_num > 6:
                wcs_data['gcode'] = f"G54.1 P{wcs_num - 6}"
            else:
                wcs_data['gcode'] = "G54"
            wcs_data['number'] = wcs_num
        else:
            wcs_data['gcode'] = "G54"
        # WCS origin mode — use .value (not .expression) to get resolved value
        origin_mode = None
        if is_turning_setup(setup):
            origin_mode = _pexpr(setup.parameters.itemByName('wcs_origin_turning'))
        if not origin_mode:
            # .value gives resolved result; .expression may be a ternary
            p = setup.parameters.itemByName('wcs_origin_mode')
            if p:
                try:
                    v = p.value
                    origin_mode = str(v.value) if hasattr(v, 'value') else str(v)
                except Exception:
                    origin_mode = _pexpr(p)
        if origin_mode:
            # Split camelCase (e.g., "modelPoint" → "model Point") then title-case
            spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', origin_mode)
            wcs_data['origin_mode'] = spaced.replace('_', ' ').title()

        # Read box point position (e.g., "top center", "bottom center")
        bp = setup.parameters.itemByName('wcs_origin_boxPoint')
        if bp:
            try:
                bpv = bp.value
                box_str = str(bpv.value) if hasattr(bpv, 'value') else str(bpv)
            except Exception:
                box_str = _pexpr(bp)
            if box_str:
                wcs_data['box_point'] = box_str.strip().title()
        chuck_val = _pval(setup.parameters.itemByName('chuckFront_value'))
        if chuck_val is not None:
            wcs_data['chuck_position'] = chuck_val / 2.54
        stock_high = _pval(setup.parameters.itemByName('stockZHigh'))
        if stock_high is not None:
            wcs_data['stock_z_high'] = stock_high / 2.54
        stock_low = _pval(setup.parameters.itemByName('stockZLow'))
        if stock_low is not None:
            wcs_data['stock_z_low'] = stock_low / 2.54
        stock_len = _pval(setup.parameters.itemByName('stockLength'))
        if stock_len is not None:
            wcs_data['stock_length'] = stock_len / 2.54
        if is_turning_setup(setup):
            if 'chuck_position' in wcs_data and 'stock_z_high' in wcs_data:
                stickout = wcs_data['stock_z_high'] - wcs_data['chuck_position']
                if stickout > 0:
                    wcs_data['stickout'] = math.ceil(stickout * 2) / 2
    except Exception:
        if 'gcode' not in wcs_data:
            wcs_data['gcode'] = "G54"
    return wcs_data


def get_stock_wcs_bounds(setup):
    """Get stock dimensions and bounding box in WCS coordinates (inches).

    Projects the 8 corners of the stock solid's model-space AABB onto
    the WCS axes to get an oriented bounding box.
    """
    try:
        wcs_result = _decompose_wcs(setup)
        stock = getattr(setup, 'stockSolid', None)
        if not wcs_result or not stock:
            return None
        origin, xd, yd, zd = wcs_result
        bb = stock.boundingBox
        min_p = bb.minPoint
        max_p = bb.maxPoint
        # 8 corners of model-space AABB
        corners = [(x, y, z)
                    for x in (min_p.x, max_p.x)
                    for y in (min_p.y, max_p.y)
                    for z in (min_p.z, max_p.z)]
        # Project each corner into WCS
        wxs, wys, wzs = [], [], []
        for cx, cy, cz in corners:
            dx = cx - origin.x
            dy = cy - origin.y
            dz = cz - origin.z
            wxs.append(dx * xd.x + dy * xd.y + dz * xd.z)
            wys.append(dx * yd.x + dy * yd.y + dz * yd.z)
            wzs.append(dx * zd.x + dy * zd.y + dz * zd.z)
        # Convert cm → inches
        return {
            'stock_lower': (min(wxs) / 2.54, min(wys) / 2.54, min(wzs) / 2.54),
            'stock_upper': (max(wxs) / 2.54, max(wys) / 2.54, max(wzs) / 2.54),
            'stock_size': ((max(wxs) - min(wxs)) / 2.54,
                           (max(wys) - min(wys)) / 2.54,
                           (max(wzs) - min(wzs)) / 2.54)
        }
    except Exception as e:
        log(f"Could not compute stock WCS bounds: {e}")
        return None


# ===========================================================================
# Screenshot Capture (adapted from EXPORT TO PROSHOP — returns base64)
# ===========================================================================

def _doEvents_wait(seconds):
    """Wait approximately `seconds` while keeping Fusion UI responsive.

    Splits the wait into 50ms micro-sleeps with adsk.doEvents() between each,
    so Fusion can process pending UI updates instead of showing "(Not Responding)".
    """
    iterations = max(1, int(seconds / 0.05))
    for _ in range(iterations):
        adsk.doEvents()
        time.sleep(0.05)


def capture_setup_screenshots_base64(setup, setup_idx):
    """Capture screenshots for a setup, return list of (view_name, base64) tuples.

    Also returns the temp directory path so the caller can run composite
    creation off the main thread."""
    screenshots_b64 = []
    viewport = _app.activeViewport

    try:
        setup.activate()
        _doEvents_wait(0.5)
        try:
            _ui.activeSelections.clear()
            _ui.activeSelections.add(setup)
        except Exception as e:
            log(f"Could not select setup for screenshot: {e}")
        viewport.refresh()
        _doEvents_wait(0.5)
    except Exception as e:
        log(f"Could not activate setup {setup_idx} for screenshots: {e}")

    # Get WCS axes for camera positioning
    wcs_origin = wcs_x = wcs_y = wcs_z = None
    try:
        wcs_result = _decompose_wcs(setup)
        if wcs_result:
            wcs_origin, wcs_x, wcs_y, wcs_z = wcs_result
    except Exception as e:
        log(f"Could not read WCS for setup {setup_idx}: {e}")

    viewport.fit()
    _doEvents_wait(0.3)

    base_camera = viewport.camera
    extent = base_camera.viewExtents
    cam_dist = extent * 2.0 if extent > 0 else 50.0
    target = wcs_origin if wcs_origin else base_camera.target
    has_wcs = all(v is not None for v in [wcs_origin, wcs_x, wcs_y, wcs_z])

    temp_dir = tempfile.mkdtemp(prefix="proshop_bridge_")

    if has_wcs:
        # (name, eye_direction_in_WCS, up_direction_in_WCS, orthographic?)
        views = [
            ('top',   (0, 0, 1),           (0, 1, 0), True),   # looking down -Z, Y up
            ('front', (0, -1, 0),          (0, 0, 1), True),   # looking from -Y, Z up
            ('right', (1, 0, 0),           (0, 0, 1), True),   # looking from +X, Z up
            ('iso',   (0.7, -0.5, 1.0),   (0, 0, 1), False),  # perspective ISO
        ]
        for view_name, eye_wcs, up_wcs, ortho in views:
            try:
                ex, ey, ez = eye_wcs
                eye_world_x = ex * wcs_x.x + ey * wcs_y.x + ez * wcs_z.x
                eye_world_y = ex * wcs_x.y + ey * wcs_y.y + ez * wcs_z.y
                eye_world_z = ex * wcs_x.z + ey * wcs_y.z + ez * wcs_z.z
                norm = (eye_world_x**2 + eye_world_y**2 + eye_world_z**2) ** 0.5
                if norm > 0:
                    eye_world_x = eye_world_x / norm * cam_dist
                    eye_world_y = eye_world_y / norm * cam_dist
                    eye_world_z = eye_world_z / norm * cam_dist
                ux, uy, uz = up_wcs
                up_world_x = ux * wcs_x.x + uy * wcs_y.x + uz * wcs_z.x
                up_world_y = ux * wcs_x.y + uy * wcs_y.y + uz * wcs_z.y
                up_world_z = ux * wcs_x.z + uy * wcs_y.z + uz * wcs_z.z
                camera = viewport.camera
                camera.isSmoothTransition = False
                try:
                    if ortho:
                        camera.cameraType = adsk.core.CameraTypes.OrthographicCameraType
                    else:
                        camera.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
                except Exception:
                    pass  # old Fusion versions may not support cameraType
                camera.eye = adsk.core.Point3D.create(
                    target.x + eye_world_x, target.y + eye_world_y, target.z + eye_world_z)
                camera.target = target
                camera.upVector = adsk.core.Vector3D.create(up_world_x, up_world_y, up_world_z)
                camera.isFitView = True
                viewport.camera = camera
                _doEvents_wait(0.3)
                viewport.fit()
                _doEvents_wait(0.3)
                filepath = os.path.join(temp_dir, f"s{setup_idx}_{view_name}.png")
                viewport.saveAsImageFile(filepath, SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT)
                with open(filepath, "rb") as f:
                    screenshots_b64.append((view_name, base64.b64encode(f.read()).decode("utf-8")))
            except Exception as e:
                log(f"Screenshot '{view_name}' failed for setup {setup_idx}: {e}")
    else:
        views = [
            ('top',   adsk.core.ViewOrientations.TopViewOrientation,          True),
            ('front', adsk.core.ViewOrientations.FrontViewOrientation,        True),
            ('right', adsk.core.ViewOrientations.RightViewOrientation,        True),
            ('iso',   adsk.core.ViewOrientations.IsoTopRightViewOrientation,  False),
        ]
        for view_name, orientation, ortho in views:
            try:
                camera = viewport.camera
                camera.viewOrientation = orientation
                try:
                    if ortho:
                        camera.cameraType = adsk.core.CameraTypes.OrthographicCameraType
                    else:
                        camera.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
                except Exception:
                    pass
                camera.isFitView = True
                viewport.camera = camera
                _doEvents_wait(0.3)
                viewport.fit()
                _doEvents_wait(0.3)
                filepath = os.path.join(temp_dir, f"s{setup_idx}_{view_name}.png")
                viewport.saveAsImageFile(filepath, SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT)
                with open(filepath, "rb") as f:
                    screenshots_b64.append((view_name, base64.b64encode(f.read()).decode("utf-8")))
            except Exception as e:
                log(f"Screenshot '{view_name}' (fallback) failed for setup {setup_idx}: {e}")

    # Restore the original camera so the user's view isn't left in perspective/ISO
    try:
        viewport.camera = base_camera
        _doEvents_wait(0.3)
        viewport.fit()
    except Exception as e:
        log(f"Could not restore camera after screenshots: {e}")

    # Return screenshots + temp_dir so composite can run off main thread
    return screenshots_b64, temp_dir


def _capture_single_screenshot(setup, setup_idx):
    """Capture a single ISO screenshot for audit purposes. Returns base64 string or ''."""
    viewport = _app.activeViewport
    try:
        setup.activate()
        _doEvents_wait(0.3)
        try:
            _ui.activeSelections.clear()
            _ui.activeSelections.add(setup)
        except Exception:
            pass
        viewport.refresh()
        _doEvents_wait(0.3)
    except Exception as e:
        log(f"Could not activate setup {setup_idx} for audit screenshot: {e}")
        return ""

    wcs_origin = wcs_x = wcs_y = wcs_z = None
    try:
        wcs_result = _decompose_wcs(setup)
        if wcs_result:
            wcs_origin, wcs_x, wcs_y, wcs_z = wcs_result
    except Exception:
        pass

    viewport.fit()
    _doEvents_wait(0.2)

    base_camera = viewport.camera
    extent = base_camera.viewExtents
    cam_dist = extent * 2.0 if extent > 0 else 50.0
    target = wcs_origin if wcs_origin else base_camera.target
    has_wcs = all(v is not None for v in [wcs_origin, wcs_x, wcs_y, wcs_z])

    try:
        camera = viewport.camera
        camera.isSmoothTransition = False
        if has_wcs:
            ex, ey, ez = 0.7, -0.5, 1.0  # ISO view
            eye_world_x = ex * wcs_x.x + ey * wcs_y.x + ez * wcs_z.x
            eye_world_y = ex * wcs_x.y + ey * wcs_y.y + ez * wcs_z.y
            eye_world_z = ex * wcs_x.z + ey * wcs_y.z + ez * wcs_z.z
            norm = (eye_world_x**2 + eye_world_y**2 + eye_world_z**2) ** 0.5
            if norm > 0:
                eye_world_x = eye_world_x / norm * cam_dist
                eye_world_y = eye_world_y / norm * cam_dist
                eye_world_z = eye_world_z / norm * cam_dist
            ux, uy, uz = 0, 0, 1  # Z-up for ISO
            up_world_x = ux * wcs_x.x + uy * wcs_y.x + uz * wcs_z.x
            up_world_y = ux * wcs_x.y + uy * wcs_y.y + uz * wcs_z.y
            up_world_z = ux * wcs_x.z + uy * wcs_y.z + uz * wcs_z.z
            try:
                camera.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
            except Exception:
                pass
            camera.eye = adsk.core.Point3D.create(
                target.x + eye_world_x, target.y + eye_world_y, target.z + eye_world_z)
            camera.target = target
            camera.upVector = adsk.core.Vector3D.create(up_world_x, up_world_y, up_world_z)
        else:
            camera.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
            try:
                camera.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
            except Exception:
                pass
        camera.isFitView = True
        viewport.camera = camera
        _doEvents_wait(0.3)
        viewport.fit()
        _doEvents_wait(0.2)

        temp_path = os.path.join(tempfile.gettempdir(), f"audit_s{setup_idx}.png")
        viewport.saveAsImageFile(temp_path, 480, 270)  # smaller for audit
        with open(temp_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        try:
            os.remove(temp_path)
        except Exception:
            pass
        # Restore the original camera so the user's view isn't left in perspective/ISO
        try:
            viewport.camera = base_camera
            _doEvents_wait(0.3)
            viewport.fit()
        except Exception:
            pass
        return b64
    except Exception as e:
        log(f"Audit screenshot failed for setup {setup_idx}: {e}")
        # Restore the original camera even on failure
        try:
            viewport.camera = base_camera
            _doEvents_wait(0.3)
            viewport.fit()
        except Exception:
            pass
        return ""


def _composite_and_cleanup(screenshots_b64, temp_dir, setup_idx):
    """Create composite 2x2 grid image and clean up temp files.

    Runs on a background thread — no Fusion API calls, just file I/O
    and PowerShell subprocess.  Returns the final screenshots list.
    """
    if len(screenshots_b64) == 4:
        png_paths = {}
        for vname, _ in screenshots_b64:
            png_paths[vname] = os.path.join(temp_dir, f"s{setup_idx}_{vname}.png")
        all_exist = all(os.path.exists(p) for p in png_paths.values())
        ps_script = os.path.join(os.path.dirname(__file__), "composite_screenshots.ps1")
        if all_exist and os.path.exists(ps_script):
            composite_path = os.path.join(temp_dir, f"s{setup_idx}_composite.jpg")
            try:
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script,
                     "-topPng", png_paths.get("top", ""),
                     "-frontPng", png_paths.get("front", ""),
                     "-rightPng", png_paths.get("right", ""),
                     "-isoPng", png_paths.get("iso", ""),
                     "-outputPath", composite_path],
                    capture_output=True, text=True, timeout=15,
                    creationflags=0x08000000  # CREATE_NO_WINDOW
                )
                if result.returncode == 0 and os.path.exists(composite_path):
                    with open(composite_path, "rb") as f:
                        composite_b64 = base64.b64encode(f.read()).decode("utf-8")
                    screenshots_b64 = [("composite", composite_b64)]
                    log(f"Created composite screenshot for setup {setup_idx}")
                else:
                    log(f"Composite failed (rc={result.returncode}): {result.stderr[:200]}")
            except Exception as e:
                log(f"Composite error: {e}")

    # Clean up temp files
    try:
        import glob as _glob
        for f in _glob.glob(os.path.join(temp_dir, "*")):
            try:
                os.remove(f)
            except Exception:
                pass
        os.rmdir(temp_dir)
    except Exception:
        pass
    return screenshots_b64


# ===========================================================================
# Sequence Details Generation (from proshop_gui_v1_5.py)
# ===========================================================================

def generate_sequence_details(setup_data):
    tools_list = []
    for i, op in enumerate(setup_data.get("operations", []), 1):
        tool = op.get("tool", {}) or {}
        tool_id = tool.get("product_id", "") or ""
        if not tool_id or tool_id == "-":
            tool_id = tool.get("description", "") or ""
        if not tool_id or tool_id == "-":
            tool_id = tool.get("comment", "") or ""
        if not tool_id:
            tool_id = "-"
        tool_id = tool_id.replace(" ", "_").replace("/", "-")
        tool_body = tool_id
        tool_insert = ""
        if "-" in tool_id:
            parts = tool_id.split("-", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                if parts[1][0:1].upper() == 'T' or parts[1][0:2].upper() in ['IC', 'CN', 'DN', 'SN', 'TN', 'VN', 'WN']:
                    tool_body = parts[0]
                    tool_insert = parts[1]
        ooh = tool.get("body_length", 0) or 0
        if ooh > 0:
            ooh = ooh / 2.54
        holder = tool.get("holder_description", "") or tool.get("holder_id", "") or "-"
        holder = holder.replace(" ", "_") if holder else "-"
        tool_number = tool.get("number")
        desc = op.get("name", "")
        if tool_number is not None:
            desc = f"T{int(tool_number)}: {desc}"
        tool_data = {
            "sequenceNumber": str(i),
            "tool": tool_body,
            "outOfHolder": f"{ooh:.4f}" if isinstance(ooh, (int, float)) else str(ooh),
            "holder": holder if holder else "-",
            "sequenceDescription": desc
        }
        if tool_insert:
            tool_data["gTypeInsert"] = tool_insert
        tools_list.append(tool_data)
    return tools_list


# ===========================================================================
# Written Description HTML Generation
# ===========================================================================

def generate_written_description_html(setup_data, setup_index, screenshots_b64, doc_name=None):
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    html = []
    program_num = setup_data.get("program_number", f"O{setup_index}")
    program_comment = setup_data.get("program_comment", "")
    if program_comment:
        display_name = program_comment
    elif doc_name:
        display_name = doc_name.replace('.f3d', '').replace('_', ' ')
    else:
        display_name = setup_data.get("name", "")
    wcs_data = setup_data.get("wcs", {})
    wcs_gcode = wcs_data.get("gcode", "G54")
    origin_mode = wcs_data.get("origin_mode", "")
    box_point = wcs_data.get("box_point", "")
    # Build WCS display: "G56 — Model Point, Top Center"
    wcs_detail_parts = []
    if origin_mode:
        wcs_detail_parts.append(origin_mode)
    if box_point:
        wcs_detail_parts.append(box_point)
    wcs_detail = ", ".join(wcs_detail_parts)
    wcs_display = f"{wcs_gcode} &mdash; {wcs_detail}" if wcs_detail else wcs_gcode
    stickout = wcs_data.get("stickout")

    # --- Header table ---
    td_style = "padding:2px 8px 2px 0;"
    html.append(f"<table style='border-collapse:collapse; margin-bottom:10px;'>")
    html.append(f"<tr><td style='{td_style}'><strong>Program:</strong></td><td>{program_num}</td></tr>")
    html.append(f"<tr><td style='{td_style}'><strong>Name:</strong></td><td>{display_name}</td></tr>")
    html.append(f"<tr><td style='{td_style}'><strong>WCS:</strong></td><td>{wcs_display}</td></tr>")
    if stickout is not None:
        html.append(f"<tr><td style='{td_style}'><strong>Material Stick Out:</strong></td><td>{stickout:.3f}\"</td></tr>")

    # Stock dimensions
    stock_bounds = setup_data.get("stock_bounds")
    if stock_bounds:
        sz = stock_bounds['stock_size']
        html.append(f"<tr><td style='{td_style}'><strong>Stock Size:</strong></td>"
                     f"<td>DX={sz[0]:.4f}\" DY={sz[1]:.4f}\" DZ={sz[2]:.4f}\"</td></tr>")

    # Setup notes
    setup_notes = setup_data.get("setup_notes", "")
    if setup_notes:
        html.append(f"<tr><td style='{td_style}'><strong>Notes:</strong></td><td>{setup_notes}</td></tr>")

    # Total machining time
    total_time = setup_data.get("total_machining_time")
    if total_time is not None and total_time > 0:
        mins = int(total_time)
        secs = int((total_time - mins) * 60)
        html.append(f"<tr><td style='{td_style}'><strong>Est. Machining Time:</strong></td>"
                     f"<td>{mins}m {secs}s</td></tr>")

    html.append("</table>")

    # --- Setup transition visual (Before→After orientation cubes) ---
    transition = setup_data.get("transition")
    if transition:
        transition_html = _render_transition_visual(transition)
        if transition_html:
            html.append(transition_html)

    html.append(f"<p><em>Auto-generated from Fusion 360 - {timestamp}</em></p>")
    html.append("<hr>")

    # --- Screenshots ---
    if screenshots_b64:
        if len(screenshots_b64) == 1 and screenshots_b64[0][0] == "composite":
            # Single composite image (2x2 grid with labels baked in)
            _, b64 = screenshots_b64[0]
            html.append(f'<img src="data:image/jpeg;base64,{b64}" '
                        f'style="width:100%; max-width:1920px;" alt="Setup Views">')
        else:
            # Fallback: separate images in a grid
            VIEW_LABELS = {
                "top": "TOP VIEW", "front": "FRONT VIEW", "iso": "ISO VIEW",
                "right": "RIGHT VIEW",
            }
            for item in screenshots_b64:
                if isinstance(item, tuple):
                    view_name, b64 = item
                else:
                    view_name, b64 = "", item
                label = VIEW_LABELS.get(view_name, view_name.upper().replace("_", " ") if view_name else "")
                html.append(f'<div style="display:inline-block; max-width:48%; margin:1%; vertical-align:top;">')
                if label:
                    html.append(f'  <p style="margin:2px 0; font-weight:bold; font-size:11px;">{label}</p>')
                html.append(f'  <img src="data:image/png;base64,{b64}" '
                            f'style="width:100%;" alt="{label or "View"}">')
                html.append(f'</div>')
        html.append("<hr>")

    # --- Tool List table ---
    operations = setup_data.get("operations", [])
    turning = setup_data.get("is_turning", False)
    if operations:
        th = "padding:4px 8px; text-align:left; border-bottom:2px solid #999;"
        tc = "padding:4px 8px; border-bottom:1px solid #ddd;"
        ncols = 3 if turning else 5  # turning: T# | Description | Vendor/Product
        html.append("<p><strong>Tool List:</strong></p>")
        html.append(f'<table style="border-collapse:collapse; width:100%; margin-bottom:10px;">')
        html.append(f'<tr style="background:#f0f0f0;">')
        html.append(f'  <th style="{th}">T#</th>')
        html.append(f'  <th style="{th}">Description</th>')
        if not turning:
            html.append(f'  <th style="{th} text-align:center;">Dia</th>')
            html.append(f'  <th style="{th} text-align:center;">Flutes</th>')
        html.append(f'  <th style="{th}">Vendor / Product ID</th>')
        html.append(f'</tr>')
        for op in operations:
            tool = op.get("tool", {}) or {}
            if op.get("is_manual_nc"):
                op_name = op.get("name", "")
                mc = op.get("manual_nc_comment", "")
                note = f" &mdash; {mc}" if mc else ""
                html.append(f'<tr style="background:#fffacd;">')
                html.append(f'  <td style="{tc}">&mdash;</td>')
                html.append(f'  <td style="{tc}" colspan="{ncols - 1}">{op_name}{note}</td>')
                html.append(f'</tr>')
                continue
            tool_num = tool.get("number", "?")
            tn = int(tool_num) if tool_num is not None and tool_num != "?" else "?"
            desc = tool.get("description", "") or tool.get("comment", "") or op.get("name", "") or "-"
            vendor = tool.get("vendor", "") or ""
            product = tool.get("product_id", "") or ""
            if vendor and product:
                vp = f"({vendor.upper()}) {product}"
            elif product:
                vp = product
            elif vendor:
                vp = vendor
            else:
                vp = "-"
            html.append(f'<tr>')
            html.append(f'  <td style="{tc}">T{tn}</td>')
            html.append(f'  <td style="{tc}">{desc}</td>')
            if not turning:
                dia_cm = tool.get("diameter")
                dia_str = f'{dia_cm / 2.54:.4f}"' if dia_cm and dia_cm > 0 else "-"
                flutes = tool.get("number_of_flutes")
                flutes_str = str(int(flutes)) if isinstance(flutes, (int, float)) and flutes > 0 else "-"
                html.append(f'  <td style="{tc} text-align:center;">{dia_str}</td>')
                html.append(f'  <td style="{tc} text-align:center;">{flutes_str}</td>')
            html.append(f'  <td style="{tc}">{vp}</td>')
            html.append(f'</tr>')
        html.append(f'</table>')

    return "\n".join(html)


# ===========================================================================
# Push Functions
# ===========================================================================

def push_sequence_details(part_number, op_number, tools_list):
    mutation = """
    mutation($partNumber: String!, $opNumber: String!, $tools: [UpdatePartOperationToolInput!]!) {
      updatePart(partNumber: $partNumber, data: {
        operations: [{
          selector: { field: opNumber, value: $opNumber },
          data: { tools: $tools }
        }]
      }) { partNumber }
    }
    """
    # Push one tool at a time so ProShop creates rows in sequential order
    last_result = None
    for i, t in enumerate(tools_list):
        td = {
            "tool": t.get("tool", ""),
            "outOfHolder": str(t.get("outOfHolder", "")),
            "holder": t.get("holder", ""),
            "sequenceDescription": t.get("sequenceDescription", "")
        }
        if t.get("gTypeInsert"):
            td["gTypeInsert"] = t["gTypeInsert"]
        tool_input = [{
            "selector": {"field": "sequenceNumber", "value": str(t.get("sequenceNumber", "1"))},
            "data": td
        }]
        last_result = graphql_query(mutation, {"partNumber": part_number, "opNumber": op_number, "tools": tool_input})
        if "errors" in last_result:
            log(f"  Seq detail #{i+1} FAILED: {json.dumps(last_result['errors'][:1])}")
            return last_result
    return last_result


def _start_oneshot_server(html_content, marker_id, timeout=120):
    """Start a localhost HTTP server that serves html_content until timeout.

    Serves multiple requests because the Tampermonkey script may fetch twice:
    once before clicking CHECKOUT and again after ProShop reloads the page.
    """

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET')
            self.end_headers()
        def log_message(self, format, *args):
            pass  # suppress console noise

    server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
    port = server.server_address[1]
    log(f"One-shot server on port {port} for bridge {marker_id}")

    def run():
        # Serve until timeout expires (multiple fetches allowed)
        deadline = time.time() + timeout
        while time.time() < deadline:
            server.timeout = 1
            server.handle_request()
        server.server_close()
        log(f"One-shot server on port {port} shut down")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return port


def push_written_description_via_clipboard(part_number, op_number, html_content):
    marker_id = str(uuid.uuid4())[:8]
    marked_html = f"<!--PROSHOP_BRIDGE:{marker_id}-->\n{html_content}"

    # Start one-shot localhost server for Tampermonkey to fetch via GM_xmlhttpRequest
    try:
        port = _start_oneshot_server(marked_html, marker_id)
    except Exception as e:
        return False, f"Failed to start local server: {e}"

    customer = part_number.split("-")[0] if "-" in part_number else part_number
    url = (f"https://{PROSHOP_HOST}/procnc/parts/{customer}/{part_number}"
           f"?formName=writtenDescription&opId={op_number}"
           f"&psBridge={marker_id}&bridgePort={port}")
    log(f"Opening browser: {url}")
    # Find Chrome and open in a new window to avoid tab reuse
    chrome_paths = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    chrome_exe = next((p for p in chrome_paths if os.path.exists(p)), None)
    try:
        if chrome_exe:
            subprocess.Popen([chrome_exe, "--new-window", url],
                             creationflags=0x08000000)
        else:
            # Fallback: quote URL for cmd.exe (& is a command separator)
            subprocess.Popen(f'cmd /c start "" "{url}"',
                             creationflags=0x08000000)
    except Exception as e:
        log(f"Browser open failed: {e}")
        try:
            os.startfile(url)
        except Exception as e2:
            log(f"os.startfile also failed: {e2}")
    return True, f"Opened browser for {part_number} Op {op_number}"


# ===========================================================================
# Selenium Sequence Detail Helper
# ===========================================================================

def _find_system_python():
    """Find system Python 3.x executable (not Fusion's embedded Python)."""
    candidates = [
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs",
                     "Python", "Python314", "python.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs",
                     "Python", "Python313", "python.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs",
                     "Python", "Python312", "python.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # Try py launcher
    try:
        result = subprocess.run(["py", "-3", "-c", "import sys; print(sys.executable)"],
                                capture_output=True, text=True, timeout=5,
                                creationflags=0x08000000)
        if result.returncode == 0:
            exe = result.stdout.strip()
            if os.path.exists(exe):
                return exe
    except Exception:
        pass
    return None


def _run_selenium_sequence_fix(part_number, op_number):
    """Run Selenium helper subprocess to sort rows + fill G-Code Tool # on ProShop page.
    Returns True on success, False on failure."""
    selenium_helper = os.path.join(os.path.dirname(__file__), "proshop_selenium_helper.py")
    python_exe = _find_system_python()
    if not os.path.exists(selenium_helper):
        log(f"Selenium helper not found: {selenium_helper}")
        return False
    if not python_exe:
        log("System Python not found — skipping Selenium sequence fix")
        return False
    try:
        result = subprocess.run(
            [python_exe, selenium_helper,
             "--part-number", str(part_number),
             "--op-number", str(op_number)],
            capture_output=True, text=True, timeout=120,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        for line in result.stdout.strip().splitlines():
            log(f"  [selenium] {line}")
        if result.returncode == 0:
            log(f"Selenium sequence fix OK for {part_number} Op {op_number}")
            return True
        else:
            log(f"Selenium sequence fix FAILED (rc={result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    log(f"  [selenium/stderr] {line}")
            return False
    except subprocess.TimeoutExpired:
        log("Selenium helper timed out (120s)")
        return False
    except Exception as e:
        log(f"Selenium helper error: {e}")
        return False


def _run_selenium_written_desc(part_number, op_number, html_content):
    """Run Selenium helper to set written description via CKEditor.
    HTML content is passed via stdin. Returns (True, msg) or (False, msg)."""
    selenium_helper = os.path.join(os.path.dirname(__file__), "proshop_selenium_helper.py")
    python_exe = _find_system_python()
    if not os.path.exists(selenium_helper):
        return False, f"Selenium helper not found: {selenium_helper}"
    if not python_exe:
        return False, "System Python not found"
    try:
        result = subprocess.run(
            [python_exe, selenium_helper,
             "--mode", "written-description",
             "--part-number", str(part_number),
             "--op-number", str(op_number)],
            input=html_content,
            capture_output=True, text=True, timeout=360,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        for line in result.stdout.strip().splitlines():
            log(f"  [selenium-wd] {line}")
        if result.returncode == 0:
            log(f"Selenium written desc OK for {part_number} Op {op_number}")
            return True, "Written description set via Selenium"
        else:
            log(f"Selenium written desc FAILED (rc={result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    log(f"  [selenium-wd/stderr] {line}")
            return False, f"Selenium failed (rc={result.returncode})"
    except subprocess.TimeoutExpired:
        log("Selenium written desc timed out (360s)")
        return False, "Selenium timed out"
    except Exception as e:
        log(f"Selenium written desc error: {e}")
        return False, str(e)


# ===========================================================================
# Full Push Orchestrator
# ===========================================================================

def _start_push(mappings, push_flags=None):
    """Initialize push state and begin first setup extraction (main thread)."""
    global _push_state
    cam = get_cam_product()
    if not cam:
        _send_response("pushProgress", {"status": "error", "message": "No CAM data in document"})
        _send_response("pushComplete", {"results": []})
        return
    doc_name = ""
    try:
        doc_name = _app.activeDocument.name
    except Exception as e:
        log(f"Could not get document name: {e}")
    _push_state = {
        "mappings": mappings,
        "current": 0,
        "cam": cam,
        "doc_name": doc_name,
        "results": [],
        "push_flags": push_flags or {"push_sequence": True, "push_written": True}
    }

    # Save part number to document attributes so TraxisPostProcessor can use it
    # Uses the first mapping's part number (all mappings share the same part)
    if mappings:
        part_num = mappings[0].get("part_number", "")
        if part_num:
            try:
                doc = _app.activeDocument
                if doc:
                    doc.attributes.add('ProShopBridge', 'PartNumber', part_num)
                    doc.attributes.add('Traxis', 'PartNumber', part_num)
                    log(f"Saved part number to document: {part_num}")
            except Exception as e:
                log(f"Could not save part number attribute: {e}")

    _process_next_setup()


def _process_next_setup():
    """Extract CAM data on main thread, then hand off HTTP push to background thread."""
    global _push_state
    if not _push_state:
        return
    idx = _push_state["current"]
    mappings = _push_state["mappings"]
    total = len(mappings)
    if idx >= total:
        _send_response("pushComplete", {"results": _push_state["results"]})
        _push_state = None
        return

    mapping = mappings[idx]
    cam = _push_state["cam"]
    doc_name = _push_state["doc_name"]
    push_flags = _push_state.get("push_flags", {"push_sequence": True, "push_written": True})
    setup_idx = mapping["setup_index"]
    part_number = mapping["part_number"]
    op_number = mapping["op_number"]

    if setup_idx >= cam.setups.count:
        _push_state["results"].append({"setup_index": setup_idx, "success": False, "error": "Setup not found"})
        _push_state["current"] += 1
        _process_next_setup()
        return

    setup = cam.setups.item(setup_idx)

    # --- Main thread: extract CAM data + screenshots (requires Fusion API) ---
    _send_response("pushProgress", {"status": "extracting", "current": idx + 1,
                                     "total": total, "setup_name": setup.name})
    adsk.doEvents()

    wcs_info = get_wcs_info(setup)

    # Decompose WCS for transition description
    wcs_result = None
    try:
        wcs_result = _decompose_wcs(setup)
    except Exception as e:
        log(f"Could not decompose WCS: {e}")

    # Compute setup transition from the previous setup in the CAM document
    transition_info = None
    if wcs_result and setup_idx > 0:
        try:
            prev_setup = cam.setups.item(setup_idx - 1)
            prev_wcs = _decompose_wcs(prev_setup)
            if prev_wcs:
                # Debug: log raw WCS axes for both setups
                def _fmt_vec(v):
                    return f"({v.x:.3f}, {v.y:.3f}, {v.z:.3f})"
                po, px, py, pz = prev_wcs
                co, cx, cy, cz = wcs_result
                log(f"  WCS prev '{prev_setup.name}': X={_fmt_vec(px)} Y={_fmt_vec(py)} Z={_fmt_vec(pz)}")
                log(f"  WCS curr '{setup.name}':      X={_fmt_vec(cx)} Y={_fmt_vec(cy)} Z={_fmt_vec(cz)}")
                transition_info = _describe_setup_transition(prev_wcs, wcs_result)
                if transition_info:
                    log(f"  Setup transition: {transition_info['text']}")
                    if transition_info.get('face_map'):
                        log(f"  Face map: {transition_info['face_map']}")
        except Exception as e:
            log(f"  Could not compute setup transition: {e}")

    stock_bounds = get_stock_wcs_bounds(setup)

    setup_data = {
        "name": setup.name,
        "program_number": "",
        "program_comment": "",
        "operations": [],
        "stock": get_stock_info(setup),
        "stock_bounds": stock_bounds,
        "wcs": wcs_info,
        "setup_notes": "",
        "total_machining_time": None,
        "is_turning": is_turning_setup(setup),
        "transition": transition_info
    }
    try:
        pn = setup.parameters.itemByName('job_programName')
        if pn:
            val = pn.expression.strip("'\"")
            setup_data["program_number"] = f"O{val}" if val.isdigit() else val
    except Exception as e:
        log(f"Could not read program name: {e}")
    try:
        pc = setup.parameters.itemByName('job_programComment')
        if pc:
            setup_data["program_comment"] = pc.expression.strip("'\"")
    except Exception as e:
        log(f"Could not read program comment: {e}")

    # Setup notes/comments
    try:
        notes_param = setup.parameters.itemByName('job_description')
        if notes_param:
            notes_val = notes_param.expression
            if notes_val:
                if (notes_val.startswith("'") and notes_val.endswith("'")) or \
                   (notes_val.startswith('"') and notes_val.endswith('"')):
                    notes_val = notes_val[1:-1]
                setup_data["setup_notes"] = notes_val
    except Exception as e:
        log(f"Could not read setup notes: {e}")

    op_seq = 1
    total_time = 0.0
    for op in get_all_operations(setup):
        op_data = extract_operation_data(op, op_seq)
        if op_data:
            setup_data["operations"].append(op_data)
            op_seq += 1
            # Accumulate machining time from operation
            try:
                if hasattr(op, 'parameters'):
                    time_param = op.parameters.itemByName('machiningTime')
                    if time_param:
                        t_val = time_param.value
                        t = float(t_val.value) if hasattr(t_val, 'value') else float(t_val)
                        if t > 0:
                            total_time += t
            except Exception:
                pass
    if total_time > 0:
        setup_data["total_machining_time"] = total_time

    _send_response("pushProgress", {"status": "screenshots", "current": idx + 1,
                                     "total": total, "setup_name": setup.name})
    adsk.doEvents()
    screenshots_b64, temp_dir = capture_setup_screenshots_base64(setup, setup_idx)

    # --- Background thread: composite + HTTP push + Tampermonkey wait (no Fusion API) ---
    def _bg_push():
        # Create composite image from individual screenshots (runs PowerShell)
        final_screenshots = _composite_and_cleanup(screenshots_b64, temp_dir, setup_idx)

        tools_list = generate_sequence_details(setup_data)
        seq_ok = True
        seq_skipped = False
        wd_ok = True
        wd_skipped = False
        wd_msg = ""

        # --- Sequence Details ---
        if push_flags.get("push_sequence", True):
            _send_from_thread("pushProgress", {"status": "pushing_sequence", "current": idx + 1,
                                                "total": total, "setup_name": setup.name})
            seq_result = None
            if tools_list:
                log(f"Pushing sequence details: {len(tools_list)} tools to {part_number} Op {op_number}")
                log(f"  Sequence payload sample: {json.dumps(tools_list[0]) if tools_list else 'empty'}")
                seq_result = push_sequence_details(part_number, op_number, tools_list)
                if seq_result:
                    if "errors" in seq_result:
                        log(f"  Sequence push ERRORS: {json.dumps(seq_result['errors'])}")
                    else:
                        log(f"  Sequence push OK: {json.dumps(seq_result.get('data', {}))}")
                else:
                    log(f"  Sequence push returned None")
            else:
                log(f"No tools to push for sequence details (tools_list empty)")
            seq_ok = seq_result and "errors" not in seq_result

            # Run Selenium helper to sort rows + fill G-Code Tool # on ProShop page
            selenium_ok = False
            if seq_ok and tools_list:
                _send_from_thread("pushProgress", {"status": "fixing_sequence_page", "current": idx + 1,
                                                    "total": total, "setup_name": setup.name})
                selenium_ok = _run_selenium_sequence_fix(part_number, op_number)
        else:
            seq_skipped = True
            selenium_ok = False
            log(f"Skipping sequence details push (checkbox unchecked)")

        # --- Written Description ---
        if push_flags.get("push_written", True):
            _send_from_thread("pushProgress", {"status": "pushing_written", "current": idx + 1,
                                                "total": total, "setup_name": setup.name})
            html_content = generate_written_description_html(
                setup_data, setup_idx + 1, final_screenshots, doc_name)
            wd_ok, wd_msg = _run_selenium_written_desc(part_number, op_number, html_content)
        else:
            wd_skipped = True
            log(f"Skipping written description push (checkbox unchecked)")

        result = {
            "setup_index": setup_idx, "setup_name": setup.name,
            "part_number": part_number, "op_number": op_number,
            "sequence_ok": seq_ok, "sequence_skipped": seq_skipped,
            "selenium_ok": selenium_ok,
            "written_ok": wd_ok, "written_skipped": wd_skipped,
            "tools_count": len(tools_list) if not seq_skipped else 0,
            "screenshots_count": len(final_screenshots),
            "message": wd_msg
        }

        # Signal main thread to advance to next setup
        _push_result_queue.put(result)
        try:
            _app.fireCustomEvent(PUSH_NEXT_EVENT_ID, "")
        except Exception as e:
            log(f"Failed to fire push-next event: {e}")

    threading.Thread(target=_bg_push, daemon=True).start()


# ===========================================================================
# Fusion 360 Command & Palette Handlers
# ===========================================================================

def _send_response(action, data):
    try:
        if _palette:
            data_str = json.dumps(data)
            _palette.sendInfoToHTML(action, data_str)
            log(f"Sent: {action} ({len(data_str)} bytes)")
    except Exception as e:
        log(f"_send_response error: {e}")


def _send_from_thread(action, data):
    """Thread-safe: queue response and fire custom event for main-thread delivery."""
    _response_queue.put((action, data))
    try:
        _app.fireCustomEvent(RESPONSE_EVENT_ID, "")
    except Exception as e:
        log(f"fireCustomEvent error: {e}")


class ResponseEventHandler(adsk.core.CustomEventHandler):
    """Delivers queued responses to the palette on the main thread."""
    def notify(self, args):
        while not _response_queue.empty():
            try:
                action, data = _response_queue.get_nowait()
                if _palette:
                    data_str = json.dumps(data)
                    _palette.sendInfoToHTML(action, data_str)
                    log(f"Sent (queued): {action} ({len(data_str)} bytes)")
            except queue.Empty:
                break
            except Exception as e:
                log(f"ResponseEventHandler error: {e}")


class PushNextEventHandler(adsk.core.CustomEventHandler):
    """Handles background push completion, advances to next setup on main thread."""
    def notify(self, args):
        global _push_state
        try:
            while not _push_result_queue.empty():
                try:
                    result = _push_result_queue.get_nowait()
                    if _push_state:
                        _push_state["results"].append(result)
                        _push_state["current"] += 1
                except queue.Empty:
                    break
            _process_next_setup()
        except Exception as e:
            log(f"PushNextEventHandler error: {e}\n{traceback.format_exc()}")


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            global _palette
            palettes = _ui.palettes
            _palette = palettes.itemById(PALETTE_ID)
            if not _palette:
                html_path = os.path.join(os.path.dirname(__file__), "palette.html").replace("\\", "/")
                _palette = palettes.add(PALETTE_ID, PALETTE_NAME, html_path,
                                        True, True, True, 450, 750)
                _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
                onHTMLEvent = HTMLEventHandler()
                _palette.incomingFromHTML.add(onHTMLEvent)
                _handlers.append(onHTMLEvent)
                onClose = PaletteCloseHandler()
                _palette.closed.add(onClose)
                _handlers.append(onClose)
            else:
                _palette.isVisible = True
        except Exception:
            log(traceback.format_exc())


class HTMLEventHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            html_args = adsk.core.HTMLEventArgs.cast(args)
            action = html_args.action
            data_str = html_args.data
            log(f"Action: {action}")

            # WO browser actions (background threads)
            if action == "fetchWorkOrders":
                params = json.loads(data_str) if data_str else {}
                year = params.get("year", None)
                def _bg(y=year):
                    try:
                        result = fetch_work_orders(y)
                        _send_from_thread("fetchWorkOrdersResponse", result)
                    except Exception as ex:
                        _send_from_thread("fetchWorkOrdersResponse", {"errors": [{"message": str(ex)}]})
                threading.Thread(target=_bg, daemon=True).start()

            elif action == "fetchMultiYearWorkOrders":
                def _bg():
                    try:
                        result = fetch_multi_year_work_orders()
                        _send_from_thread("fetchMultiYearWorkOrdersResponse", result)
                    except Exception as ex:
                        _send_from_thread("fetchMultiYearWorkOrdersResponse", {"errors": [{"message": str(ex)}]})
                threading.Thread(target=_bg, daemon=True).start()

            elif action == "fetchSingleWO":
                params = json.loads(data_str)
                wo_num = params.get("workOrderNumber", "")
                def _bg(wn=wo_num):
                    try:
                        result = fetch_single_wo(wn)
                        _send_from_thread("fetchSingleWOResponse", result)
                    except Exception as ex:
                        _send_from_thread("fetchSingleWOResponse", {"errors": [{"message": str(ex)}]})
                threading.Thread(target=_bg, daemon=True).start()

            elif action == "openInBrowser":
                params = json.loads(data_str)
                url = params.get("url", "")
                if url:
                    webbrowser.open(url)

            elif action == "getDocumentInfo":
                doc_name, folder_name, project_name = get_document_context()
                fusion_user = get_fusion_user()
                has_cam = get_cam_product() is not None
                _send_response("getDocumentInfoResponse", {
                    "documentName": doc_name, "folderName": folder_name,
                    "projectName": project_name, "fusionUser": fusion_user,
                    "hasCAM": has_cam
                })

            elif action == "testConnection":
                def _bg():
                    try:
                        token = get_token()
                        if token:
                            _send_from_thread("testConnectionResponse", {"ok": True})
                        else:
                            _send_from_thread("testConnectionResponse", {"ok": False, "message": "Auth failed"})
                    except Exception as ex:
                        _send_from_thread("testConnectionResponse", {"ok": False, "message": str(ex)})
                threading.Thread(target=_bg, daemon=True).start()

            # CAM export actions (main thread)
            elif action == "getSetups":
                cam = get_cam_product()
                if not cam:
                    _send_response("getSetupsResponse", {"error": "No CAM data in document"})
                    return
                setups = []
                for i in range(cam.setups.count):
                    s = cam.setups.item(i)
                    prog = ""
                    try:
                        p = s.parameters.itemByName('job_programName')
                        if p:
                            prog = p.expression.strip("'\"")
                    except Exception:
                        pass
                    comment = ""
                    try:
                        c = s.parameters.itemByName('job_programComment')
                        if c:
                            comment = c.expression.strip("'\"")
                    except Exception:
                        pass
                    ops_count = len(get_all_operations(s))
                    # Read WCS axes for debugging
                    wcs_info = {}
                    try:
                        wcs_result = _decompose_wcs(s)
                        if wcs_result:
                            o, x, y, z = wcs_result
                            wcs_info = {
                                "origin": f"({o.x:.3f}, {o.y:.3f}, {o.z:.3f})",
                                "X": f"({x.x:.3f}, {x.y:.3f}, {x.z:.3f})",
                                "Y": f"({y.x:.3f}, {y.y:.3f}, {y.z:.3f})",
                                "Z": f"({z.x:.3f}, {z.y:.3f}, {z.z:.3f})"
                            }
                            log(f"Setup '{s.name}' WCS: origin={wcs_info['origin']} X={wcs_info['X']} Y={wcs_info['Y']} Z={wcs_info['Z']}")
                    except Exception as e:
                        log(f"WCS read error for '{s.name}': {e}")
                    setups.append({
                        "index": i, "name": s.name, "program": prog,
                        "programComment": comment, "operationCount": ops_count,
                        "wcs": wcs_info
                    })
                _send_response("getSetupsResponse", {"setups": setups})

            elif action == "savePartNumber":
                params = json.loads(data_str)
                part_num = params.get("partNumber", "")
                cust_pn = params.get("customerPartNumber", "")
                if part_num:
                    try:
                        doc = _app.activeDocument
                        if doc:
                            doc.attributes.add('ProShopBridge', 'PartNumber', part_num)
                            doc.attributes.add('Traxis', 'PartNumber', part_num)
                            if cust_pn:
                                doc.attributes.add('Traxis', 'CustomerPartNumber', cust_pn)
                                log(f"Part number saved: {part_num}, customer PN: {cust_pn}")
                            else:
                                log(f"Part number saved to document: {part_num}")
                    except Exception as e:
                        log(f"Could not save part number: {e}")

            elif action == "pushToProShop":
                params = json.loads(data_str)
                mappings = params.get("mappings", [])
                push_flags = {
                    "push_sequence": params.get("pushSequence", True),
                    "push_written": params.get("pushWritten", True)
                }
                _start_push(mappings, push_flags)

            elif action == "auditWCS":
                cam = get_cam_product()
                if not cam:
                    _send_response("auditWCSResponse", {"error": "No CAM data in document"})
                    return
                audit_results = []
                for i in range(cam.setups.count):
                    s = cam.setups.item(i)
                    wcs_info = get_wcs_info(s)
                    wcs_result = _decompose_wcs(s)
                    stock_bounds = get_stock_wcs_bounds(s)

                    origin_x = origin_y = origin_z = "—"
                    wcs_x_str = wcs_y_str = wcs_z_str = "—"
                    if wcs_result:
                        o, x, y, z = wcs_result
                        origin_x = f"{o.x / 2.54:.4f}"
                        origin_y = f"{o.y / 2.54:.4f}"
                        origin_z = f"{o.z / 2.54:.4f}"
                        wcs_x_str = f"({x.x:.3f}, {x.y:.3f}, {x.z:.3f})"
                        wcs_y_str = f"({y.x:.3f}, {y.y:.3f}, {y.z:.3f})"
                        wcs_z_str = f"({z.x:.3f}, {z.y:.3f}, {z.z:.3f})"

                    screenshot_b64 = _capture_single_screenshot(s, i)

                    stock_size = None
                    if stock_bounds:
                        sz = stock_bounds['stock_size']
                        stock_size = [f"{sz[0]:.4f}", f"{sz[1]:.4f}", f"{sz[2]:.4f}"]

                    audit_results.append({
                        "name": s.name,
                        "origin_x": origin_x, "origin_y": origin_y, "origin_z": origin_z,
                        "origin_mode": wcs_info.get("origin_mode", ""),
                        "box_point": wcs_info.get("box_point", ""),
                        "gcode": wcs_info.get("gcode", "G54"),
                        "stock_size": stock_size,
                        "wcs_x": wcs_x_str, "wcs_y": wcs_y_str, "wcs_z": wcs_z_str,
                        "screenshot": screenshot_b64
                    })
                    adsk.doEvents()
                _send_response("auditWCSResponse", {"setups": audit_results})

            else:
                log(f"Unknown action: {action}")

        except Exception:
            log(traceback.format_exc())


class PaletteCloseHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self, args):
        try:
            global _palette
            _palette = None
        except Exception:
            log(traceback.format_exc())


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        pass


# ===========================================================================
# Add-in lifecycle
# ===========================================================================

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if not cmd_def:
            res_folder = os.path.join(os.path.dirname(__file__), "resources")
            cmd_def = _ui.commandDefinitions.addButtonDefinition(
                CMD_ID, "ProShop Bridge",
                "ProShop Bridge — browse WOs, export CAM data, push to ProShop",
                res_folder)
        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)
        workspaces = ["CAMEnvironment", "FusionSolidEnvironment"]
        added = False
        for ws_id in workspaces:
            try:
                ws = _ui.workspaces.itemById(ws_id)
                if ws:
                    tabs = ws.toolbarTabs
                    tab = tabs.itemById("ToolsTab")
                    if not tab:
                        tab = tabs.itemById("UtilitiesTab")
                    if tab:
                        panels = tab.toolbarPanels
                        panel = panels.itemById(PANEL_ID)
                        if not panel:
                            panel = panels.add(PANEL_ID, "ProShop Bridge", "", False)
                        ctrl = panel.controls.itemById(CMD_ID)
                        if not ctrl:
                            panel.controls.addCommand(cmd_def)
                        added = True
            except Exception as e:
                log(f"Could not add to workspace {ws_id}: {e}")
        if not added:
            try:
                panel = _ui.allToolbarPanels.itemById("SolidScriptsAddinsPanel")
                if panel:
                    ctrl = panel.controls.itemById(CMD_ID)
                    if not ctrl:
                        panel.controls.addCommand(cmd_def)
            except Exception as e:
                log(f"Could not add to fallback panel: {e}")
        # Register custom events for thread-safe communication
        resp_event = _app.registerCustomEvent(RESPONSE_EVENT_ID)
        resp_handler = ResponseEventHandler()
        resp_event.add(resp_handler)
        _handlers.append(resp_handler)

        push_event = _app.registerCustomEvent(PUSH_NEXT_EVENT_ID)
        push_handler = PushNextEventHandler()
        push_event.add(push_handler)
        _handlers.append(push_handler)

        log("ProShop Bridge add-in started")
    except Exception as e:
        if _ui:
            _ui.messageBox(f"ProShop Bridge failed to start:\n{traceback.format_exc()}")


def stop(context):
    global _handlers
    try:
        palettes = _ui.palettes
        pal = palettes.itemById(PALETTE_ID)
        if pal:
            pal.deleteMe()
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        workspaces = ["CAMEnvironment", "FusionSolidEnvironment"]
        for ws_id in workspaces:
            try:
                ws = _ui.workspaces.itemById(ws_id)
                if ws:
                    tabs = ws.toolbarTabs
                    for tab_id in ["ToolsTab", "UtilitiesTab"]:
                        tab = tabs.itemById(tab_id)
                        if tab:
                            panel = tab.toolbarPanels.itemById(PANEL_ID)
                            if panel:
                                panel.deleteMe()
            except Exception:
                pass  # OK if workspace cleanup fails during shutdown
        try:
            _app.unregisterCustomEvent(RESPONSE_EVENT_ID)
        except Exception:
            pass
        try:
            _app.unregisterCustomEvent(PUSH_NEXT_EVENT_ID)
        except Exception:
            pass
        _handlers = []
        log("ProShop Bridge add-in stopped")
    except Exception as e:
        if _ui:
            _ui.messageBox(f"ProShop Bridge stop error:\n{traceback.format_exc()}")
