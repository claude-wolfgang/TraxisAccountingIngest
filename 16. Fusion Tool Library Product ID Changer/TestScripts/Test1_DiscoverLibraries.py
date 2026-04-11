#Author-Traxis Manufacturing
#Description-Test 1: Can We See Libraries? Minimal discovery test.

import adsk.core, adsk.cam

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    camMgr = adsk.cam.CAMManager.get()
    toolLibs = camMgr.libraryManager.toolLibraries

    lines = []
    for loc, label in [
        (adsk.cam.LibraryLocations.LocalLibraryLocation, "Local"),
        (adsk.cam.LibraryLocations.CloudLibraryLocation, "Cloud"),
        (adsk.cam.LibraryLocations.Fusion360LibraryLocation, "Fusion360"),
    ]:
        try:
            url = toolLibs.urlByLocation(loc)
            lib_urls = toolLibs.childAssetURLs(url)
            folder_urls = toolLibs.childFolderURLs(url)
            lines.append(f"{label}: {len(lib_urls)} libraries, {len(folder_urls)} folders")
        except Exception as e:
            lines.append(f"{label}: ERROR - {e}")

    ui.messageBox('\n'.join(lines), 'Test 1: Library Discovery')
