"""
Traxis Program Manager (TPM) for Fusion 360
v1.6.0 -- Traxis Manufacturing

Manages the full NC program lifecycle: setup naming, program versioning,
WCS metadata, and file management.

Workflow:
1. Click "TPM" in CAM toolbar
2. Enter/confirm ProShop part number (auto-filled if ProShopBridge was used)
3. Select which setups to include
4. TPM configures: setup names, program names, output folder, comments, WCS
5. Post normally -- fields are pre-filled
6. After posting, TPM copies files to NC Programs and PART FILES

Metadata headers (PART, OP, WCS, POSTED) and tool IDs are generated
natively by the .cps post processors via writeTraxisHeader() and
tool.productId -- no post-processing injection needed.

Full traceability chain:
  Setup name:  NP000674:60
  Program:     NP000674_OP60.nc
  NC header:   (PART: NP000674) (OP: 60) (WCS: G54 - ...) (POSTED: ...)
  File:        {Dropbox}\\NC Programs\\NP000674\\
  PART FILES:  {Dropbox}\\PART FILES Traxis\\{Customer}\\{CustomerPN}\\

INSTALLATION:
1. Copy entire TraxisProgramManager folder to:
   %appdata%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\
   (or run setup_fusion_addins.bat to create symlink)
2. In Fusion: Scripts and Add-Ins -> Add-Ins -> TraxisProgramManager -> Run
3. Check "Run on Startup"

NAMING CONVENTION:
    Setup 1 -> OP60      Setup 4 -> OP90
    Setup 2 -> OP70      Setup 5 -> OP100
    Setup 3 -> OP80      Setup 6 -> OP110
    Formula: OP = 60 + (SetupNumber - 1) * 10
"""

import adsk.core
import adsk.fusion
import adsk.cam
import logging
import traceback
import os
import re
import sys
import threading

# Fusion doesn't add the add-in folder to sys.path, so subpackage
# imports fail without this.
_addon_dir = os.path.dirname(os.path.abspath(__file__))
if _addon_dir not in sys.path:
    sys.path.insert(0, _addon_dir)

from tpm import config, proshop, naming, fileops, wcs

# ===========================================================================
# Global references (prevent garbage collection)
# ===========================================================================
_app = None
_ui = None
_handlers = []
_naming_state = {}  # Stores naming info per setup for header injection

# Constants
CMD_ID = "traxisProgramManagerCmd"
PANEL_ID = "traxisProgramManagerPanel"

# Module-level path aliases (may be None if Dropbox not found; run() checks)
NC_PROGRAMS_ROOT = config.NC_PROGRAMS_ROOT
PART_FILES_ROOT = config.PART_FILES_ROOT

# Customer part number cache (set by get_part_number or lookup)
_customer_part_number = None


def log(msg):
    try:
        adsk.core.Application.get().log(f"[TPM] {msg}")
    except Exception:
        pass


# ===========================================================================
# Part Number Detection
# ===========================================================================

def get_part_number(document):
    """Get part number from saved document attribute.

    The part number is the ProShop internal number (e.g. NP000674).
    Customer filenames are unpredictable, so we don't try to guess --
    the programmer types it once and it's saved for future posts.

    Also checks if ProShopBridge has set it via shared attribute.
    Also reads Traxis:CustomerPartNumber if available (for folder lookup).
    """
    global _customer_part_number

    if document is None:
        return ""

    # Check saved attributes (set by prior TPM or ProShopBridge use)
    part_number = ""
    for group, key in [('Traxis', 'PartNumber'),
                       ('ProShopBridge', 'PartNumber')]:
        try:
            attr = document.attributes.itemByName(group, key)
            if attr and attr.value:
                log(f"Part number from attribute {group}:{key} = {attr.value}")
                part_number = attr.value
                break
        except Exception as e:
            log(f"Could not read {group}:{key}: {e}")

    # Also read customer part number attribute if present
    try:
        cust_attr = document.attributes.itemByName('Traxis', 'CustomerPartNumber')
        if cust_attr and cust_attr.value:
            _customer_part_number = cust_attr.value
            log(f"Customer PN from attribute: {_customer_part_number}")
    except Exception as e:
        log(f"Could not read Traxis:CustomerPartNumber: {e}")

    return part_number


def save_part_number(document, part_number):
    """Save part number as a document attribute for future use."""
    try:
        document.attributes.add('Traxis', 'PartNumber', part_number)
        log(f"Saved part number attribute: {part_number}")
    except Exception as e:
        log(f"Could not save part number attribute: {e}")


# ===========================================================================
# CAM Parameter Helpers (patterns from ProShopBridge)
# ===========================================================================

def _param_value(obj, param_name):
    """Get numeric/resolved value from a CAM parameter."""
    try:
        param = obj.parameters.itemByName(param_name)
        if param:
            val = param.value
            return float(val.value) if hasattr(val, 'value') else float(val)
    except Exception:
        pass
    return None


def _param_expr(obj, param_name):
    """Get string expression from a CAM parameter (strips quotes)."""
    try:
        param = obj.parameters.itemByName(param_name)
        if param:
            expr = param.expression
            if not expr:
                return None
            if '?' in expr and '==' in expr:
                return None  # Skip unresolved ternary formulas
            if (expr.startswith("'") and expr.endswith("'")) or \
               (expr.startswith('"') and expr.endswith('"')):
                return expr[1:-1]
            return expr
    except Exception:
        pass
    return None


# ===========================================================================
# WCS & Tool Data Extraction
# ===========================================================================

def _get_wcs_gcode(setup):
    """Get WCS G-code (G54, G55, G54.1 Px) from setup parameters."""
    wcs_num = _param_value(setup, 'job_workOffset')
    if wcs_num is not None:
        wcs_num = int(wcs_num)
        if 1 <= wcs_num <= 6:
            return f"G{53 + wcs_num}"
        elif wcs_num > 6:
            return f"G54.1 P{wcs_num - 6}"
    return "G54"


def _get_wcs_raw(setup):
    """Read raw WCS origin mode and box point from Fusion setup parameters.

    Returns (origin_mode, box_point) as title-cased strings, or (None, None).
    """
    origin_mode = None

    # Try turning-specific parameter first
    try:
        p = setup.parameters.itemByName('wcs_origin_turning')
        if p:
            origin_mode = _param_expr(setup, 'wcs_origin_turning')
    except Exception:
        pass

    # Fall back to general origin mode
    if not origin_mode:
        p = setup.parameters.itemByName('wcs_origin_mode')
        if p:
            try:
                v = p.value
                origin_mode = str(v.value) if hasattr(v, 'value') else str(v)
            except Exception:
                origin_mode = _param_expr(setup, 'wcs_origin_mode')

    # Clean up camelCase -> Title Case
    if origin_mode:
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', origin_mode)
        origin_mode = spaced.replace('_', ' ').title()

    # Read box point position (e.g., "top center", "top 1")
    box_point = None
    bp = setup.parameters.itemByName('wcs_origin_boxPoint')
    if bp:
        try:
            bpv = bp.value
            box_str = str(bpv.value) if hasattr(bpv, 'value') else str(bpv)
        except Exception:
            box_str = _param_expr(setup, 'wcs_origin_boxPoint')
        if box_str:
            box_point = box_str.strip().title()

    return origin_mode, box_point


def _get_tool_list(setup):
    """Extract unique tools from setup operations with ProShop product IDs.

    Returns list of dicts: [{number, product_id, description, diameter}, ...]
    """
    tools = []
    seen_numbers = set()
    try:
        ops = setup.allOperations
        for i in range(ops.count):
            op = ops.item(i)
            tool_num = _param_value(op, 'tool_number')
            if tool_num is None or int(tool_num) in seen_numbers:
                continue
            tool_num = int(tool_num)
            seen_numbers.add(tool_num)
            tools.append({
                'number': tool_num,
                'product_id': _param_expr(op, 'tool_productId') or '',
                'description': _param_expr(op, 'tool_description') or '',
                'diameter': _param_value(op, 'tool_diameter'),
            })
    except Exception as e:
        log(f"Could not extract tool list: {e}")
    tools.sort(key=lambda t: t['number'])
    return tools


# ===========================================================================
# Naming Logic (adsk-dependent parts)
# ===========================================================================

def get_cam_product():
    """Return the CAM product from the active document, or None."""
    try:
        doc = _app.activeDocument
        if doc:
            return adsk.cam.CAM.cast(
                doc.products.itemByProductType('CAMProductType'))
    except Exception:
        pass
    return None


def setup_has_changes(setup):
    """Check if any operation in a setup has an invalid (stale) toolpath.

    Uses Operation.isToolpathValid -- returns False when toolpath has been
    invalidated by model or parameter changes since last generation.

    Returns True if the setup needs a new version (has changes).
    Returns True if no toolpaths exist yet (first post).
    """
    try:
        has_any_toolpath = False
        for i in range(setup.allOperations.count):
            op = setup.allOperations.item(i)
            if hasattr(op, 'hasToolpath') and op.hasToolpath:
                has_any_toolpath = True
                if hasattr(op, 'isToolpathValid') and not op.isToolpathValid:
                    log(f"  Op '{op.name}' has stale toolpath")
                    return True
        if not has_any_toolpath:
            return True  # No toolpaths yet = first generation
        return False  # All toolpaths valid = no changes
    except Exception as e:
        log(f"Could not check toolpath validity: {e}")
        return True  # Default to new version on error


# ===========================================================================
# Apply Naming to Setups
# ===========================================================================

def apply_naming_to_setups(cam, part_number, included_indices):
    """Pre-fill included setups' NC Program fields with Traxis naming.

    Only setups whose index is in included_indices get named.
    OP numbering is sequential among included setups only.

    Returns a summary list of what was configured.
    """
    global _naming_state
    _naming_state = {}
    results = []

    part_folder = os.path.join(NC_PROGRAMS_ROOT, part_number)
    os.makedirs(part_folder, exist_ok=True)

    # Find Dropbox part folder for copy
    part_files_folder = fileops.find_part_files_folder(
        part_number, customer_part_number=_customer_part_number)

    # Save customer part number to document attribute for next time
    if _customer_part_number:
        try:
            doc = _app.activeDocument
            if doc:
                doc.attributes.add('Traxis', 'CustomerPartNumber',
                                   _customer_part_number)
                log(f"Saved customer PN attribute: {_customer_part_number}")
        except Exception as e:
            log(f"Could not save customer PN attribute: {e}")

    part_op_index = 0
    for i in range(cam.setups.count):
        setup = cam.setups.item(i)

        if i not in included_indices:
            log(f"Setup '{setup.name}' skipped (unchecked)")
            continue

        part_op_index += 1
        op_number = naming.get_operation_number(part_op_index)
        version = naming.get_next_version(
            part_folder, part_number, op_number,
            has_changes=setup_has_changes(setup))
        filename_stem = f"{part_number}_OP{op_number}"
        program_number = naming.get_program_number(op_number, version)

        # Extract WCS and tool data for header injection
        wcs_gcode = _get_wcs_gcode(setup)
        origin_mode, box_point = _get_wcs_raw(setup)
        wcs_desc = wcs.format_for_machinist(origin_mode, box_point)
        tool_list = _get_tool_list(setup)

        # Build WCS display: "G54 - X: Center, Y: Near Side, Z: Top of Stock"
        wcs_display = f"{wcs_gcode} - {wcs_desc}" if wcs_desc else wcs_gcode
        log(f"  WCS: {wcs_display}")

        if tool_list:
            ids = [f"T{t['number']}={t['product_id']}"
                   for t in tool_list if t['product_id']]
            if ids:
                log(f"  Tool IDs: {', '.join(ids)}")

        # Store naming state for header injection and file copy
        _naming_state[setup.name] = {
            'part_number': part_number,
            'op_number': op_number,
            'version': version,
            'program_number': program_number,
            'filename': f"{filename_stem}.nc",
            'fusion_filename': f"{program_number}.nc",
            'output_folder': part_folder,
            'part_files_folder': part_files_folder,
            'wcs_display': wcs_display,
            'tools': tool_list,
        }

        # Set program name/number -- 4-digit O-number (e.g. "0061")
        # TODO: Change to filename_stem once .cps files are updated to
        # handle non-numeric programName (extract O-code from _OPxx pattern)
        try:
            name_param = setup.parameters.itemByName('job_programName')
            if name_param:
                name_param.expression = f"'{program_number}'"
                log(f"  Set Name/number: O{program_number}")
        except Exception as e:
            log(f"  Could not set program number for '{setup.name}': {e}")

        # Set program comment
        try:
            comment_param = setup.parameters.itemByName('job_programComment')
            if comment_param:
                comment_param.expression = f"'{filename_stem}'"
                log(f"  Set comment: {filename_stem}")
        except Exception as e:
            log(f"  Could not set program comment for '{setup.name}': {e}")

        # Set job description
        try:
            desc_param = setup.parameters.itemByName('job_description')
            if desc_param:
                desc_param.expression = f"'{filename_stem}'"
        except Exception as e:
            pass

        # Try to set output folder via setup parameter
        try:
            folder_param = setup.parameters.itemByName('job_outputFolder')
            if folder_param:
                folder_param.expression = f"'{part_folder}'"
                log(f"  Set output folder: {part_folder}")
        except Exception as e:
            pass  # Output folder may not be a setup parameter

        # Rename setup to PART:OP convention
        conforming_name = f"{part_number}:{op_number}"
        original_name = setup.name
        try:
            setup.name = conforming_name
            log(f"  Renamed setup: '{original_name}' -> '{conforming_name}'")
        except Exception as e:
            log(f"  Could not rename setup '{original_name}': {e}")
            conforming_name = original_name  # keep original if rename fails

        # Update naming state key to match new setup name
        if conforming_name != original_name and original_name in _naming_state:
            _naming_state[conforming_name] = _naming_state.pop(original_name)

        results.append({
            'setup': conforming_name,
            'original_name': original_name,
            'filename': f"{filename_stem}.nc",
            'op': f"OP{op_number}",
            'version': f"v{version}",
            'program_number': program_number,
        })

        log(f"Setup '{conforming_name}' -> {filename_stem}.nc (O{program_number})")

    return results


# ===========================================================================
# NC Program Entity Updates
# ===========================================================================

def _update_nc_programs(cam):
    """Update NC Program entities to match naming convention.

    Sets NC Program name (controls File name and Save-in-document Name)
    and program number (controls Name/number in post dialog).
    """
    global _naming_state
    if not _naming_state:
        return

    try:
        nc_progs = cam.ncPrograms
        count = nc_progs.count if hasattr(nc_progs, 'count') else 0
        log(f"NC Programs found: {count}")
        if count == 0:
            return
    except Exception as e:
        log(f"cam.ncPrograms error: {e}")
        return

    log(f"Updating {nc_progs.count} NC Program(s)...")

    for i in range(nc_progs.count):
        try:
            nc = nc_progs.item(i)
        except Exception:
            continue

        # Match this NC Program to a setup via its operations
        matched_setup = _match_nc_to_setup(nc)
        if matched_setup is None:
            continue

        info = _naming_state.get(matched_setup)
        if info is None:
            continue

        filename_stem = f"{info['part_number']}_OP{info['op_number']}"

        # Set NC Program name -> controls "File name" and "Name" fields
        try:
            old_name = nc.name
            nc.name = filename_stem
            log(f"  NC Program '{old_name}' -> {filename_stem}")
        except Exception as e:
            log(f"  Could not rename NC Program: {e}")

        # Set Name/number -> 4-digit O-number
        try:
            param = nc.parameters.itemByName('job_programName')
            if param:
                param.expression = f"'{info['program_number']}'"
        except Exception:
            pass

        # Set Comment
        try:
            param = nc.parameters.itemByName('job_programComment')
            if param:
                param.expression = f"'{filename_stem}'"
        except Exception:
            pass

        # Set Output folder
        try:
            param = nc.parameters.itemByName('job_outputFolder')
            if param:
                param.expression = f"'{info['output_folder']}'"
        except Exception:
            pass

        # Set Traxis WCS description (read by writeTraxisHeader() in .cps)
        try:
            wcs_param = nc.parameters.itemByName('traxisWCS')
            if wcs_param:
                wcs_param.expression = f"'{info.get('wcs_display', '')}'"
                log(f"  Set traxisWCS: {info.get('wcs_display', '')}")
        except Exception:
            pass


def _match_nc_to_setup(nc_program):
    """Match an NC Program to a setup name by checking its operations."""
    try:
        ops = nc_program.operations
        if ops is None or ops.count == 0:
            log(f"  NC '{nc_program.name}': no operations -- cannot match")
            return None

        first_op = ops.item(0)
        # Try known API attributes for parent setup reference
        for attr_name in ('parentSetup', 'setup'):
            parent = getattr(first_op, attr_name, None)
            if parent and hasattr(parent, 'name'):
                log(f"  NC '{nc_program.name}' matched via "
                    f"{attr_name} -> '{parent.name}'")
                return parent.name
        log(f"  NC '{nc_program.name}': op has no parentSetup/setup attr")
    except Exception as e:
        log(f"  NC match error for '{nc_program.name}': {e}")
    return None


def _rename_nc_programs(cam):
    """Rename NC Programs that have default names (e.g. NCProgram4).

    Runs after posting so NC Programs created by "Create NC program"
    checkbox get proper names. Uses _naming_state to match via operations.
    """
    global _naming_state
    if not _naming_state:
        return

    try:
        nc_progs = cam.ncPrograms
        if not nc_progs or nc_progs.count == 0:
            return
    except Exception:
        return

    for i in range(nc_progs.count):
        try:
            nc = nc_progs.item(i)
        except Exception:
            continue

        # Only rename NC Programs with default names
        if not nc.name.startswith('NCProgram'):
            continue

        matched_setup = _match_nc_to_setup(nc)
        if matched_setup is None:
            continue

        info = _naming_state.get(matched_setup)
        if info is None:
            continue

        filename_stem = f"{info['part_number']}_OP{info['op_number']}"
        try:
            old_name = nc.name
            nc.name = filename_stem
            log(f"Renamed NC Program '{old_name}' -> '{filename_stem}'")
        except Exception as e:
            log(f"Could not rename NC Program '{nc.name}': {e}")


# ===========================================================================
# Fusion 360 Command Handlers
# ===========================================================================

class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.command)
            cmd.isRepeatable = False

            on_execute = CommandExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)

            on_validate = CommandValidateHandler()
            cmd.validateInputs.add(on_validate)
            _handlers.append(on_validate)

            on_input_changed = CommandInputChangedHandler()
            cmd.inputChanged.add(on_input_changed)
            _handlers.append(on_input_changed)

            on_destroy = CommandDestroyHandler()
            cmd.destroy.add(on_destroy)
            _handlers.append(on_destroy)

            inputs = cmd.commandInputs

            # Part Number -- the only thing we need from the user
            doc = _app.activeDocument
            detected_part = get_part_number(doc) if doc else ""
            inputs.addStringValueInput(
                'partNumber', 'Part #', detected_part)

            # Checkbox per setup -- auto-uncheck fixture setups
            cam = get_cam_product()
            _SKIP_KEYWORDS = ['fixture', 'soft jaw', 'softjaw', 'jaws',
                              'workholding', 'vise']
            if cam and cam.setups.count > 0:
                for i in range(cam.setups.count):
                    s = cam.setups.item(i)
                    name_lower = s.name.lower()
                    is_part_op = not any(
                        kw in name_lower for kw in _SKIP_KEYWORDS)
                    inputs.addBoolValueInput(
                        f'setup_{i}', s.name, True, '', is_part_op)
            else:
                inputs.addTextBoxCommandInput(
                    'noSetups', '', '<i>No CAM setups found</i>',
                    1, True)

            # Preview of what will be configured
            preview = _build_setup_preview(
                inputs, cam, detected_part)
            inputs.addTextBoxCommandInput(
                'preview', 'Preview', preview, 4, True)

        except Exception:
            log(traceback.format_exc())
            if _ui:
                _ui.messageBox(
                    f"TPM dialog error:\n"
                    f"{traceback.format_exc()}")


def _build_setup_preview(inputs, cam, part_number):
    """Build preview text showing naming for checked setups."""
    if not cam or cam.setups.count == 0:
        return "<i>No setups</i>"
    if not part_number:
        return "<i>Enter a part number</i>"

    lines = []
    part_op_index = 0  # Only count checked setups for OP numbering

    for i in range(cam.setups.count):
        cb = inputs.itemById(f'setup_{i}')
        setup = cam.setups.item(i)
        if cb and cb.value:
            part_op_index += 1
            op = naming.get_operation_number(part_op_index)
            setup_label = f"{part_number}:{op}"
            lines.append(
                f"{setup.name} -> <b>{setup_label}</b> | "
                f"<b>{part_number}_OP{op}.nc</b>")
        else:
            lines.append(f"{setup.name}: <i>skip</i>")

    return '<br>'.join(lines)


class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            inputs = args.input.parentCommandInputs
            part_number = inputs.itemById('partNumber').value.strip()
            cam = get_cam_product()
            preview = _build_setup_preview(inputs, cam, part_number)
            preview_input = inputs.itemById('preview')
            if preview_input:
                preview_input.formattedText = preview
        except Exception as e:
            log(f"Input changed error: {e}")


class CommandValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            inputs = args.inputs
            part_number = inputs.itemById('partNumber').value.strip()
            args.areInputsValid = bool(part_number)
        except Exception:
            args.areInputsValid = False


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            part_number = inputs.itemById('partNumber').value.strip()

            cam = get_cam_product()
            if not cam:
                _ui.messageBox("No CAM data in the active document.")
                return

            if cam.setups.count == 0:
                _ui.messageBox("No setups found in this document.")
                return

            # Gather checked setup indices
            included = []
            for i in range(cam.setups.count):
                cb = inputs.itemById(f'setup_{i}')
                if cb and cb.value:
                    included.append(i)

            if not included:
                _ui.messageBox("No setups selected.")
                return

            # Apply naming to checked setups only
            results = apply_naming_to_setups(cam, part_number, included)

            # Update existing NC Program entities so the post dialog
            # shows the correct File name and Name fields.
            _update_nc_programs(cam)

            # Save part number for next time
            doc = _app.activeDocument
            if doc:
                save_part_number(doc, part_number)

            # Build confirmation message
            lines = [f"Naming configured for {len(results)} setup(s):\n"]
            for r in results:
                lines.append(
                    f"  {r['setup']}:  {r['filename']}  "
                    f"O{r['program_number']} ({r['version']})")
            lines.append(f"\nOutput: {NC_PROGRAMS_ROOT}\\{part_number}\\")

            # Show part files folder status
            pf = fileops.find_part_files_folder(
                part_number, customer_part_number=_customer_part_number)
            if pf:
                lines.append(f"Copy to: {pf}\\")
            else:
                lines.append(
                    f"\nNote: No part folder found in PART FILES "
                    f"for '{part_number}' -- NC files will only be "
                    f"saved to NC Programs.")

            lines.append(
                "\nPost normally -- fields are pre-filled "
                "in the post dialog.")

            _ui.messageBox('\n'.join(lines), "Traxis Program Manager")
            log(f"Naming configured: {part_number}, "
                f"{len(results)} setups")

        except Exception:
            log(traceback.format_exc())
            if _ui:
                _ui.messageBox(
                    f"TPM error:\n{traceback.format_exc()}")


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        pass  # Add-in stays running after dialog closes


class PostCompletedHandler(adsk.core.ApplicationCommandEventHandler):
    """Detect post-processor completion and copy files.

    File processing runs on a BACKGROUND THREAD because:
    - IronPostProcess terminates before the file is fully flushed
    - Fusion needs the main thread to finish writing the file
    - time.sleep() on the main thread blocks the file write
    """

    def notify(self, args):
        try:
            event_args = adsk.core.ApplicationCommandEventArgs.cast(args)
            cmd_id = event_args.commandId
            reason = event_args.terminationReason

            if cmd_id not in ('IronPostProcess', 'IronNcProgram'):
                return

            log(f"Post command: '{cmd_id}' reason={reason}")

            if cmd_id == 'IronNcProgram':
                return

            if not _naming_state:
                log("Post completed -- no naming state, trying auto-catch")
                # Read part number from document attributes (main thread = API safe)
                app = adsk.core.Application.get()
                doc = app.activeDocument
                part_number = get_part_number(doc) if doc else ""
                if not part_number:
                    log("Auto-catch: no part number in document attributes -- skipping")
                    return
                log(f"Auto-catch: part number '{part_number}' from document attributes")
                t = threading.Thread(
                    target=fileops.auto_catch_posted_files,
                    args=(part_number,),
                    daemon=True)
                t.start()
                return

            log("Post completed -- processing on background thread")

            # Rename NC Programs created during posting (main thread = API safe)
            try:
                cam = get_cam_product()
                if cam:
                    _rename_nc_programs(cam)
            except Exception as e:
                log(f"NC Program rename error: {e}")

            # Copy naming state for the background thread
            state_copy = dict(_naming_state)

            # Spawn background thread -- main thread stays free for
            # Fusion to finish writing the NC file to disk
            t = threading.Thread(
                target=fileops.process_posted_files,
                args=(state_copy,),
                daemon=True)
            t.start()

        except Exception:
            log(f"PostCompleted error: {traceback.format_exc()}")


# ===========================================================================
# Add-in Lifecycle
# ===========================================================================

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        # Validate Dropbox is available
        if config.DROPBOX_ROOT is None:
            _ui.messageBox(
                "TPM: Cannot locate Dropbox folder.\n"
                "Is Dropbox installed?",
                "Traxis Program Manager")
            return

        # Bridge tpm package logging to Fusion console
        class _FusionLogHandler(logging.Handler):
            def emit(self, record):
                try:
                    adsk.core.Application.get().log(
                        f"[TPM] {record.getMessage()}")
                except Exception:
                    pass

        tpm_logger = logging.getLogger("tpm")
        tpm_logger.addHandler(_FusionLogHandler())
        tpm_logger.setLevel(logging.DEBUG)

        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if not cmd_def:
            res_folder = os.path.join(
                os.path.dirname(__file__), 'resources')
            cmd_def = _ui.commandDefinitions.addButtonDefinition(
                CMD_ID,
                'TPM',
                'Traxis Program Manager\n\n'
                'Names setups (PART:OP), versions NC programs '
                '(PART_OPxx_vN.nc), sets WCS metadata, and '
                'files programs to NC Programs + PART FILES.',
                res_folder if os.path.isdir(res_folder) else '')

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)

        # Add to CAM workspace toolbar
        added = False
        try:
            ws = _ui.workspaces.itemById('CAMEnvironment')
            if ws:
                tabs = ws.toolbarTabs
                tab = tabs.itemById('ToolsTab')
                if not tab:
                    tab = tabs.itemById('UtilitiesTab')
                if tab:
                    panels = tab.toolbarPanels
                    panel = panels.itemById(PANEL_ID)
                    if not panel:
                        panel = panels.add(
                            PANEL_ID, 'Traxis Program Manager', '', False)
                    ctrl = panel.controls.itemById(CMD_ID)
                    if not ctrl:
                        panel.controls.addCommand(cmd_def)
                    added = True
        except Exception as e:
            log(f"Could not add to CAM workspace: {e}")

        if not added:
            try:
                panel = _ui.allToolbarPanels.itemById(
                    'SolidScriptsAddinsPanel')
                if panel:
                    ctrl = panel.controls.itemById(CMD_ID)
                    if not ctrl:
                        panel.controls.addCommand(cmd_def)
            except Exception as e:
                log(f"Could not add to fallback panel: {e}")

        # Register post-completion handler for file copy
        post_handler = PostCompletedHandler()
        _ui.commandTerminated.add(post_handler)
        _handlers.append(post_handler)

        log("TPM add-in started (with post-completion hook)")

    except Exception:
        if _ui:
            _ui.messageBox(
                f"TPM failed to start:\n"
                f"{traceback.format_exc()}")


def stop(context):
    global _handlers
    try:
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()

        try:
            ws = _ui.workspaces.itemById('CAMEnvironment')
            if ws:
                tabs = ws.toolbarTabs
                for tab_id in ['ToolsTab', 'UtilitiesTab']:
                    tab = tabs.itemById(tab_id)
                    if tab:
                        panel = tab.toolbarPanels.itemById(PANEL_ID)
                        if panel:
                            panel.deleteMe()
        except Exception:
            pass

        _handlers = []
        log("TPM add-in stopped")

    except Exception:
        if _ui:
            _ui.messageBox(
                f"TPM stop error:\n"
                f"{traceback.format_exc()}")
