#Author-Traxis Manufacturing
#Description-Test 2: Can We Read One Tool? Reads first tool from first library.

import adsk.core, adsk.cam

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    camMgr = adsk.cam.CAMManager.get()
    toolLibs = camMgr.libraryManager.toolLibraries
    url = toolLibs.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    lib_urls = toolLibs.childAssetURLs(url)

    if not lib_urls:
        # Try subfolders
        for folder_url in toolLibs.childFolderURLs(url):
            lib_urls = toolLibs.childAssetURLs(folder_url)
            if lib_urls:
                break

    if not lib_urls:
        ui.messageBox('No libraries found at Local location.\nTry Cloud or Fusion360 location.', 'Test 2')
        return

    toolLib = toolLibs.toolLibraryAtURL(lib_urls[0])
    if toolLib.count == 0:
        ui.messageBox(f'Library "{lib_urls[0].leafName}" is empty', 'Test 2')
        return

    tool = toolLib.item(0)
    params = tool.parameters

    fields = ['tool_number', 'tool_description', 'tool_productId',
              'tool_diameter', 'tool_type']
    lines = [f'Library: {lib_urls[0].leafName}', f'Tool count: {toolLib.count}', '']

    for name in fields:
        try:
            p = params.itemByName(name)
            if p:
                lines.append(f'{name} = {p.value.value}')
            else:
                lines.append(f'{name} = (not found)')
        except Exception as e:
            lines.append(f'{name} = ERROR: {e}')

    ui.messageBox('\n'.join(lines), 'Test 2: Single Tool Read')
