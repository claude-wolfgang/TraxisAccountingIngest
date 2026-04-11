# Fusion 360 API Reference — Lessons Learned

**Last Updated:** 2026-02-05
**Applies to:** `EXPORT TO PROSHOP.py` (Fusion 360 Script)

---

## Quick Reference

| Item | Detail |
|------|--------|
| Script Location | `%appdata%\Autodesk\Autodesk Fusion 360\API\Scripts\EXPORT TO PROSHOP\` |
| Dev Copy | `D:\Dropbox\...\1. Proshop Automations\EXPORT_TO_PROSHOP.py` |
| Deploy | Copy dev file to Script Location (filenames differ: underscore vs space) |
| Internal Units | **Centimeters** — always divide by 2.54 for inches |
| API Module | `adsk.core`, `adsk.fusion`, `adsk.cam` |

---

## Units

Fusion 360 stores ALL numeric values internally in **centimeters**, regardless of what the user sees in the UI.

```python
# Convert to inches for ProShop
value_inches = value_cm / 2.54
```

This applies to: tool dimensions, stock dimensions, WCS offsets, stickout, etc.

---

## CAM Access

```python
app = adsk.core.Application.get()
doc = app.activeDocument
cam = adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))

# cam will be None if no CAM data exists (user hasn't entered Manufacturing workspace)
```

---

## Setup Iteration

```python
for i in range(cam.setups.count):
    setup = cam.setups.item(i)
```

### Operations Are Nested in Folders

Operations can be at the top level of a setup OR inside folders (and nested folders). Always use recursive traversal:

```python
def get_all_operations(setup):
    operations = []
    for i in range(setup.operations.count):
        operations.append(setup.operations.item(i))
    for i in range(setup.folders.count):
        folder = setup.folders.item(i)
        operations.extend(get_operations_from_folder(folder))
    return operations

def get_operations_from_folder(folder):
    operations = []
    for i in range(folder.operations.count):
        operations.append(folder.operations.item(i))
    for i in range(folder.folders.count):
        operations.extend(get_operations_from_folder(folder.folders.item(i)))
    return operations
```

---

## Setup Type Detection (Milling vs Turning)

### Primary Method: operationType enum

```python
if setup.operationType == adsk.cam.OperationTypes.TurningOperation:
    # This is a lathe/turning setup
```

Other values: `MillingOperation`, `MillTurnOperation`

### Fallback Methods

```python
# Check for turning-specific parameters
param = setup.parameters.itemByName('turning_stockStickout')
if param:
    # Turning setup

# Check setup name keywords
name_lower = setup.name.lower()
if any(kw in name_lower for kw in ['turn', 'lathe', 'chuck']):
    # Probably turning
```

Use all three in a cascade — the enum check can fail on older API versions.

---

## Parameter Access

Setup and operation parameters are accessed via `.parameters.itemByName('name')`.

### Getting Numeric Values

```python
param = setup.parameters.itemByName('tool_bodyLength')
if param:
    val = param.value
    # val might be a Value object or a raw number
    if hasattr(val, 'value'):
        val = val.value  # Extract the float
    # val is now in centimeters
```

### Getting Text/Expression Values

```python
param = setup.parameters.itemByName('job_programComment')
if param:
    expr = param.expression  # Returns string, may have quotes
    # Strip surrounding quotes
    if expr.startswith("'") and expr.endswith("'"):
        expr = expr[1:-1]
    if expr.startswith('"') and expr.endswith('"'):
        expr = expr[1:-1]
```

### Debugging: Dump All Parameters

When you don't know what parameters exist on a setup/operation, dump them all:

```python
for i in range(setup.parameters.count):
    p = setup.parameters.item(i)
    try:
        print(f"{p.name}: {p.expression}")
    except:
        pass
```

The export script writes these to `wcs._all_params` in the JSON output for inspection.

---

## Known Parameter Names

### Setup — Program Info

| Parameter | Content | Type |
|-----------|---------|------|
| `job_programName` | Program number (e.g., "1001") | text |
| `job_programComment` | Program comment / name | text |

### Setup — WCS / Origin

| Parameter | Content | Type |
|-----------|---------|------|
| `job_wcsNumber` | WCS offset (1=G54, 2=G55, ...) | numeric |
| `job_wcsOriginMode` | Origin mode (e.g., "Model front", "Stock front") | text |
| `job_wcsXExpression` | X offset | text/numeric |
| `job_wcsYExpression` | Y offset | text/numeric |
| `job_wcsZExpression` | Z offset | text/numeric |

### Setup — Stock

| Parameter | Content | Type |
|-----------|---------|------|
| `job_stockMode` | Stock definition mode | text |
| `job_stockOffsetSides` | Side offset | numeric (cm) |
| `job_stockOffsetTop` | Top offset | numeric (cm) |
| `job_stockOffsetBottom` | Bottom offset | numeric (cm) |
| `job_stockZLow` | Stock Z minimum | numeric (cm) |
| `job_stockZHigh` | Stock Z maximum | numeric (cm) |

### Setup — Turning Specific

| Parameter | Content | Type |
|-----------|---------|------|
| `turning_stockStickout` | Stickout from chuck | numeric (cm) |
| `turning_chuckZOffset` | Chuck Z position | numeric (cm) |

**Note:** These parameter names are discovered via the debug dump. If they don't exist on your setup, check `_all_params` in the JSON output for the actual names your Fusion version uses.

### Operation — Tool Data

| Parameter | ProShop Field | Notes |
|-----------|---------------|-------|
| `tool_number` | — | G-code tool number (T1, T2, ...) |
| `tool_description` | — | Free-text description |
| `tool_comment` | — | Tool comment |
| `tool_type` | — | Tool type category |
| `tool_diameter` | — | Cutter diameter (cm) |
| `tool_fluteLength` | — | Flute length (cm) |
| `tool_overallLength` | — | Overall length (cm) |
| `tool_bodyLength` | OOH | **"Length below holder"** in Fusion UI (cm) |
| `tool_shoulderLength` | — | Shoulder length (cm) |
| `tool_shaftDiameter` | — | Shaft diameter (cm) |
| `tool_numberOfFlutes` | — | Number of flutes |
| `tool_holderDescription` | Holder | Holder name |
| `tool_holderId` | Holder (fallback) | Holder ID |
| `tool_productId` | Tool # | Library tool ID (e.g., "TH495") |
| `tool_productLink` | — | Link to tool catalog |
| `tool_vendor` | — | Tool vendor name |
| `tool_coolant` | — | Coolant type |

**Key discovery:** "Length below holder" is `tool_bodyLength`, NOT `tool_lengthBelowHolder`.

### Operation — Machining Parameters

| Parameter | Content |
|-----------|---------|
| `tool_feedCutting` | Cutting feedrate |
| `tool_feedPlunge` | Plunge feedrate |
| `tool_spindleSpeed` | Spindle speed |
| `tool_rampFeedRate` | Ramp feedrate |
| `tolerance` | Machining tolerance |
| `stepdown` | Axial stepdown |
| `stepover` | Radial stepover |
| `maximumStepdown` | Max stepdown |
| `optimalLoad` | Optimal load (HSM) |

---

## Compound / Indexable Tools

Some tools have a hyphenated `product_id` like `TH495-TP496` where:
- First part = tool body (e.g., `TH495`)
- Second part = insert (e.g., `TP496`)

The export script splits these and sends the insert as `gTypeInsert` to ProShop.

Detection heuristic: second part starts with `T` or common insert prefixes (`IC`, `CN`, `DN`, `SN`, `TN`, `VN`, `WN`).

---

## Screenshots / Viewport Control

### Workspace Must Be Manufacturing

Stock, toolpaths, and WCS triad only display when the Manufacturing (CAM) workspace is active:

```python
cam_workspace = app.userInterface.workspaces.itemById('CAMEnvironment')
if cam_workspace:
    cam_workspace.activate()
    adsk.doEvents()
    time.sleep(0.5)
```

### Setup Activation

Activating a setup makes its stock, toolpaths, and WCS visible:

```python
setup.activate()
adsk.doEvents()
time.sleep(1.0)  # Need a real delay for rendering
```

### Selecting the Setup in the Browser

Selecting the setup in the UI browser triggers the same visual state as clicking it (stock overlay, toolpath display):

```python
ui = app.userInterface
ui.activeSelections.clear()
ui.activeSelections.add(setup)
adsk.doEvents()
time.sleep(0.5)
```

### Toolpath Visibility

Individual operation toolpaths may need explicit visibility toggling:

```python
for op in get_all_operations(setup):
    if op.hasToolpath:
        op.isToolpathVisible = True
adsk.doEvents()
time.sleep(0.5)
```

### ViewOrientations (Milling Only)

Standard `ViewOrientations` work in **world/model coordinates**, NOT in the setup's WCS. This is fine for milling where the WCS usually aligns with the model, but wrong for turning setups.

```python
camera = viewport.camera
camera.viewOrientation = adsk.core.ViewOrientations.FrontViewOrientation
viewport.camera = camera
adsk.doEvents()
viewport.fit()
```

Available orientations:
- `IsoTopRightViewOrientation`
- `TopViewOrientation`
- `FrontViewOrientation`
- `RightViewOrientation`
- (and others: Bottom, Back, Left, IsoTopLeft, etc.)

### Custom Camera Positions (Turning)

For turning setups, manually set `eye`, `target`, and `upVector` to get the lathe-correct orientation (Z horizontal right, X up):

```python
# Get model center and distance from a fit view
viewport.fit()
base_cam = viewport.camera
cx, cy, cz = base_cam.target.x, base_cam.target.y, base_cam.target.z
ex, ey, ez = base_cam.eye.x, base_cam.eye.y, base_cam.eye.z
dist = ((ex-cx)**2 + (ey-cy)**2 + (ez-cz)**2) ** 0.5

# Side view: operator looking from Y+, Z horizontal right, X up
camera = viewport.camera
camera.isSmoothTransition = False  # Snap, don't animate
camera.eye = adsk.core.Point3D.create(cx, cy + dist, cz)
camera.target = adsk.core.Point3D.create(cx, cy, cz)
camera.upVector = adsk.core.Vector3D.create(1, 0, 0)  # X is up
viewport.camera = camera
viewport.fit()
```

**Lathe camera convention:**
| View | Eye Position | Up Vector | Shows |
|------|-------------|-----------|-------|
| Side (operator) | (cx, cy+D, cz) | (1,0,0) | Z right, X up — main profile |
| Isometric | (cx+D*0.5, cy+D*0.6, cz+D*0.4) | (1,0,0) | 3D from front-above-right |
| End-on | (cx, cy, cz+D) | (1,0,0) | Looking down spindle at face |
| Alt iso | (cx+D*0.5, cy+D*0.6, cz-D*0.4) | (1,0,0) | 3D from front-above-left (chuck side) |

**Assumption:** Model Z axis = spindle axis. This is the standard for turning parts modeled in Fusion. If a part was modeled with a different axis as the spindle, these camera positions would be wrong.

### Saving Screenshots

```python
viewport.saveAsImageFile(filepath, width, height)
# width/height in pixels, e.g., 1920x1080
```

### Timing / Event Loop

Fusion's viewport doesn't update synchronously. Always call:
```python
adsk.doEvents()   # Process pending UI events
time.sleep(0.3)   # Wait for rendering to finish
```

After ANY camera change, fit, or activation. Without this, screenshots may capture the previous state.

---

## WCS G-Code Mapping

| WCS Number | G-Code |
|------------|--------|
| 1 | G54 |
| 2 | G55 |
| 3 | G56 |
| 4 | G57 |
| 5 | G58 |
| 6 | G59 |
| 7+ | G54.1 P1, P2, ... |

---

## Manual NC Operations

Manual NC operations have a different object type and don't carry normal tool data. The comment text can come from multiple sources (checked in order):

1. Brackets in operation name: `Manual NC1 [Comment text]`
2. Parameters: `nc_comment`, `comment`, `manualNC_comment`, `notes`, etc.
3. `operation.comment` property
4. `operation.notes` parameter

---

## Common Pitfalls

1. **`tool_bodyLength` not `tool_lengthBelowHolder`** — The Fusion UI label "Length below holder" maps to the internal parameter `tool_bodyLength`.

2. **Units are ALWAYS cm** — Even if the Fusion document is set to inches, internal API values are in cm.

3. **ViewOrientations ignore WCS** — They use model coordinates. For turning, you must set camera eye/target/up manually.

4. **`adsk.doEvents()` is essential** — Without it, the UI won't update between your API calls and screenshots will be wrong.

5. **`setup.activate()` doesn't change the camera** — It makes the setup's stock/toolpaths visible, but the viewport orientation stays as-is.

6. **CAM workspace must be active** — Stock and toolpath rendering only happens in Manufacturing workspace. Design workspace won't show CAM visuals.

7. **Parameter `.value` may be a Value object** — Always check `hasattr(val, 'value')` and unwrap if needed.

8. **Text parameters have surrounding quotes** — `param.expression` for text fields returns `'quoted text'` — strip the quotes.

9. **`viewport.fit()` preserves orientation** — It adjusts distance/zoom to fit the model but keeps the current view direction and up vector.

10. **Selecting the setup in the browser** — `ui.activeSelections.add(setup)` triggers the full visual state (stock overlay, toolpath previews) similar to clicking the setup node.

---

## Stickout Calculation (Turning)

Stickout = distance from chuck face to end of stock. The export tries these sources in order:

1. `turning_stockStickout` — direct stickout parameter (preferred)
2. `turning_chuckZOffset` — chuck Z position (stored as `chuck_position`)
3. `abs(job_stockZHigh - job_stockZLow)` — stock length from Z bounds (fallback)

If only stock length is available, it's used as an approximation for stickout.

All values converted from cm to inches before storing in JSON.

---

## Debugging Workflow

1. Run export on a test file
2. Open `ProShop Exports/[docname]/proshop_data.json`
3. Check `wcs._all_params` for the full list of parameters on each setup
4. Look for any turning-specific parameters you need
5. Add them to the export script by name

The `_all_params` dump captures every parameter name and its expression value. This is the fastest way to discover new parameters when Fusion updates or when encountering unfamiliar setup types.

---

## Operation Type Detection

Operations have an `objectType` string that includes the class name:

```python
# Returns something like "adsk.cam::MillingOperation" or "adsk.cam::ManualNCOperation"
operation.objectType
```

Useful for Manual NC detection:

```python
is_manual_nc = 'ManualNCOperation' in operation.objectType
```

Operations also have a `strategy` parameter that returns the specific strategy (e.g., "face", "pocket2d", "adaptive2d"):

```python
strategy_param = operation.parameters.itemByName('strategy')
if strategy_param:
    strategy_name = strategy_param.expression  # e.g., "face"
```

Fallback: parse the last segment of `objectType`:

```python
op_type = operation.objectType.split('::')[-1]  # e.g., "MillingOperation"
```

---

## Document Handling

```python
doc = app.activeDocument
doc.name        # e.g., "10983 v2.f3d" — may include .f3d extension
```

Clean up for folder/file naming:

```python
doc_name = doc.name.replace(' ', '_').replace('.f3d', '')
```

---

## Export Output Structure

The script creates this folder layout:

```
ProShop Exports/[DocumentName]/
├── proshop_data.json          # All CAM data (setups, operations, tools, WCS)
├── proshop_operations.txt     # Human-readable operation summary
├── proshop_mapping.json       # Part:Op mapping (created by GUI, saved for reuse)
└── screenshots/
    ├── setup1_SetupName_side.png   # (turning) or setup1_SetupName_iso.png (milling)
    ├── setup1_SetupName_iso.png
    ├── setup1_SetupName_end.png    # (turning) or setup1_SetupName_front.png (milling)
    └── setup1_SetupName_alt.png    # (turning) or setup1_SetupName_right.png (milling)
```

### JSON Structure

```json
{
  "document_name": "10983 v2",
  "export_date": "2026-02-05 14:30:00",
  "setups": [
    {
      "name": "Setup 1",
      "program_number": "O1001",
      "program_comment": "Part Name",
      "operations": [
        {
          "sequence": 1,
          "name": "Face1",
          "type": "face",
          "is_manual_nc": false,
          "manual_nc_comment": "",
          "tool": {
            "number": 1,
            "product_id": "TH495-TP496",
            "body_length": 6.35,
            "holder_description": "BT40_ER32"
          },
          "parameters": { "feedCutting": 500, "spindleSpeed": 6000 },
          "machining_time": null,
          "notes": ""
        }
      ],
      "stock": { "mode": "from solid", "offsetsides": 0.0 },
      "wcs": {
        "gcode": "G54",
        "number": 1,
        "origin_mode": "Model front",
        "stickout": 2.5,
        "_all_params": { "...": "all setup params for debugging" }
      },
      "screenshots": ["setup1_Setup_1_side.png", "setup1_Setup_1_iso.png"]
    }
  ]
}
```

---

## Fusion → ProShop Field Mapping

How export JSON fields map to ProShop Sequence Detail API fields:

| Fusion Export (JSON) | ProShop API Field | Notes |
|---------------------|-------------------|-------|
| `tool.product_id` | `tool` | Split at `-` for body/insert |
| `tool.body_length` | `outOfHolder` | cm / 2.54 → inches, formatted `"X.XXXX"` |
| `tool.holder_description` | `holder` | Spaces replaced with underscores |
| `operation.name` | `sequenceDescription` | Prefixed with tool number: `"T1: Face1"` |
| (split from product_id) | `gTypeInsert` | Second half of hyphenated tool ID |

**Fields NOT to use:** `ncDescription` overwrites the Description column in ProShop — do not write to it. `machineToolNumber` does not exist in the GraphQL schema.

---

## Script Troubleshooting

### Script Runs But No Output

The Fusion script can fail silently. Common causes:

1. **Import errors** — If `adsk.cam` fails to import, no error shown. Check Fusion's Text Commands panel.
2. **Path issues** — `OUTPUT_FOLDER` path doesn't exist and `os.makedirs` fails silently in the outer try/except.
3. **No CAM data** — Script returns early if `cam` is None (user is in Design workspace, not Manufacturing).
4. **Wrong script location** — Dev copy (`EXPORT_TO_PROSHOP.py` with underscore) vs Fusion copy (`EXPORT TO PROSHOP.py` with space) — make sure you deployed the latest.

### How to Debug

- The script shows a message box with the export folder path on start — if you don't see this, the script isn't running at all.
- Check Fusion's **Text Commands** panel (View → Text Commands) for Python tracebacks.
- Add `ui.messageBox('checkpoint')` at key points to trace execution.

### Deployment Reminder

The dev file and Fusion script have different filenames:
- **Dev:** `D:\Dropbox\...\EXPORT_TO_PROSHOP.py` (underscore)
- **Fusion:** `C:\Users\TRAXIS\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\Scripts\EXPORT TO PROSHOP\EXPORT TO PROSHOP.py` (spaces)

Always copy from dev → Fusion after making changes.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-02-05 | Consolidated info from all project docs into this reference |
| 2026-02-05 | Added turning setup detection (`is_turning_setup`) |
| 2026-02-05 | Fixed `origin_mode` key (was `originmode`) |
| 2026-02-05 | Added stickout/chuck_position/stock_length to WCS data |
| 2026-02-05 | Added `_all_params` debug dump to JSON output |
| 2026-02-05 | Custom camera positions for lathe screenshots (Z right, X up) |
| 2026-02-05 | Manufacturing workspace activation before screenshots |
| 2026-02-05 | Browser selection + toolpath visibility before screenshots |
| 2026-01-19 | Discovered `tool_bodyLength` = "Length below holder" |
| 2026-01-19 | Discovered cm internal units |
