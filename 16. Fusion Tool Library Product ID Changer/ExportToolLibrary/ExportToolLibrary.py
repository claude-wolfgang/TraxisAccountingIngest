#Author-Wolfgang / Traxis Manufacturing
#Description-Exports Fusion 360 tool libraries to JSON and CSV for ProShop ERP integration

import adsk.core, adsk.cam
import os
import json
import csv
import math
import traceback

# Global handlers list to prevent garbage collection
handlers = []

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        # Discover all tool libraries
        libraries = discover_all_libraries()

        if not libraries:
            ui.messageBox('No tool libraries found.', 'Export Tool Library')
            return

        # Build selection list
        selection_text = "Enter the number of the library to export:\n\n"
        for i, lib_info in enumerate(libraries, 1):
            selection_text += f"{i}. [{lib_info['location']}] {lib_info['path']}\n"

        # Get user selection
        (user_input, cancelled) = ui.inputBox(selection_text, 'Select Library', '1')

        if cancelled:
            return

        try:
            selection = int(user_input.strip())
            if selection < 1 or selection > len(libraries):
                ui.messageBox(f'Invalid selection. Please enter a number between 1 and {len(libraries)}.', 'Error')
                return
        except ValueError:
            ui.messageBox('Please enter a valid number.', 'Error')
            return

        selected_lib = libraries[selection - 1]

        # Ask for output folder
        folderDialog = ui.createFolderDialog()
        folderDialog.title = 'Select Output Folder'
        result = folderDialog.showDialog()

        if result != adsk.core.DialogResults.DialogOK:
            return

        output_folder = folderDialog.folder

        # Generate safe filename from library path
        safe_name = selected_lib['path'].replace('/', '_').replace('\\', '_').replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
        if not safe_name:
            safe_name = 'library'

        # Export the library
        export_library(selected_lib['url'], output_folder, safe_name, ui)

    except:
        if ui:
            ui.messageBox(f'Failed:\n{traceback.format_exc()}', 'Error')


def discover_all_libraries():
    """Discover all tool libraries from all locations."""
    libraries = []

    camMgr = adsk.cam.CAMManager.get()
    if not camMgr:
        return libraries

    toolLibs = camMgr.libraryManager.toolLibraries
    if not toolLibs:
        return libraries

    # Location types and their labels
    locations = [
        (adsk.cam.LibraryLocations.LocalLibraryLocation, "Local"),
        (adsk.cam.LibraryLocations.CloudLibraryLocation, "Cloud"),
        (adsk.cam.LibraryLocations.Fusion360LibraryLocation, "Fusion360"),
    ]

    for loc_enum, loc_label in locations:
        try:
            root_url = toolLibs.urlByLocation(loc_enum)
            if root_url:
                # Recursively walk this location
                walk_library_folder(toolLibs, root_url, "", loc_label, libraries)
        except:
            # Location may not be available
            pass

    # Check for Document library if a CAM document is open
    try:
        app = adsk.core.Application.get()
        doc = app.activeDocument
        if doc:
            cam_product = doc.products.itemByProductType('CAMProductType')
            if cam_product:
                cam_obj = adsk.cam.CAM.cast(cam_product)
                if cam_obj and cam_obj.documentToolLibrary:
                    docLib = cam_obj.documentToolLibrary
                    if docLib.count > 0:
                        libraries.append({
                            'location': 'Document',
                            'path': doc.name,
                            'url': None,  # Special case for document library
                            'is_document': True
                        })
    except:
        pass

    return libraries


def walk_library_folder(toolLibs, folder_url, parent_path, location_label, libraries):
    """Recursively walk a folder and collect library URLs."""

    # Get libraries (assets) in this folder
    try:
        lib_urls = toolLibs.childAssetURLs(folder_url)
        for lib_url in lib_urls:
            lib_name = lib_url.leafName if lib_url.leafName else "Unnamed"
            full_path = f"{parent_path}/{lib_name}" if parent_path else lib_name
            libraries.append({
                'location': location_label,
                'path': full_path,
                'url': lib_url,
                'is_document': False
            })
    except:
        pass

    # Get subfolders
    try:
        folder_urls = toolLibs.childFolderURLs(folder_url)
        for sub_folder_url in folder_urls:
            folder_name = sub_folder_url.leafName if sub_folder_url.leafName else "Folder"
            new_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
            walk_library_folder(toolLibs, sub_folder_url, new_path, location_label, libraries)
    except:
        pass


def export_library(lib_url, output_folder, safe_name, ui):
    """Export a library to JSON and CSV files."""

    app = adsk.core.Application.get()

    # Load the library
    if lib_url is None:
        # Document library
        doc = app.activeDocument
        cam_product = doc.products.itemByProductType('CAMProductType')
        cam_obj = adsk.cam.CAM.cast(cam_product)
        toolLib = cam_obj.documentToolLibrary
        is_document_lib = True
    else:
        camMgr = adsk.cam.CAMManager.get()
        toolLibs = camMgr.libraryManager.toolLibraries
        toolLib = toolLibs.toolLibraryAtURL(lib_url)
        is_document_lib = False

    if not toolLib or toolLib.count == 0:
        ui.messageBox('Library is empty or could not be loaded.', 'Export Tool Library')
        return

    # Prepare output data
    full_json_path = os.path.join(output_folder, f"{safe_name}_full.json")
    csv_path = os.path.join(output_folder, f"{safe_name}_summary.csv")

    # Build full JSON export
    full_data = {
        'library_name': safe_name,
        'tool_count': toolLib.count,
        'tools': []
    }

    # Also try to get library-level JSON if available
    try:
        if not is_document_lib:
            full_data['library_json'] = json.loads(toolLib.toJson())
    except:
        pass

    # CSV rows
    csv_rows = []
    csv_headers = [
        'Tool Number',
        'Description',
        'Product ID',
        'Type',
        'Diameter (in)',
        'Flute Length (in)',
        'Body Length (in)',
        'Overall Length (in)',
        'Number of Flutes',
        'Corner Radius (in)',
        'Vendor',
        'Comment',
        'Holder Description',
        'GUID'
    ]

    # Process each tool
    for i in range(toolLib.count):
        try:
            tool = toolLib.item(i)

            # Get individual tool JSON
            try:
                tool_json = json.loads(tool.toJson())
                full_data['tools'].append(tool_json)
            except:
                tool_json = {}

            # Extract parameters for CSV
            row = extract_tool_row(tool, tool_json)
            csv_rows.append(row)

        except Exception as e:
            # Add error row
            csv_rows.append({
                'Tool Number': f'ERROR at index {i}',
                'Description': str(e),
                'Product ID': '',
                'Type': '',
                'Diameter (in)': '',
                'Flute Length (in)': '',
                'Body Length (in)': '',
                'Overall Length (in)': '',
                'Number of Flutes': '',
                'Corner Radius (in)': '',
                'Vendor': '',
                'Comment': '',
                'Holder Description': '',
                'GUID': ''
            })

    # Write full JSON
    with open(full_json_path, 'w', encoding='utf-8') as f:
        json.dump(full_data, f, indent=2)

    # Write CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(csv_rows)

    ui.messageBox(
        f'Export complete!\n\n'
        f'Tools exported: {toolLib.count}\n\n'
        f'Files:\n'
        f'  {os.path.basename(full_json_path)}\n'
        f'  {os.path.basename(csv_path)}\n\n'
        f'Location: {output_folder}',
        'Export Tool Library'
    )


def extract_tool_row(tool, tool_json):
    """Extract a flattened row of tool data for CSV export."""

    row = {
        'Tool Number': '',
        'Description': '',
        'Product ID': '',
        'Type': '',
        'Diameter (in)': '',
        'Flute Length (in)': '',
        'Body Length (in)': '',
        'Overall Length (in)': '',
        'Number of Flutes': '',
        'Corner Radius (in)': '',
        'Vendor': '',
        'Comment': '',
        'Holder Description': '',
        'GUID': ''
    }

    # Get GUID from JSON (most reliable source)
    row['GUID'] = tool_json.get('guid', '')

    # Get type from JSON
    row['Type'] = tool_json.get('type', '')

    # Get description from JSON
    row['Description'] = tool_json.get('description', '')

    # Get product-id from JSON (this is the field we care about)
    row['Product ID'] = tool_json.get('product-id', '')

    # Get vendor from JSON
    row['Vendor'] = tool_json.get('vendor', '')

    # Get holder description from JSON
    holder = tool_json.get('holder', {})
    row['Holder Description'] = holder.get('description', '')

    # Get post-process fields from JSON
    post_process = tool_json.get('post-process', {})
    row['Tool Number'] = str(post_process.get('number', ''))
    row['Comment'] = post_process.get('comment', '')

    # Get geometry from JSON (values are in mm, convert to inches)
    geometry = tool_json.get('geometry', {})

    # DC = diameter (mm)
    if 'DC' in geometry:
        row['Diameter (in)'] = round(geometry['DC'] / 25.4, 4)

    # LCF = flute length (mm)
    if 'LCF' in geometry:
        row['Flute Length (in)'] = round(geometry['LCF'] / 25.4, 4)

    # LB = body length / length below holder (mm)
    if 'LB' in geometry:
        row['Body Length (in)'] = round(geometry['LB'] / 25.4, 4)

    # OAL = overall length (mm)
    if 'OAL' in geometry:
        row['Overall Length (in)'] = round(geometry['OAL'] / 25.4, 4)

    # NOF = number of flutes
    if 'NOF' in geometry:
        row['Number of Flutes'] = geometry['NOF']

    # RE = corner radius (mm)
    if 'RE' in geometry:
        row['Corner Radius (in)'] = round(geometry['RE'] / 25.4, 4)

    # Fallback to parameter API if JSON is missing data
    try:
        params = tool.parameters

        if not row['Tool Number']:
            row['Tool Number'] = get_param_value(params, 'tool_number', '')

        if not row['Description']:
            row['Description'] = get_param_value(params, 'tool_description', '')

        if not row['Product ID']:
            row['Product ID'] = get_param_value(params, 'tool_productId', '')

        if not row['Vendor']:
            row['Vendor'] = get_param_value(params, 'tool_vendor', '')

        if not row['Comment']:
            row['Comment'] = get_param_value(params, 'tool_comment', '')

        if not row['Type']:
            row['Type'] = get_param_value(params, 'tool_type', '')

        if not row['Diameter (in)']:
            diam_cm = get_param_value(params, 'tool_diameter', None)
            if diam_cm is not None:
                row['Diameter (in)'] = round(diam_cm / 2.54, 4)

        if not row['Flute Length (in)']:
            fl_cm = get_param_value(params, 'tool_fluteLength', None)
            if fl_cm is not None:
                row['Flute Length (in)'] = round(fl_cm / 2.54, 4)

        if not row['Body Length (in)']:
            bl_cm = get_param_value(params, 'tool_bodyLength', None)
            if bl_cm is not None:
                row['Body Length (in)'] = round(bl_cm / 2.54, 4)

        if not row['Overall Length (in)']:
            ol_cm = get_param_value(params, 'tool_overallLength', None)
            if ol_cm is not None:
                row['Overall Length (in)'] = round(ol_cm / 2.54, 4)

        if not row['Number of Flutes']:
            row['Number of Flutes'] = get_param_value(params, 'tool_numberOfFlutes', '')

        if not row['Corner Radius (in)']:
            cr_cm = get_param_value(params, 'tool_cornerRadius', None)
            if cr_cm is not None:
                row['Corner Radius (in)'] = round(cr_cm / 2.54, 4)

        if not row['Holder Description']:
            row['Holder Description'] = get_param_value(params, 'tool_holderDescription', '')

    except:
        pass

    return row


def get_param_value(params, param_name, default):
    """Safely get a parameter value."""
    try:
        param = params.itemByName(param_name)
        if param and param.value:
            return param.value.value
    except:
        pass
    return default
