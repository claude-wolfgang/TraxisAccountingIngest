# Claude Code Task: Fusion 360 Automatic Program Naming Add-in

## Project: 12. FASData Implementation (Extension) / ProShop Bridge Enhancement

## Overview

Build a Fusion 360 add-in that automatically generates standardized NC program names based on part number and setup number, with automatic versioning. This ensures every program leaving Fusion follows the convention:

```
{PartNumber}_OP{XX}_v{N}.nc
```

Example: `3847-C_OP60_v2.nc`

This integrates with the Shop Hub ecosystem — when programs follow this convention, the transfer service can parse them, display metadata on the dashboard, and maintain audit trails.

---

## Naming Convention

### Format
```
{PartNumber}_OP{OperationNumber}_v{Version}.nc
```

### Operation Number Mapping
| Setup # | Operation # |
|---------|-------------|
| Setup 1 | OP60 |
| Setup 2 | OP70 |
| Setup 3 | OP80 |
| Setup 4 | OP90 |
| Setup 5 | OP100 |
| Setup 6 | OP110 |

Formula: `OP = 60 + (SetupNumber - 1) * 10`

### Version Numbering
- First post: v1
- Each subsequent post of the same part/op: increment version
- Version determined by checking existing files in target folder

### Examples
```
3847-C_OP60_v1.nc    (Part 3847-C, Setup 1, first post)
3847-C_OP60_v2.nc    (Part 3847-C, Setup 1, revised)
3847-C_OP70_v1.nc    (Part 3847-C, Setup 2, first post)
4521-A_OP60_v1.nc    (Part 4521-A, Setup 1, first post)
```

---

## Program Header Comment

The add-in should inject a standardized header comment into the posted G-code:

```gcode
O1001 (3847-C_OP60_v2)
(PART: 3847-C)
(OP: 60)
(VERSION: 2)
(POSTED: 2026-02-19 14:32:07)
(MACHINE: FANUC Mill)
(PROGRAMMER: Wolfgang)
G90 G54 G17
...
```

This header is readable by FOCAS (first line comment) and provides full traceability.

---

## Fusion 360 Add-in Architecture

### Option A: Extend ProShop Bridge Add-in

The existing ProShop Bridge add-in is at:
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\ProShopBridge\
```

Could add a "Post with Naming" command alongside existing functionality.

### Option B: Standalone Add-in

New add-in focused solely on posting with standardized naming:
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\TraxisPostProcessor\
```

**Recommendation:** Option A if ProShop Bridge is actively used and stable. Option B if you want to keep concerns separated.

---

## Implementation Details

### Part 1: Get Part Number

**Sources (in priority order):**

1. **Document property** — Check if document has a custom "PartNumber" attribute
2. **Document name** — Parse from filename if it follows a pattern
3. **User prompt** — Ask user to enter part number if not found

```python
def get_part_number(document):
    # Try custom attribute first
    attrs = document.attributes
    part_attr = attrs.itemByName('Traxis', 'PartNumber')
    if part_attr:
        return part_attr.value
    
    # Try parsing from document name
    # e.g., "3847-C Rev 2.f3d" → "3847-C"
    name = document.name
    match = re.match(r'^(\d{4,5}-?[A-Z]?)', name)
    if match:
        return match.group(1)
    
    # Prompt user
    return prompt_for_part_number()
```

**Store for future use:**
Once part number is entered, save it as a document attribute so it persists.

### Part 2: Get Setup Number

```python
def get_setup_number(setup):
    """
    Extract setup number from Fusion setup object.
    Setup names are typically "Setup1", "Setup2", etc.
    """
    cam = document.design.cam
    setups = cam.setups
    for i, s in enumerate(setups):
        if s == setup:
            return i + 1  # 1-based
    return 1
```

### Part 3: Calculate Operation Number

```python
def get_operation_number(setup_number):
    """
    Setup 1 → OP60
    Setup 2 → OP70
    etc.
    """
    return 60 + (setup_number - 1) * 10
```

### Part 4: Determine Version

```python
def get_next_version(output_folder, part_number, op_number):
    """
    Check existing files and return next version number.
    """
    pattern = f"{part_number}_OP{op_number}_v*.nc"
    existing = glob.glob(os.path.join(output_folder, pattern))
    
    if not existing:
        return 1
    
    # Extract version numbers
    versions = []
    for f in existing:
        match = re.search(r'_v(\d+)\.nc$', f)
        if match:
            versions.append(int(match.group(1)))
    
    return max(versions) + 1 if versions else 1
```

### Part 5: Generate Filename

```python
def generate_program_name(part_number, setup_number, output_folder):
    op_number = get_operation_number(setup_number)
    version = get_next_version(output_folder, part_number, op_number)
    
    filename = f"{part_number}_OP{op_number}_v{version}.nc"
    return filename, op_number, version
```

### Part 6: Modify Post-Processor Output

The add-in needs to inject the header comment. Options:

**Option A: Custom post-processor**
Modify the .cps file to read properties and generate header.

**Option B: Post-process the output**
Let Fusion post normally, then prepend the header to the .nc file.

**Recommendation:** Option B is simpler and doesn't require maintaining custom post-processors.

```python
def inject_header(nc_file_path, part_number, op_number, version, machine):
    with open(nc_file_path, 'r') as f:
        content = f.read()
    
    # Find O-number line or first line
    lines = content.split('\n')
    
    # Build header
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    header_comment = f"({part_number}_OP{op_number}_v{version})"
    
    metadata = [
        f"(PART: {part_number})",
        f"(OP: {op_number})",
        f"(VERSION: {version})",
        f"(POSTED: {timestamp})",
        f"(MACHINE: {machine})",
    ]
    
    # If first line is O-number, insert comment on same line
    if lines[0].startswith('O'):
        o_line = lines[0].split('(')[0].strip()  # Remove any existing comment
        lines[0] = f"{o_line} {header_comment}"
        # Insert metadata after O-line
        for i, m in enumerate(metadata):
            lines.insert(1 + i, m)
    else:
        # Prepend everything
        lines = [f"O0001 {header_comment}"] + metadata + lines
    
    with open(nc_file_path, 'w') as f:
        f.write('\n'.join(lines))
```

### Part 7: Output Folder Structure

Default output location:
```
D:\Dropbox\NC Programs\{PartNumber}\{filename}
```

Example:
```
D:\Dropbox\NC Programs\3847-C\3847-C_OP60_v2.nc
```

Create part folder if it doesn't exist.

```python
NC_PROGRAMS_ROOT = r"D:\Dropbox\NC Programs"

def get_output_path(part_number, filename):
    part_folder = os.path.join(NC_PROGRAMS_ROOT, part_number)
    os.makedirs(part_folder, exist_ok=True)
    return os.path.join(part_folder, filename)
```

---

## User Interface

### Command: "Post with Traxis Naming"

Add a button to the CAM toolbar or right-click context menu on a Setup.

**Dialog fields:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| Part Number | Text | Auto-detected | Editable, saved to document |
| Setup | Dropdown | Current setup | Select which setup to post |
| Operation # | Display | Calculated | Shows OP60, OP70, etc. |
| Version | Display | Auto | Shows what version this will be |
| Output Folder | Folder picker | NC Programs root | Can override |
| Post Processor | Dropdown | Last used | Standard Fusion post selector |
| Machine | Dropdown | FANUC Mill | For header comment |

**Preview:**
```
Output: D:\Dropbox\NC Programs\3847-C\3847-C_OP60_v2.nc
```

**Buttons:**
- [Post] — Generate the file
- [Post & Open Folder] — Generate and open explorer to the folder
- [Cancel]

### Success Notification

After posting:
```
✓ Posted successfully!

File: 3847-C_OP60_v2.nc
Location: D:\Dropbox\NC Programs\3847-C\
Version: 2 (previous: v1)

[Open Folder] [Copy Path] [OK]
```

---

## Integration Points

### 1. Shop Hub Dashboard

Once programs follow this convention, Shop Hub can:
- Parse program comment via FOCAS
- Display part number, op, version on machine card
- Show "3847-C OP60 v2" instead of just "O1234"

### 2. ProShop

When attaching program to operation:
- Dropbox link points to specific version: `.../3847-C/3847-C_OP60_v2.nc`
- Or to "latest" via a symlink/shortcut (future enhancement)

### 3. Program Transfer Service

Transfer service can:
- Validate filename matches expected pattern
- Log transfers with full provenance
- Prevent loading wrong version

---

## File Locations

### Add-in Location
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\TraxisPostProcessor\
├── TraxisPostProcessor.py      # Main add-in
├── TraxisPostProcessor.manifest # Add-in manifest
├── commands/
│   └── post_with_naming.py     # Post command implementation
└── lib/
    ├── naming.py               # Filename generation logic
    └── header.py               # G-code header injection
```

### NC Programs Output
```
D:\Dropbox\NC Programs\
├── 3847-C\
│   ├── 3847-C_OP60_v1.nc
│   ├── 3847-C_OP60_v2.nc
│   └── 3847-C_OP70_v1.nc
├── 4521-A\
│   └── ...
```

### Reference: Existing ProShop Bridge
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\ProShopBridge\
```

Check `docs/proshop-bridge.md` for architecture details.

---

## Testing

### Test Cases

1. **First post of new part**
   - Input: Part 9999-X, Setup 1, no existing files
   - Expected: `9999-X_OP60_v1.nc`

2. **Revision of existing**
   - Input: Part 3847-C, Setup 1, v1 and v2 exist
   - Expected: `3847-C_OP60_v3.nc`

3. **Second setup**
   - Input: Part 3847-C, Setup 2
   - Expected: `3847-C_OP70_v1.nc`

4. **Part number from document**
   - Input: Document named "3847-C Assembly.f3d"
   - Expected: Auto-detects "3847-C"

5. **Header injection**
   - Verify O-line has comment: `O1001 (3847-C_OP60_v1)`
   - Verify metadata lines present

6. **Folder creation**
   - Post to new part number
   - Verify folder created in NC Programs

### Manual Testing

1. Open a CAM document in Fusion
2. Run the add-in command
3. Verify dialog shows correct auto-detected values
4. Post and verify:
   - File created in correct location
   - Filename follows convention
   - Header comment is correct
   - File opens in NC editor without errors

---

## Future Enhancements

1. **Auto-upload to ProShop** — After posting, automatically attach file link to the operation in ProShop

2. **Batch post** — Post all setups in a document at once

3. **Version diff** — Show what changed between versions (tool paths, parameters)

4. **Machine-specific post processors** — Auto-select post based on target machine

5. **Sync with Shop Hub** — Notify Shop Hub when new program is posted

---

## Dependencies

- Fusion 360 API (Python)
- Access to `D:\Dropbox\NC Programs\` folder
- Standard post-processors (FANUC, etc.)

---

## Success Criteria

- [ ] Add-in installs and appears in Fusion 360
- [ ] Part number auto-detected from document or prompted
- [ ] Setup number correctly identified
- [ ] Operation number calculated (60, 70, 80...)
- [ ] Version auto-incremented based on existing files
- [ ] Filename follows `PART_OP_v#.nc` convention
- [ ] Header comment injected with full metadata
- [ ] Output folder structure maintained
- [ ] Shop Hub can parse the program comment

---

## Final Step: Update Documentation

After completing this task, update:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\FASData System Reference.md
```

And create/update:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\docs\fusion-post-naming.md
```

Document:
- Add-in installation steps
- Naming convention specification
- Configuration options
- Troubleshooting
