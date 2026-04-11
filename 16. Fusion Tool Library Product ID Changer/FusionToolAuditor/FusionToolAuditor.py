# Author: Traxis Manufacturing
# Description: Audit and edit Product IDs in Fusion tool libraries for ProShop ERP integration

import adsk.core
import adsk.cam
import traceback
import json
import threading
import urllib.request
import urllib.parse

# Global handlers to prevent garbage collection
handlers = []

# Global references
_app = None
_ui = None
_palette = None
_library_data = []  # Cache of discovered libraries
_current_tools = []  # Cache of tools from selected library
_current_lib_info = None  # Info about currently selected library
_proshop_tools = []  # Cache of ProShop tools

PALETTE_ID = 'FusionToolAuditorPalette'
PALETTE_NAME = 'Tool Library Auditor'
COMMAND_ID = 'FusionToolAuditorCmd'
COMMAND_NAME = 'Tool Auditor'
COMMAND_TOOLTIP = 'Audit and edit Product IDs in tool libraries'
PANEL_ID = 'ToolsPanel'  # Existing panel in Manufacture workspace

# ProShop API credentials
PROSHOP_CLIENT_ID = 'BA16-EFAF-B154'
PROSHOP_CLIENT_SECRET = '2F64968E4E77FDE1CB6B587D9F92340CC3B4C82A414D77798F359A85CD4976D1'
PROSHOP_SCOPE = 'parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r'
PROSHOP_TOKEN_URL = 'https://traxismfg.adionsystems.com/home/member/oauth/accesstoken'
PROSHOP_GRAPHQL_URL = 'https://traxismfg.adionsystems.com/api/graphql'

# Get HTML file path (same directory as this script)
import os
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
HTML_FILE_PATH = os.path.join(SCRIPT_DIR, 'palette.html')


def run(context):
    """Entry point when add-in is started."""
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        # Show the palette immediately
        show_palette()

    except:
        if _ui:
            _ui.messageBox(f'Add-in start failed:\n{traceback.format_exc()}')


def stop(context):
    """Entry point when add-in is stopped."""
    global _palette
    try:
        if _palette:
            _palette.deleteMe()
            _palette = None
    except:
        pass


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            onExecute = CommandExecuteHandler()
            cmd.execute.add(onExecute)
            handlers.append(onExecute)
        except:
            _ui.messageBox(f'Command created failed:\n{traceback.format_exc()}')


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            show_palette()
        except:
            _ui.messageBox(f'Command execute failed:\n{traceback.format_exc()}')


def show_palette():
    """Create and show the palette."""
    global _palette

    palettes = _ui.palettes
    _palette = palettes.itemById(PALETTE_ID)

    if not _palette:
        # Convert Windows path to file URL
        import pathlib
        html_url = pathlib.Path(HTML_FILE_PATH).as_uri()

        _palette = palettes.add(
            PALETTE_ID,
            PALETTE_NAME,
            html_url,
            True,   # isVisible
            True,   # showCloseButton
            True,   # isResizable
            800,    # width
            550     # height
        )

        onHTMLEvent = PaletteHTMLEventHandler()
        _palette.incomingFromHTML.add(onHTMLEvent)
        handlers.append(onHTMLEvent)

        onClosed = PaletteClosedHandler()
        _palette.closed.add(onClosed)
        handlers.append(onClosed)
    else:
        _palette.isVisible = True


class PaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        pass


class PaletteHTMLEventHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            msg = json.loads(args.data)
            action = msg.get('action', '')
            data = msg.get('data', {})

            if action == 'getLibraries' or action == 'refreshLibraries':
                self.handle_get_libraries()
            elif action == 'loadLibrary':
                self.handle_load_library(data.get('index', 0))
            elif action == 'saveChanges':
                self.handle_save_changes(data.get('tools', []))
            elif action == 'fetchProshopTools':
                self.handle_fetch_proshop_tools()
            elif action == 'exportJson':
                self.handle_export_json(data.get('tools', []))
            elif action == 'closePalette':
                if _palette:
                    _palette.isVisible = False

        except:
            _ui.messageBox(f'Palette event failed:\n{traceback.format_exc()}')

    def handle_get_libraries(self):
        global _library_data
        _library_data = discover_all_libraries()
        lib_list = [{'location': l['location'], 'path': l['path']} for l in _library_data]
        self.send_to_html(f'setLibraries({json.dumps(lib_list)})')

    def handle_load_library(self, index):
        global _current_tools, _current_lib_info

        if index < 0 or index >= len(_library_data):
            return

        _current_lib_info = _library_data[index]
        _current_tools = load_tools_from_library(_current_lib_info)

        tool_list = []
        for t in _current_tools:
            tool_list.append({
                'index': t['index'],
                'toolNumber': t.get('tool_number', ''),
                'description': t.get('description', ''),
                'type': t.get('type', ''),
                'diameter': t.get('diameter_in'),
                'productId': t.get('product_id', ''),
                'vendor': t.get('vendor', ''),
                'guid': t.get('guid', '')
            })

        self.send_to_html(f'setTools({json.dumps(tool_list)})')

    def handle_save_changes(self, tools_data):
        global _current_lib_info

        if not _current_lib_info:
            self.send_to_html('showMessage("No library loaded", "error")')
            return

        try:
            success_count = save_product_ids(_current_lib_info, tools_data)
            self.send_to_html(f'showMessage("Saved {success_count} Product IDs", "success")')
            self.handle_load_library(_library_data.index(_current_lib_info))
        except Exception as e:
            self.send_to_html(f'showMessage("Save failed: {str(e)}", "error")')

    def handle_fetch_proshop_tools(self):
        """Fetch ProShop tools in a background thread."""
        global _proshop_tools

        # Try synchronous fetch first (simpler, works better in Fusion)
        try:
            tools = fetch_proshop_tools()
            _proshop_tools = tools
            self.send_to_html(f'setProshopTools({json.dumps(tools)})')
            return
        except Exception as e:
            self.send_to_html(f'showMessage("ProShop fetch failed: {str(e)}", "error")')
            return

        # Background thread version (commented out - sync works better)
        # def fetch_thread():
        #     global _proshop_tools
        #     try:
        #         tools = fetch_proshop_tools()
        #         _proshop_tools = tools
        #         adsk.core.Application.get().fireCustomEvent('FusionToolAuditorProShopLoaded', json.dumps(tools))
        #     except Exception as e:
        #         adsk.core.Application.get().fireCustomEvent('FusionToolAuditorProShopLoaded', json.dumps({'error': str(e)}))

        # Register custom event if not already
        try:
            app = adsk.core.Application.get()
            evt = app.registerCustomEvent('FusionToolAuditorProShopLoaded')
            onProShopLoaded = ProShopLoadedHandler()
            evt.add(onProShopLoaded)
            handlers.append(onProShopLoaded)
        except:
            pass  # Already registered

        thread = threading.Thread(target=fetch_thread)
        thread.daemon = True
        thread.start()

    def handle_export_json(self, tools_data):
        """Export library with modified Product IDs to JSON file."""
        global _current_lib_info

        if not _current_lib_info:
            self.send_to_html('showMessage("No library loaded", "error")')
            return

        try:
            app = adsk.core.Application.get()

            # Load the actual library
            if _current_lib_info.get('is_document'):
                doc = app.activeDocument
                cam_product = doc.products.itemByProductType('CAMProductType')
                cam_obj = adsk.cam.CAM.cast(cam_product)
                toolLib = cam_obj.documentToolLibrary
            else:
                camMgr = adsk.cam.CAMManager.get()
                toolLibs = camMgr.libraryManager.toolLibraries
                toolLib = toolLibs.toolLibraryAtURL(_current_lib_info['url'])

            if not toolLib:
                self.send_to_html('showMessage("Could not load library", "error")')
                return

            # Build modified tools list
            modified_tools = []
            for tool_data in tools_data:
                idx = tool_data.get('index', -1)
                if idx >= 0 and idx < toolLib.count:
                    tool = toolLib.item(idx)
                    try:
                        tool_json = json.loads(tool.toJson())
                        # Apply user modifications
                        tool_json['product-id'] = tool_data.get('productId', '')
                        tool_json['vendor'] = tool_data.get('vendor', '')
                        modified_tools.append(tool_json)
                    except:
                        pass

            # Create library JSON structure
            library_json = {
                'version': 2,
                'data': modified_tools
            }

            # Ask user for save location
            fileDialog = _ui.createFileDialog()
            fileDialog.isMultiSelectEnabled = False
            fileDialog.title = 'Save Modified Tool Library'
            fileDialog.filter = 'Tool Library (*.json)'
            fileDialog.filterIndex = 0

            # Generate default filename
            safe_name = _current_lib_info['path'].replace('/', '_').replace('\\', '_').replace(' ', '_')
            safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
            fileDialog.initialFilename = f'{safe_name}_modified.json'

            result = fileDialog.showSave()
            if result != adsk.core.DialogResults.DialogOK:
                return

            filepath = fileDialog.filename

            # Write JSON file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(library_json, f, indent=2)

            self.send_to_html(f'showMessage("Exported {len(modified_tools)} tools to {os.path.basename(filepath)}", "success")')

        except Exception as e:
            self.send_to_html(f'showMessage("Export failed: {str(e)}", "error")')

    def send_to_html(self, js_code):
        if _palette:
            _palette.sendInfoToHTML('exec', js_code)


class ProShopLoadedHandler(adsk.core.CustomEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            data = json.loads(args.additionalInfo)
            if isinstance(data, dict) and 'error' in data:
                if _palette:
                    _palette.sendInfoToHTML('exec', f'showMessage("ProShop: {data["error"]}", "error")')
            else:
                if _palette:
                    _palette.sendInfoToHTML('exec', f'setProshopTools({json.dumps(data)})')
        except:
            pass


def fetch_proshop_tools():
    """Fetch all tools from ProShop API."""
    import ssl

    # Create SSL context that doesn't verify (for corporate proxies)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Get access token
    token_data = urllib.parse.urlencode({
        'grant_type': 'client_credentials',
        'client_id': PROSHOP_CLIENT_ID,
        'client_secret': PROSHOP_CLIENT_SECRET,
        'scope': PROSHOP_SCOPE
    }).encode('utf-8')

    req = urllib.request.Request(PROSHOP_TOKEN_URL, data=token_data)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
        token_resp = json.loads(response.read().decode('utf-8'))

    access_token = token_resp.get('access_token')
    if not access_token:
        raise Exception('Failed to get access token: ' + str(token_resp))

    # Query tools with EDP data from approvedBrands
    query = '''
    {
        tools(pageSize: 1000) {
            totalRecords
            records {
                toolNumber
                description
                cutDiameter
                numberOfFlutes
                toolGroupLetter
                approvedBrands {
                    records {
                        vendorToolId
                    }
                }
            }
        }
    }
    '''

    graphql_data = json.dumps({'query': query}).encode('utf-8')
    req = urllib.request.Request(PROSHOP_GRAPHQL_URL, data=graphql_data)
    req.add_header('Authorization', f'Bearer {access_token}')
    req.add_header('Content-Type', 'application/json')

    with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
        result = json.loads(response.read().decode('utf-8'))

    raw_tools = result.get('data', {}).get('tools', {}).get('records', [])

    # Process tools to extract EDP list
    tools = []
    for t in raw_tools:
        tool = {
            'toolNumber': t.get('toolNumber', ''),
            'description': t.get('description', ''),
            'cutDiameter': t.get('cutDiameter'),
            'numberOfFlutes': t.get('numberOfFlutes'),
            'toolGroupLetter': t.get('toolGroupLetter', ''),
            'edps': []
        }
        # Extract EDPs from approvedBrands
        brands = t.get('approvedBrands', {}).get('records', [])
        for b in brands:
            edp = b.get('vendorToolId', '')
            if edp:
                tool['edps'].append(edp)
        tools.append(tool)

    return tools


def discover_all_libraries():
    """Discover all tool libraries from all locations."""
    libraries = []

    camMgr = adsk.cam.CAMManager.get()
    if not camMgr:
        return libraries

    toolLibs = camMgr.libraryManager.toolLibraries
    if not toolLibs:
        return libraries

    locations = [
        (adsk.cam.LibraryLocations.LocalLibraryLocation, "Local"),
        (adsk.cam.LibraryLocations.CloudLibraryLocation, "Cloud"),
        (adsk.cam.LibraryLocations.Fusion360LibraryLocation, "Fusion360"),
    ]

    for loc_enum, loc_label in locations:
        try:
            root_url = toolLibs.urlByLocation(loc_enum)
            if root_url:
                walk_library_folder(toolLibs, root_url, "", loc_label, libraries)
        except:
            pass

    # Document library
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
                            'url': None,
                            'is_document': True
                        })
    except:
        pass

    return libraries


def walk_library_folder(toolLibs, folder_url, parent_path, location_label, libraries):
    """Recursively walk a folder and collect library URLs."""
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

    try:
        folder_urls = toolLibs.childFolderURLs(folder_url)
        for sub_folder_url in folder_urls:
            folder_name = sub_folder_url.leafName if sub_folder_url.leafName else "Folder"
            new_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
            walk_library_folder(toolLibs, sub_folder_url, new_path, location_label, libraries)
    except:
        pass


def load_tools_from_library(lib_info):
    """Load all tools from a library and extract key data."""
    tools = []

    app = adsk.core.Application.get()

    if lib_info.get('is_document'):
        doc = app.activeDocument
        cam_product = doc.products.itemByProductType('CAMProductType')
        cam_obj = adsk.cam.CAM.cast(cam_product)
        toolLib = cam_obj.documentToolLibrary
    else:
        camMgr = adsk.cam.CAMManager.get()
        toolLibs = camMgr.libraryManager.toolLibraries
        toolLib = toolLibs.toolLibraryAtURL(lib_info['url'])

    if not toolLib:
        return tools

    for i in range(toolLib.count):
        try:
            tool = toolLib.item(i)
            tool_data = extract_tool_data(tool, i)
            tools.append(tool_data)
        except:
            tools.append({'index': i, 'description': f'Error loading tool {i}'})

    return tools


def extract_tool_data(tool, index):
    """Extract key data from a tool for display."""
    data = {'index': index}

    try:
        tj = json.loads(tool.toJson())
        data['guid'] = tj.get('guid', '')
        data['description'] = tj.get('description', '')
        data['product_id'] = tj.get('product-id', '')
        data['vendor'] = tj.get('vendor', '')
        data['type'] = tj.get('type', '')

        post = tj.get('post-process', {})
        data['tool_number'] = str(post.get('number', ''))

        geom = tj.get('geometry', {})
        if 'DC' in geom:
            data['diameter_in'] = geom['DC'] / 25.4
    except:
        pass

    try:
        params = tool.parameters

        if not data.get('tool_number'):
            data['tool_number'] = str(get_param_value(params, 'tool_number', ''))

        if not data.get('description'):
            data['description'] = get_param_value(params, 'tool_description', '')

        if not data.get('product_id'):
            data['product_id'] = get_param_value(params, 'tool_productId', '')

        if not data.get('type'):
            data['type'] = get_param_value(params, 'tool_type', '')

        if not data.get('vendor'):
            data['vendor'] = get_param_value(params, 'tool_vendor', '')

        if not data.get('diameter_in'):
            diam_cm = get_param_value(params, 'tool_diameter', None)
            if diam_cm:
                data['diameter_in'] = diam_cm / 2.54
    except:
        pass

    return data


def get_param_value(params, param_name, default):
    """Safely get a parameter value."""
    try:
        param = params.itemByName(param_name)
        if param and param.value:
            return param.value.value
    except:
        pass
    return default


def save_product_ids(lib_info, tools_data):
    """Save Product ID changes back to Fusion."""
    app = adsk.core.Application.get()
    success_count = 0

    if lib_info.get('is_document'):
        doc = app.activeDocument
        cam_product = doc.products.itemByProductType('CAMProductType')
        cam_obj = adsk.cam.CAM.cast(cam_product)
        toolLib = cam_obj.documentToolLibrary

        for tool_data in tools_data:
            try:
                idx = tool_data.get('index', -1)
                new_id = tool_data.get('productId', '')
                new_vendor = tool_data.get('vendor', '')

                if idx >= 0 and idx < toolLib.count:
                    tool = toolLib.item(idx)
                    params = tool.parameters
                    changed = False

                    # Update Product ID
                    param = params.itemByName('tool_productId')
                    if param:
                        current = ''
                        try:
                            current = param.value.value or ''
                        except:
                            pass
                        if current != new_id:
                            param.value.value = new_id
                            changed = True

                    # Update Vendor
                    vendor_param = params.itemByName('tool_vendor')
                    if vendor_param:
                        current_vendor = ''
                        try:
                            current_vendor = vendor_param.value.value or ''
                        except:
                            pass
                        if current_vendor != new_vendor:
                            vendor_param.value.value = new_vendor
                            changed = True

                    if changed:
                        toolLib.update(tool, True)
                        success_count += 1
            except:
                pass
    else:
        camMgr = adsk.cam.CAMManager.get()
        toolLibs = camMgr.libraryManager.toolLibraries
        toolLib = toolLibs.toolLibraryAtURL(lib_info['url'])

        if toolLib:
            for tool_data in tools_data:
                try:
                    idx = tool_data.get('index', -1)
                    new_id = tool_data.get('productId', '')
                    new_vendor = tool_data.get('vendor', '')

                    if idx >= 0 and idx < toolLib.count:
                        tool = toolLib.item(idx)
                        params = tool.parameters
                        changed = False

                        # Update Product ID
                        param = params.itemByName('tool_productId')
                        if param:
                            current = ''
                            try:
                                current = param.value.value or ''
                            except:
                                pass
                            if current != new_id:
                                param.value.value = new_id
                                changed = True

                        # Update Vendor
                        vendor_param = params.itemByName('tool_vendor')
                        if vendor_param:
                            current_vendor = ''
                            try:
                                current_vendor = vendor_param.value.value or ''
                            except:
                                pass
                            if current_vendor != new_vendor:
                                vendor_param.value.value = new_vendor
                                changed = True

                        if changed:
                            success_count += 1
                except:
                    pass

    return success_count
