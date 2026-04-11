#Author-Traxis Manufacturing
#Description-Test 3: Does toJson() Work? Shows raw JSON structure.

import adsk.core, adsk.cam
import json

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    camMgr = adsk.cam.CAMManager.get()
    toolLibs = camMgr.libraryManager.toolLibraries
    url = toolLibs.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)

    # Find first library (check subfolders too)
    lib_urls = toolLibs.childAssetURLs(url)
    if not lib_urls:
        for folder_url in toolLibs.childFolderURLs(url):
            lib_urls = toolLibs.childAssetURLs(folder_url)
            if lib_urls:
                break

    if not lib_urls:
        ui.messageBox('No libraries found at Local location.\nTry Cloud or Fusion360 location.', 'Test 3')
        return

    toolLib = toolLibs.toolLibraryAtURL(lib_urls[0])
    if toolLib.count == 0:
        ui.messageBox(f'Library "{lib_urls[0].leafName}" is empty', 'Test 3')
        return

    tool = toolLib.item(0)

    try:
        tj = json.loads(tool.toJson())
    except Exception as e:
        ui.messageBox(f'toJson() failed: {e}', 'Test 3')
        return

    # Show just the top-level keys and product-id
    lines = [
        f'Library: {lib_urls[0].leafName}',
        f'Tool: {tj.get("description", "Unknown")}',
        '',
        f'Top-level keys: {list(tj.keys())}',
        '',
        f'product-id: "{tj.get("product-id", "")}"',
        f'description: "{tj.get("description", "")}"',
        f'type: "{tj.get("type", "")}"',
        f'vendor: "{tj.get("vendor", "")}"',
        '',
        f'geometry keys: {list(tj.get("geometry", {}).keys())}',
    ]

    # Show geometry values if present
    geom = tj.get('geometry', {})
    if 'DC' in geom:
        lines.append(f'  DC (diameter): {geom["DC"]} mm')
    if 'LCF' in geom:
        lines.append(f'  LCF (flute length): {geom["LCF"]} mm')
    if 'LB' in geom:
        lines.append(f'  LB (body length): {geom["LB"]} mm')

    ui.messageBox('\n'.join(lines), 'Test 3: toJson() Structure')
