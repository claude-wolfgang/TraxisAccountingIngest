"""
SetupNamingPreview — Fusion 360 Add-In
Version: 1.0.0

Dry-run tool for the PART:OP setup naming convention.
Click the button, see what would change, then Apply or Cancel.

Completely standalone — does not modify or depend on TraxisCapture.
"""

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import re
import os
import json

# ---------------------------------------------------------------------------
# Config (self-contained — reads same config file as TraxisCapture if present,
# otherwise uses defaults)
# ---------------------------------------------------------------------------

ADDIN_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Try to load TraxisCapture's config for consistency
_CAPTURE_CONFIG = os.path.join(
    os.path.dirname(ADDIN_FOLDER), "TraxisCapture", "capture_config.json")

_cfg = {}
for cfg_path in [_CAPTURE_CONFIG, os.path.join(ADDIN_FOLDER, "config.json")]:
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                _cfg = json.load(f)
            break
        except Exception:
            pass

OP_START = _cfg.get("op_start_number", 60)
OP_INCREMENT = _cfg.get("op_increment", 10)
NAMING_RE = re.compile(_cfg.get("naming_pattern", r"^[A-Z0-9_-]+:\d+$"))
SKIP_KEYWORDS = _cfg.get("skip_keywords",
    ["fixture", "soft jaw", "softjaw", "jaws", "workholding", "vise"])
PART_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _cfg.get(
    "part_number_patterns", [
        r"^(\d{2,5}-\d{3,5})",
        r"^(\d{4,5}-[A-Z])",
        r"^(SA\d{4,8})",
        r"^(\d{4,6})",
    ])]


# ---------------------------------------------------------------------------
# Globals (prevent GC)
# ---------------------------------------------------------------------------
app = None
ui = None
handlers = []

_pending_preview = None  # holds preview data between Created and Execute

CMD_ID = "TraxisSetupNamingPreview"
CMD_NAME = "Setup Naming Preview"
CMD_DESC = "Preview PART:OP naming for all setups before applying"

TOOLBAR_PANEL_ID = "CAMManagePanel"  # CAM > Manage panel


# ---------------------------------------------------------------------------
# Part number detection (same logic as TraxisCapture)
# ---------------------------------------------------------------------------

def get_part_number(document):
    """Detect part number from attributes or document name."""
    # Check attributes
    for group, key in [("Traxis", "PartNumber"),
                       ("TraxisCapture", "part_number")]:
        try:
            attr = document.attributes.itemByName(group, key)
            if attr and attr.value:
                return attr.value
        except Exception:
            pass

    # Parse from filename
    name = document.name or ""
    for pat in PART_PATTERNS:
        m = pat.match(name)
        if m:
            return m.group(1).upper()
    return None


# ---------------------------------------------------------------------------
# Build the preview (dry run)
# ---------------------------------------------------------------------------

def build_preview(cam, document):
    """Return a list of dicts: {index, current, proposed, skip, already_ok}."""
    part = get_part_number(document)
    rows = []
    part_op_index = 0

    for i in range(cam.setups.count):
        setup = cam.setups.item(i)
        current = setup.name
        lower = current.lower()

        # Check skip
        skipped = any(kw in lower for kw in SKIP_KEYWORDS)
        if skipped:
            rows.append({
                "index": i,
                "current": current,
                "proposed": "(skipped — fixture/workholding)",
                "skip": True,
                "already_ok": False,
            })
            continue

        part_op_index += 1
        op = OP_START + (part_op_index - 1) * OP_INCREMENT

        if part:
            proposed = f"{part}:{op}"
        else:
            proposed = f"???:{op}  (no part number detected)"

        already = NAMING_RE.match(current) is not None

        rows.append({
            "index": i,
            "current": current,
            "proposed": proposed,
            "skip": False,
            "already_ok": already,
        })

    return rows, part


# ---------------------------------------------------------------------------
# Command Created handler — builds the dialog
# ---------------------------------------------------------------------------

class PreviewCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.command)
            cmd.isExecutedWhenPreEmpted = False

            # Get CAM
            doc = app.activeDocument
            if doc is None:
                ui.messageBox("No document is open.", CMD_NAME)
                return

            try:
                cam = adsk.cam.CAM.cast(
                    doc.products.itemByProductType("CAMProductType"))
            except Exception:
                cam = None

            if cam is None or cam.setups.count == 0:
                ui.messageBox(
                    "This document has no CAM setups to rename.", CMD_NAME)
                return

            rows, part = build_preview(cam, doc)

            # Build preview text
            lines = []
            if part:
                lines.append(f"Part number detected: {part}")
            else:
                lines.append("WARNING: Could not detect part number from "
                             "document name or attributes.")
                lines.append("Setups will show '???' — rename will be skipped.")
            lines.append(f"OP numbering: starts at {OP_START}, increments by {OP_INCREMENT}")
            lines.append("")
            lines.append(f"{'#':<4} {'Current Name':<30} {'-->':<5} {'Proposed Name':<30}")
            lines.append("-" * 72)

            any_changes = False
            for r in rows:
                num = r["index"] + 1
                cur = r["current"]
                prop = r["proposed"]

                if r["skip"]:
                    tag = " [SKIP]"
                elif r["already_ok"]:
                    tag = " [OK]"
                else:
                    tag = " [RENAME]"
                    any_changes = True

                lines.append(f"{num:<4} {cur:<30} {'-->':<5} {prop:<28}{tag}")

            lines.append("")
            if not any_changes:
                lines.append("All setups already conform — nothing to change.")
            elif not part:
                lines.append("No part number found — cannot rename. "
                             "Set the part number in the document name or attributes.")

            preview_text = "\n".join(lines)

            # Store preview data on the command for the execute handler
            global _pending_preview
            _pending_preview = {
                "rows": rows,
                "part": part,
                "any_changes": any_changes,
            }

            # Show dialog with preview
            inputs = cmd.commandInputs
            text_input = inputs.addTextBoxCommandInput(
                "preview_text", "Preview",
                f"<pre>{preview_text}</pre>",
                18,   # rows
                True  # read-only
            )

            # Only enable OK if there are actual changes to make
            if not any_changes or not part:
                cmd.isOKButtonVisible = False

            # Wire up execute handler
            on_execute = PreviewExecuteHandler()
            cmd.execute.add(on_execute)
            handlers.append(on_execute)

            # Destroy handler
            on_destroy = PreviewDestroyHandler()
            cmd.destroy.add(on_destroy)
            handlers.append(on_destroy)

        except Exception:
            ui.messageBox(f"Error building preview:\n{traceback.format_exc()}",
                          CMD_NAME)


# ---------------------------------------------------------------------------
# Execute handler — user clicked OK (Apply)
# ---------------------------------------------------------------------------

class PreviewExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            global _pending_preview
            if _pending_preview is None:
                ui.messageBox("No preview data — run preview first.", CMD_NAME)
                return
            rows = _pending_preview["rows"]
            part = _pending_preview["part"]
            _pending_preview = None

            if not part:
                ui.messageBox("No part number — cannot rename.", CMD_NAME)
                return

            doc = app.activeDocument
            cam = adsk.cam.CAM.cast(
                doc.products.itemByProductType("CAMProductType"))

            renamed = 0
            errors = []
            for r in rows:
                if r["skip"] or r["already_ok"]:
                    continue
                idx = r["index"]
                setup = cam.setups.item(idx)
                try:
                    setup.name = r["proposed"]
                    renamed += 1
                except Exception as e:
                    errors.append(f"  Setup {idx+1}: {e}")

            msg = f"Renamed {renamed} setup(s) to PART:OP convention."
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors)

            ui.messageBox(msg, CMD_NAME)

        except Exception:
            ui.messageBox(f"Error applying names:\n{traceback.format_exc()}",
                          CMD_NAME)


# ---------------------------------------------------------------------------
# Destroy handler — cleanup
# ---------------------------------------------------------------------------

class PreviewDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        adsk.terminate()


# ---------------------------------------------------------------------------
# Add-in Lifecycle
# ---------------------------------------------------------------------------

def run(context):
    global app, ui

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Create the command definition
        cmd_defs = ui.commandDefinitions
        existing = cmd_defs.itemById(CMD_ID)
        if existing:
            existing.deleteMe()

        cmd_def = cmd_defs.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_DESC)

        # Set icon if available (optional)
        icon_folder = os.path.join(ADDIN_FOLDER, "resources")
        if os.path.isdir(icon_folder):
            cmd_def.resourceFolder = icon_folder

        # Wire up created handler
        on_created = PreviewCommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        handlers.append(on_created)

        # Add to CAM > Manage panel (or Utilities if CAM panel not found)
        panel = None
        try:
            ws = ui.workspaces.itemById("CAMEnvironment")
            if ws:
                tabs = ws.toolbarTabs
                for t_idx in range(tabs.count):
                    tab = tabs.item(t_idx)
                    panels = tab.toolbarPanels
                    for p_idx in range(panels.count):
                        p = panels.item(p_idx)
                        if p.id == TOOLBAR_PANEL_ID:
                            panel = p
                            break
                    if panel:
                        break
        except Exception:
            pass

        # Fallback: add to utilities panel
        if panel is None:
            try:
                panel = ui.allToolbarPanels.itemById("SolidScriptsAddinsPanel")
            except Exception:
                pass

        if panel:
            existing_ctrl = panel.controls.itemById(CMD_ID)
            if existing_ctrl:
                existing_ctrl.deleteMe()
            panel.controls.addCommand(cmd_def)

        app.log(f"[SetupNamingPreview] Add-in loaded — button added")

    except Exception:
        if ui:
            ui.messageBox(f"SetupNamingPreview startup error:\n"
                          f"{traceback.format_exc()}")


def stop(context):
    global handlers

    try:
        # Remove command from UI
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()

        # Remove from panels
        for panel_id in [TOOLBAR_PANEL_ID, "SolidScriptsAddinsPanel"]:
            try:
                panel = ui.allToolbarPanels.itemById(panel_id)
                if panel:
                    ctrl = panel.controls.itemById(CMD_ID)
                    if ctrl:
                        ctrl.deleteMe()
            except Exception:
                pass

        handlers.clear()
        app.log("[SetupNamingPreview] Add-in stopped")

    except Exception:
        if ui:
            ui.messageBox(f"SetupNamingPreview stop error:\n"
                          f"{traceback.format_exc()}")
