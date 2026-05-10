"""
Traxis Program Naming for Fusion 360
v1.2.0 — Traxis Manufacturing

Pre-fills Fusion's native NC Program / Post dialog with standardized naming:
    {PartNumber}_OP{XX}_v{N}.nc

Workflow:
1. Click "Set Traxis Naming" in CAM toolbar
2. Enter/confirm part number (auto-detected)
3. Add-in configures all setups: file name, output folder, comment
4. Setups are renamed to PART:OP convention (e.g. 3847-C:60)
5. Post normally through Fusion's dialog — fields are pre-filled
6. After posting, header metadata is injected into the .nc file
7. NC file is copied to PART FILES folder if found

Full traceability chain:
  Setup name:  3847-C:60
  Program:     3847-C_OP60_v2.nc
  NC header:   (PART: 3847-C) (OP: 60) (VERSION: 2) (POSTED: ...)
  File:        D:\\Dropbox\\NC Programs\\3847-C\\
  PART FILES:  D:\\Dropbox\\PART FILES Traxis\\{Customer}\\3847-C\\

INSTALLATION:
1. Copy entire TraxisPostProcessor folder to:
   %appdata%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\
   (or run setup_fusion_addins.bat to create symlink)
2. In Fusion: Scripts and Add-Ins -> Add-Ins -> TraxisPostProcessor -> Run
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
import traceback
import os
import re
import glob
from datetime import datetime

# ===========================================================================
# Global references (prevent garbage collection)
# ===========================================================================
_app = None
_ui = None
_handlers = []
_naming_state = {}  # Stores naming info per setup for header injection

# Constants
CMD_ID = "traxisNamingCmd"
PANEL_ID = "traxisNamingPanel"
NC_PROGRAMS_ROOT = r"D:\Dropbox\NC Programs"
PART_FILES_ROOT = r"D:\Dropbox\PART FILES Traxis"


def log(msg):
    try:
        adsk.core.Application.get().log(f"[TraxisNaming] {msg}")
    except Exception:
        pass


# ===========================================================================
# Part Number Detection
# ===========================================================================

def get_part_number(document):
    """Get part number from saved document attribute.

    The part number is the ProShop internal number (e.g. NP000674).
    Customer filenames are unpredictable, so we don't try to guess —
    the programmer types it once and it's saved for future posts.

    Also checks if ProShopBridge has set it via shared attribute.
    """
    if document is None:
        return ""

    # Check saved attributes (set by prior TraxisPostProcessor or ProShopBridge use)
    for group, key in [('Traxis', 'PartNumber'),
                       ('ProShopBridge', 'PartNumber')]:
        try:
            attr = document.attributes.itemByName(group, key)
            if attr and attr.value:
                log(f"Part number from attribute {group}:{key} = {attr.value}")
                return attr.value
        except Exception as e:
            log(f"Could not read {group}:{key}: {e}")

    return ""


def save_part_number(document, part_number):
    """Save part number as a document attribute for future use."""
    try:
        document.attributes.add('Traxis', 'PartNumber', part_number)
        log(f"Saved part number attribute: {part_number}")
    except Exception as e:
        log(f"Could not save part number attribute: {e}")


# ===========================================================================
# Naming Logic
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


def get_operation_number(setup_number):
    """Setup 1 -> OP60, Setup 2 -> OP70, etc."""
    return 60 + (setup_number - 1) * 10


def get_current_version(output_folder, part_number, op_number):
    """Return the highest existing version number, or 0 if none exist."""
    pattern = os.path.join(output_folder, f"{part_number}_OP{op_number}_v*.nc")
    existing = glob.glob(pattern)
    if not existing:
        return 0
    versions = []
    for f in existing:
        match = re.search(r'_v(\d+)\.nc$', os.path.basename(f))
        if match:
            versions.append(int(match.group(1)))
    return max(versions) if versions else 0


def setup_has_changes(setup):
    """Check if any operation in a setup has an invalid (stale) toolpath.

    Uses Operation.isToolpathValid — returns False when toolpath has been
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


def get_next_version(output_folder, part_number, op_number, setup=None):
    """Determine the version number for this post.

    If setup is provided and has no stale toolpaths, reuse the current
    version (the program hasn't changed). Only increment when toolpaths
    have actually changed or no previous version exists.
    """
    current = get_current_version(output_folder, part_number, op_number)

    if current == 0:
        return 1  # First post

    if setup and not setup_has_changes(setup):
        log(f"  No toolpath changes — reusing v{current}")
        return current  # Same version, program unchanged

    return current + 1  # Toolpaths changed, new version


# ===========================================================================
# Dropbox Part Folder Lookup
# ===========================================================================

def find_part_files_folder(part_number):
    """Search PART FILES Traxis for a customer folder containing this part.

    Scans: D:\\Dropbox\\PART FILES Traxis\\{Customer}\\{PartNumber}\\
    Returns the full path if found, or None.
    """
    if not os.path.isdir(PART_FILES_ROOT):
        return None
    search = os.path.join(PART_FILES_ROOT, '*', part_number)
    matches = glob.glob(search)
    if matches:
        log(f"Found part folder: {matches[0]}")
        return matches[0]
    return None


def copy_to_part_folder(nc_file_path, part_files_folder):
    """Copy an NC file into the Dropbox part folder."""
    import shutil
    try:
        dest = os.path.join(part_files_folder, os.path.basename(nc_file_path))
        shutil.copy2(nc_file_path, dest)
        log(f"Copied to part folder: {dest}")
        return dest
    except Exception as e:
        log(f"Could not copy to part folder: {e}")
        return None


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
    part_files_folder = find_part_files_folder(part_number)

    part_op_index = 0
    for i in range(cam.setups.count):
        setup = cam.setups.item(i)

        if i not in included_indices:
            log(f"Setup '{setup.name}' skipped (unchecked)")
            continue

        part_op_index += 1
        op_number = get_operation_number(part_op_index)
        version = get_next_version(part_folder, part_number, op_number, setup)
        filename_stem = f"{part_number}_OP{op_number}_v{version}"

        # Store naming state for header injection and file copy
        _naming_state[setup.name] = {
            'part_number': part_number,
            'op_number': op_number,
            'version': version,
            'filename': f"{filename_stem}.nc",
            'output_folder': part_folder,
            'part_files_folder': part_files_folder,
        }

        # Set program comment on the setup
        try:
            comment_param = setup.parameters.itemByName('job_programComment')
            if comment_param:
                comment_param.expression = f"'{filename_stem}'"
                log(f"  Set comment: {filename_stem}")
        except Exception as e:
            log(f"  Could not set program comment for '{setup.name}': {e}")

        # Set program name — controls File name in post dialog
        try:
            name_param = setup.parameters.itemByName('job_programName')
            if name_param:
                name_param.expression = f"'{filename_stem}'"
                log(f"  Set program name: {filename_stem}")
        except Exception as e:
            log(f"  Could not set program name for '{setup.name}': {e}")

        # Set job description — may control NC Program name in browser
        try:
            desc_param = setup.parameters.itemByName('job_description')
            if desc_param:
                desc_param.expression = f"'{filename_stem}'"
                log(f"  Set description: {filename_stem}")
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
        })

        log(f"Setup '{conforming_name}' -> {filename_stem}.nc")

    return results


# ===========================================================================
# G-code Header Injection (post-process hook)
# ===========================================================================

def inject_header_into_file(nc_file_path, part_number, op_number, version):
    """Inject standardized header comment into a posted NC file."""
    try:
        with open(nc_file_path, 'r', encoding='utf-8', errors='replace') as f:
            nc_content = f.read()
    except Exception as e:
        log(f"Could not read NC file for header injection: {e}")
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    program_label = f"{part_number}_OP{op_number}_v{version}"

    # Get programmer name
    programmer = ""
    try:
        user = _app.currentUser
        if user:
            programmer = user.displayName or ""
    except Exception:
        pass

    metadata_lines = [
        f"(PART: {part_number})",
        f"(OP: {op_number})",
        f"(VERSION: {version})",
        f"(POSTED: {timestamp})",
    ]
    if programmer:
        metadata_lines.append(f"(PROGRAMMER: {programmer})")

    lines = nc_content.split('\n')
    if not lines:
        return

    first_line = lines[0].strip()

    if first_line.startswith('%'):
        if len(lines) > 1 and lines[1].strip().startswith('O'):
            o_line = lines[1].strip().split('(')[0].strip()
            lines[1] = f"{o_line} ({program_label})"
            insert_pos = 2
        else:
            lines.insert(1, f"O{op_number} ({program_label})")
            insert_pos = 2
        for idx, m in enumerate(metadata_lines):
            lines.insert(insert_pos + idx, m)
    elif first_line.startswith('O'):
        o_line = first_line.split('(')[0].strip()
        lines[0] = f"{o_line} ({program_label})"
        for idx, m in enumerate(metadata_lines):
            lines.insert(1 + idx, m)
    else:
        header = [f"O{op_number} ({program_label})"] + metadata_lines
        lines = header + lines

    try:
        with open(nc_file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        log(f"Header injected into {nc_file_path}")
    except Exception as e:
        log(f"Could not write header to NC file: {e}")


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

            # Part Number — the only thing we need from the user
            doc = _app.activeDocument
            detected_part = get_part_number(doc) if doc else ""
            inputs.addStringValueInput(
                'partNumber', 'Part #', detected_part)

            # Checkbox per setup — auto-uncheck fixture setups
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
                    f"Traxis Naming dialog error:\n"
                    f"{traceback.format_exc()}")


def _build_setup_preview(inputs, cam, part_number):
    """Build preview text showing naming for checked setups."""
    if not cam or cam.setups.count == 0:
        return "<i>No setups</i>"
    if not part_number:
        return "<i>Enter a part number</i>"

    lines = []
    part_op_index = 0  # Only count checked setups for OP numbering
    part_folder = os.path.join(NC_PROGRAMS_ROOT, part_number)

    for i in range(cam.setups.count):
        cb = inputs.itemById(f'setup_{i}')
        setup = cam.setups.item(i)
        if cb and cb.value:
            part_op_index += 1
            op = get_operation_number(part_op_index)
            v = get_next_version(part_folder, part_number, op, setup)
            changed = setup_has_changes(setup)
            tag = "" if changed else " (unchanged)"
            setup_label = f"{part_number}:{op}"
            lines.append(
                f"{setup.name} → <b>{setup_label}</b> | "
                f"<b>{part_number}_OP{op}_v{v}.nc</b>{tag}")
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

            # Save part number for next time
            doc = _app.activeDocument
            if doc:
                save_part_number(doc, part_number)

            # Build confirmation message
            lines = [f"Naming configured for {len(results)} setup(s):\n"]
            for r in results:
                lines.append(
                    f"  {r['setup']}:  {r['filename']}")
            lines.append(f"\nOutput: {NC_PROGRAMS_ROOT}\\{part_number}\\")

            # Show part files folder status
            pf = find_part_files_folder(part_number)
            if pf:
                lines.append(f"Copy to: {pf}\\")
            else:
                lines.append(
                    f"\nNote: No part folder found in PART FILES "
                    f"for '{part_number}' — NC files will only be "
                    f"saved to NC Programs.")

            lines.append(
                "\nPost normally — file name and comment "
                "are pre-filled in Fusion's post dialog.")

            _ui.messageBox('\n'.join(lines), "Traxis Naming")
            log(f"Naming configured: {part_number}, "
                f"{len(results)} setups")

        except Exception:
            log(traceback.format_exc())
            if _ui:
                _ui.messageBox(
                    f"Traxis Naming error:\n{traceback.format_exc()}")


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        pass  # Add-in stays running after dialog closes


class PostCompletedHandler(adsk.core.ApplicationCommandEventHandler):
    """Detect post-processor completion and inject headers + copy files."""

    def notify(self, args):
        try:
            event_args = adsk.core.ApplicationCommandEventArgs.cast(args)
            cmd_id = event_args.commandId

            # Only respond to post commands
            if 'Post' not in cmd_id and 'post' not in cmd_id:
                return

            # Ignore cancelled posts
            if event_args.terminationReason != 0:
                return

            if not _naming_state:
                log("Post completed but no naming state — skipping injection")
                return

            log(f"Post completed (cmd: {cmd_id}) — "
                f"processing {len(_naming_state)} setup(s)")

            for setup_name, info in _naming_state.items():
                part = info['part_number']
                op = info['op_number']
                ver = info['version']
                folder = info['output_folder']
                filename = info['filename']
                nc_path = os.path.join(folder, filename)

                # Inject header into the posted NC file
                if os.path.isfile(nc_path):
                    inject_header_into_file(nc_path, part, op, ver)

                    # Copy to PART FILES folder
                    pf = info.get('part_files_folder')
                    if pf and os.path.isdir(pf):
                        copy_to_part_folder(nc_path, pf)
                else:
                    # File might have a slightly different name — scan for
                    # recently modified .nc files in the output folder
                    log(f"  Expected file not found: {nc_path}")
                    _try_inject_recent(folder, part, op, ver, info)

        except Exception:
            log(f"PostCompleted error: {traceback.format_exc()}")


def _try_inject_recent(folder, part, op, ver, info):
    """Fallback: find recently posted NC files and inject headers."""
    try:
        now = datetime.now().timestamp()
        for fname in os.listdir(folder):
            if not fname.lower().endswith('.nc'):
                continue
            fpath = os.path.join(folder, fname)
            mtime = os.path.getmtime(fpath)
            if now - mtime < 30:  # modified in the last 30 seconds
                log(f"  Found recent NC file: {fname}")
                inject_header_into_file(fpath, part, op, ver)
                pf = info.get('part_files_folder')
                if pf and os.path.isdir(pf):
                    copy_to_part_folder(fpath, pf)
    except Exception as e:
        log(f"  Fallback scan error: {e}")


# ===========================================================================
# Add-in Lifecycle
# ===========================================================================

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if not cmd_def:
            res_folder = os.path.join(
                os.path.dirname(__file__), 'resources')
            cmd_def = _ui.commandDefinitions.addButtonDefinition(
                CMD_ID,
                'Set Traxis Naming',
                'Configure NC program naming for all setups: '
                'PartNumber_OPxx_vN.nc\n\n'
                'Sets file name, comment, and output folder, '
                'then post normally through Fusion.',
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
                            PANEL_ID, 'Traxis', '', False)
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

        # Register post-completion handler for header injection
        post_handler = PostCompletedHandler()
        _ui.commandTerminated.add(post_handler)
        _handlers.append(post_handler)

        log("Traxis Naming add-in started (with post-completion hook)")

    except Exception:
        if _ui:
            _ui.messageBox(
                f"Traxis Naming failed to start:\n"
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
        log("Traxis Naming add-in stopped")

    except Exception:
        if _ui:
            _ui.messageBox(
                f"Traxis Naming stop error:\n"
                f"{traceback.format_exc()}")
