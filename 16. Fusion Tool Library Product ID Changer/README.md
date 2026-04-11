# Fusion Tool Library Product ID Changer

Tools for auditing and correcting Product IDs in Fusion 360 tool libraries so they match ProShop ERP tool numbers. This is part of the Traxis Manufacturing automation pipeline — ProShop Bridge requires every Fusion tool to have a valid ProShop tool ID in its Product ID field.

## The Problem

Fusion 360 tools have a **Product ID** field (`tool_productId`). At Traxis, this field should contain the **ProShop tool number** (e.g., `A10`, `B259`, `D225`). Many tools instead have the **manufacturer's EDP/catalog number** in that field (e.g., `74456-C3`, `20165`), or the field is blank entirely. When Product IDs are wrong or missing, ProShop Bridge can't match Fusion tools to ProShop library entries and the automation pipeline breaks.

## Components

### 1. FusionToolAuditor (Add-in) — Primary Tool

Interactive palette UI inside Fusion 360 for bulk auditing and editing Product IDs.

**Features:**
- Browse Local, Cloud, Fusion360, and Document tool libraries
- View all tools with T#, Description, Type, Diameter, Product ID, Vendor
- Highlight tools with missing Product IDs (gold rows)
- **Auto-Extract IDs** — regex-extract ProShop IDs from descriptions (e.g., `A10 3FL 3/8" Flat Endmill` -> `A10`)
- **Lookup by EDP** — cross-reference current Product IDs against ProShop's EDP database
- **EDP to Vendor** — move manufacturer EDPs from Product ID to Vendor field, then look up the correct ProShop ID
- **ProShop Lookup** — searchable dropdown to manually find and assign ProShop tool numbers
- **Export JSON** — save modified library to JSON file for reimport into Fusion
- **Save Changes** — direct save for Document libraries (the only library type Fusion's API supports writing to)

**Manifest:** v1.0.0 | Type: add-in | runOnStartup: false

### 2. ExportToolLibrary (Script)

One-shot script to export any tool library to JSON and CSV for offline review or spreadsheet analysis.

**Outputs:**
- `{library}_full.json` — complete tool data including raw JSON from each tool
- `{library}_summary.csv` — flattened table with T#, Description, Product ID, Type, Diameter, Flute Length, Body Length, OAL, Flutes, Corner Radius, Vendor, Comment, Holder, GUID

**Manifest:** Type: script (no version)

### 3. TestScripts (Dev utilities)

Three minimal Fusion scripts used during development to verify API behavior:

| Script | Tests |
|--------|-------|
| Test1_DiscoverLibraries | Can the API enumerate library locations and counts? |
| Test2_ReadOneTool | Can we read parameters from a single tool? |
| Test3_ToJsonStructure | Does `toJson()` work and what keys does it return? |

These are not needed for production use.

## Installation

### FusionToolAuditor (add-in)

Create a directory symlink so Fusion finds it at startup:

**Windows (Admin CMD):**
```
mklink /D "%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToolAuditor" "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\16. Fusion Tool Library Product ID Changer\FusionToolAuditor"
```

**Or copy the folder manually to:**
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToolAuditor\
```

### ExportToolLibrary (script)

Create a directory symlink:

**Windows (Admin CMD):**
```
mklink /D "%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\ExportToolLibrary" "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\16. Fusion Tool Library Product ID Changer\ExportToolLibrary"
```

**Or copy the folder manually to:**
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\ExportToolLibrary\
```

## Usage

### Auditing Product IDs (FusionToolAuditor)

1. Open Fusion 360
2. Press **Shift+S** -> Scripts and Add-Ins
3. Go to the **Add-Ins** tab, select **FusionToolAuditor**, click **Run**
4. The Tool Library Auditor palette opens

**Typical workflow for Cloud libraries:**

1. Select a Cloud library from the dropdown
2. Click **Auto-Extract IDs** to pull ProShop IDs from tool descriptions
3. Click the ProShop **Load** button (in the stats bar) to fetch the EDP database
4. Click **EDP to Vendor** to migrate EDPs out of Product ID and look up correct ProShop IDs
5. Manually fix any remaining tools using the ProShop Lookup search column
6. Click **Export JSON** to save the modified library
7. In Fusion's Tool Library panel: right-click Local -> Import -> select your exported JSON

**For Document libraries (tools used in the active CAM file):**
1. Open a CAM file with toolpaths
2. Run FusionToolAuditor
3. Select the `[Document]` library
4. Make changes, then click **Save Changes** (writes directly — no export needed)

### Exporting a Library (ExportToolLibrary)

1. Press **Shift+S** -> Scripts and Add-Ins
2. In the **Scripts** tab, select **ExportToolLibrary**, click **Run**
3. Enter the number of the library to export
4. Choose an output folder
5. Two files are created: `_full.json` and `_summary.csv`

## ProShop Tool ID Formats

| Format | Example | Meaning |
|--------|---------|---------|
| Letter + digits | `A10` | Standard tool (end mill, drill, etc.) |
| Body/Insert | `I460/G458` | Indexable tool — body ID / insert ID |

EDPs (manufacturer catalog numbers) look like: `74456-C3`, `20165`, `65250045`

## Known Limitations

- **Cloud and Local libraries are read-only** via the Fusion API. The API returns copies of tool data, not references. Modifications don't persist. Workaround: Export JSON -> reimport as a new Local library.
- **Document libraries support direct save** via `documentToolLibrary.update()`.
- **ProShop API connection** works from CLI but can have SSL issues inside Fusion's embedded Python environment. The Load button retries the connection.
- **No batch mode** — you must open and process one library at a time.

## Dependencies

- Fusion 360 (Manufacture workspace with CAM enabled)
- ProShop ERP account at `traxismfg.adionsystems.com` (for ProShop lookup features)
- No external Python packages — uses only stdlib (`json`, `urllib`, `csv`, `os`, `threading`) and `adsk` modules

## ProShop API

| Item | Value |
|------|-------|
| Token URL | `https://traxismfg.adionsystems.com/home/member/oauth/accesstoken` |
| GraphQL URL | `https://traxismfg.adionsystems.com/api/graphql` |
| Auth method | OAuth 2.0 client_credentials |
| Key fields | `toolNumber`, `description`, `cutDiameter`, `approvedBrands.vendorToolId` |

Credentials are hardcoded in `FusionToolAuditor.py` (lines 32-36).

## File Structure

```
16. Fusion Tool Library Product ID Changer/
  README.md                          # This file
  CLAUDE.md                          # Project context and technical notes
  FUSION_TOOL_AUDITOR_CC.md          # Original build specification
  FusionToolAuditor/                 # Fusion 360 Add-in (-> AddIns/)
    FusionToolAuditor.py             #   Main add-in code (682 lines)
    FusionToolAuditor.manifest       #   Add-in manifest v1.0.0
    palette.html                     #   HTML/CSS/JS UI (581 lines)
    README.md                        #   Component-level docs
  ExportToolLibrary/                 # Fusion 360 Script (-> Scripts/)
    ExportToolLibrary.py             #   Export script (408 lines)
    ExportToolLibrary.manifest       #   Script manifest
    README.md                        #   Component-level docs
  TestScripts/                       # Dev/debug scripts
    Test1_DiscoverLibraries.py       #   Library enumeration test
    Test2_ReadOneTool.py             #   Single tool read test
    Test3_ToJsonStructure.py         #   JSON structure test
    *.manifest                       #   Corresponding manifests
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | February 2026 | Initial release — library browser, auto-extract IDs, EDP-to-Vendor migration, ProShop lookup, JSON export, Document library save |

## Author

Traxis Manufacturing — Wolfgang
Built with Claude Code, February 2026
