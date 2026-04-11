"""ToolRenumber — Fusion 360 add-in to renumber CAM tools to match machine pockets.

Workflow:
1. User clicks "Renumber Tools" in the Add-Ins toolbar
2. Dialog shows machine dropdown (auto-detects from setup comment if possible)
3. Queries ProShop for that machine's pocket layout
4. Reads CAM setup's tool list via adsk.cam API
5. Matches CAM tools to pockets by Product ID
6. Preview dialog: old T# → new T# with reasons
7. On confirm, modifies tool_number on each Fusion tool object
"""

import os
import sys
import json
import traceback

import adsk.core
import adsk.cam

# Add this directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pocket_client import PocketClient
from renumber_engine import compute_renumbering, format_preview

# Global references (prevent garbage collection)
handlers = []
_app = None
_ui = None
_cmd_def = None

COMMAND_ID = "traxisToolRenumber"
COMMAND_NAME = "Renumber Tools"
COMMAND_TOOLTIP = "Renumber CAM tools to match machine pocket assignments"

# Known Traxis machines (potId values)
MACHINE_LIST = [
    "Mill-1", "Mill-2", "Mill-3", "Mill-4",
    "Mill-5", "Mill-6", "Mill-7", "Mill-8", "T2"
]


def run(context):
    """Entry point when add-in starts."""
    global _app, _ui, _cmd_def
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        # Create command definition
        _cmd_def = _ui.commandDefinitions.itemById(COMMAND_ID)
        if _cmd_def:
            _cmd_def.deleteMe()
        _cmd_def = _ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID, COMMAND_NAME, COMMAND_TOOLTIP
        )

        # Connect to command created event
        on_created = CommandCreatedHandler()
        _cmd_def.commandCreated.add(on_created)
        handlers.append(on_created)

        # Add to Add-Ins panel in CAM workspace
        cam_ws = _ui.workspaces.itemById("CAMEnvironment")
        if cam_ws:
            panels = cam_ws.toolbarPanels
            panel = panels.itemById("traxisToolsPanel")
            if not panel:
                panel = panels.add("traxisToolsPanel", "Traxis Tools")
            ctrl = panel.controls.itemById(COMMAND_ID)
            if not ctrl:
                panel.controls.addCommand(_cmd_def)

    except Exception:
        if _ui:
            _ui.messageBox(f"ToolRenumber start failed:\n{traceback.format_exc()}")


def stop(context):
    """Entry point when add-in stops."""
    try:
        # Clean up UI
        cam_ws = _ui.workspaces.itemById("CAMEnvironment")
        if cam_ws:
            panel = cam_ws.toolbarPanels.itemById("traxisToolsPanel")
            if panel:
                ctrl = panel.controls.itemById(COMMAND_ID)
                if ctrl:
                    ctrl.deleteMe()
                if panel.controls.count == 0:
                    panel.deleteMe()

        cmd_def = _ui.commandDefinitions.itemById(COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except Exception:
        pass


# ── Command Handlers ─────────────────────────────────────────────────────────

class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            inputs = cmd.commandInputs

            # Machine dropdown
            machine_input = inputs.addDropDownCommandInput(
                "machineSelect", "Target Machine",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for m in MACHINE_LIST:
                machine_input.listItems.add(m, False)

            # Auto-detect machine from active setup comment
            detected = _detect_machine_from_setup()
            if detected:
                for i in range(machine_input.listItems.count):
                    if machine_input.listItems.item(i).name == detected:
                        machine_input.listItems.item(i).isSelected = True
                        break
                else:
                    machine_input.listItems.item(0).isSelected = True
            else:
                machine_input.listItems.item(0).isSelected = True

            # Preview text box (populated on execute preview)
            inputs.addTextBoxCommandInput(
                "preview", "Preview", "(Select machine and click OK to preview)", 12, True
            )

            # Connect events
            on_execute = CommandExecuteHandler()
            cmd.execute.add(on_execute)
            handlers.append(on_execute)

            on_preview = CommandPreviewHandler()
            cmd.executePreview.add(on_preview)
            handlers.append(on_preview)

            on_validate = CommandValidateHandler()
            cmd.validateInputs.add(on_validate)
            handlers.append(on_validate)

            on_input_changed = CommandInputChangedHandler()
            cmd.inputChanged.add(on_input_changed)
            handlers.append(on_input_changed)

        except Exception:
            _ui.messageBox(f"Command create failed:\n{traceback.format_exc()}")


class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            changed_input = args.input
            if changed_input.id != "machineSelect":
                return

            inputs = args.inputs
            machine_input = inputs.itemById("machineSelect")
            preview_input = inputs.itemById("preview")

            selected = machine_input.selectedItem
            if not selected:
                return

            pot_id = selected.name
            preview_input.text = f"Loading pockets for {pot_id}..."

            # Query ProShop and build preview
            try:
                client = PocketClient()
                pocket_map = client.get_machine_pockets(pot_id)
                cam_tools = _get_cam_tools()

                if not cam_tools:
                    preview_input.text = "No CAM tools found in active setup."
                    return

                assignments = compute_renumbering(cam_tools, pocket_map)
                preview_text = format_preview(assignments)
                # HTML-ify for text box
                preview_input.text = preview_text.replace("\n", "<br>").replace(" ", "&nbsp;")

            except Exception as e:
                preview_input.text = f"Error: {e}"

        except Exception:
            pass  # Don't crash on preview errors


class CommandPreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        args.isValidResult = True


class CommandValidateHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        args.areInputsValid = True


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            machine_input = inputs.itemById("machineSelect")
            selected = machine_input.selectedItem
            if not selected:
                _ui.messageBox("No machine selected.")
                return

            pot_id = selected.name

            # Query ProShop
            client = PocketClient()
            pocket_map = client.get_machine_pockets(pot_id)

            # Get CAM tools
            cam_tools = _get_cam_tools()
            if not cam_tools:
                _ui.messageBox("No CAM tools found in active setup.")
                return

            # Compute renumbering
            assignments = compute_renumbering(cam_tools, pocket_map)

            # Count actual changes
            changes = [a for a in assignments if a["tool_number_old"] != a["tool_number_new"]]
            if not changes:
                _ui.messageBox("All tools already match pocket assignments. No changes needed.")
                return

            # Apply renumbering to Fusion CAM tools
            applied = _apply_renumbering(assignments)

            _ui.messageBox(
                f"Renumbered {applied} of {len(assignments)} tools for {pot_id}.\n\n"
                f"Re-post your setups to generate NC code with the updated T-numbers."
            )

        except Exception:
            _ui.messageBox(f"Renumber failed:\n{traceback.format_exc()}")


# ── Fusion CAM Helpers ───────────────────────────────────────────────────────

def _detect_machine_from_setup():
    """Try to detect target machine from the active CAM setup's comment or name."""
    try:
        doc = _app.activeDocument
        products = doc.products
        cam_product = products.itemByProductType("CAMProductType")
        if not cam_product:
            return None
        cam = adsk.cam.CAM.cast(cam_product)
        if not cam or not cam.setups or cam.setups.count == 0:
            return None

        # Check first setup's name and comment for machine hints
        setup = cam.setups.item(0)
        text = f"{setup.name} {setup.parameters.itemByName('job_comment').expression if setup.parameters.itemByName('job_comment') else ''}"
        text = text.upper()

        for m in MACHINE_LIST:
            if m.upper().replace("-", "") in text.replace("-", "").replace(" ", ""):
                return m
    except Exception:
        pass
    return None


def _get_cam_tools():
    """Read all tools from the active CAM document's setups.

    Returns list of {tool_number, product_id, description}.
    """
    try:
        doc = _app.activeDocument
        products = doc.products
        cam_product = products.itemByProductType("CAMProductType")
        if not cam_product:
            return []
        cam = adsk.cam.CAM.cast(cam_product)
        if not cam:
            return []

        seen = set()
        tools = []
        for setup_idx in range(cam.setups.count):
            setup = cam.setups.item(setup_idx)
            for op_idx in range(setup.allOperations.count):
                op = setup.allOperations.item(op_idx)
                tool = op.tool
                if not tool or tool.objectType != "adsk::cam::Tool":
                    continue
                # Use tool number as dedup key
                t_num = tool.parameters.itemByName("tool_number")
                tool_number = int(t_num.expression) if t_num else 0
                if tool_number in seen:
                    continue
                seen.add(tool_number)

                # Get Product ID (stored as tool_productId or product_id parameter)
                product_id = ""
                pid_param = tool.parameters.itemByName("tool_productId")
                if pid_param:
                    product_id = pid_param.expression.strip("'\"")
                if not product_id:
                    pid_param = tool.parameters.itemByName("product_id")
                    if pid_param:
                        product_id = pid_param.expression.strip("'\"")

                desc_param = tool.parameters.itemByName("tool_description")
                description = desc_param.expression.strip("'\"") if desc_param else tool.description or ""

                tools.append({
                    "tool_number": tool_number,
                    "product_id": product_id,
                    "description": description,
                })

        tools.sort(key=lambda t: t["tool_number"])
        return tools
    except Exception:
        return []


def _apply_renumbering(assignments):
    """Apply renumbering to Fusion CAM tool objects. Returns count of tools changed."""
    doc = _app.activeDocument
    products = doc.products
    cam_product = products.itemByProductType("CAMProductType")
    cam = adsk.cam.CAM.cast(cam_product)
    if not cam:
        return 0

    # Build old_number → new_number map
    remap = {}
    for a in assignments:
        if a["tool_number_old"] != a["tool_number_new"]:
            remap[a["tool_number_old"]] = a["tool_number_new"]

    if not remap:
        return 0

    applied = 0
    for setup_idx in range(cam.setups.count):
        setup = cam.setups.item(setup_idx)
        for op_idx in range(setup.allOperations.count):
            op = setup.allOperations.item(op_idx)
            tool = op.tool
            if not tool:
                continue
            t_num_param = tool.parameters.itemByName("tool_number")
            if not t_num_param:
                continue
            current = int(t_num_param.expression)
            if current in remap:
                t_num_param.expression = str(remap[current])
                applied += 1

    return applied
