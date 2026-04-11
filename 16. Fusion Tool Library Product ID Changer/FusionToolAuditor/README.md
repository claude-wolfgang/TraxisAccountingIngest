# FusionToolAuditor v1.0

Fusion 360 add-in to audit and edit Product IDs in tool libraries for ProShop ERP integration.

## Purpose

ProShop Bridge requires Fusion tools to have valid ProShop tool IDs in the **Product ID** field. Many tools currently have manufacturer EDPs (like "74456-C3") instead of ProShop IDs (like "B259"). This add-in helps you:

1. View all tools in any library
2. Identify tools missing Product IDs
3. Auto-extract IDs from descriptions
4. Look up EDPs to find ProShop IDs
5. Export modified libraries for reimport

## Installation

### Windows
Copy the entire `FusionToolAuditor` folder to:
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\
```

### Mac
```
~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/
```

The folder must contain:
- `FusionToolAuditor.py`
- `FusionToolAuditor.manifest`
- `palette.html`

## Usage

1. Open Fusion 360
2. Press **Shift+S** → Scripts and Add-Ins
3. Go to **Add-Ins** tab
4. Select **FusionToolAuditor** → Click **Run**
5. The Tool Library Auditor palette opens

## Features

### Library Browser
- Select any Local, Cloud, or Document library from dropdown
- Shows all tools with: T#, Description, Type, Diameter, Product ID
- Yellow/gold rows = missing Product ID
- Check "Missing only" to filter

### Auto-Extract IDs (Purple Button)
Scans descriptions for ProShop ID patterns and fills Product ID field.

**Pattern:** 1-2 letters + 1-4 digits at start of description

| Description | Extracted ID |
|-------------|--------------|
| A10 3FL 3/8" Flat Endmill | A10 |
| B259 HARVEY - 74456-C3 | B259 |
| L18 1/4 Diam 90° Chamfer | L18 |

### Lookup by EDP (Orange Button)
If Product ID contains an EDP (not a ProShop ID), searches ProShop for matching tool.

Requires ProShop data loaded first (click Load button).

### EDP → Vendor (Brown Button)
Moves EDP from Product ID to Vendor field, then looks up ProShop ID.

**Before:**
```
Product ID: 74456-C3
Vendor: HARVEY TOOL
```

**After:**
```
Product ID: B259 (from ProShop lookup)
Vendor: HARVEY TOOL | 74456-C3
```

### Export JSON (Gray Button)
Exports the library with all your modifications to a JSON file.

**Workflow for Cloud libraries:**
1. Make all your changes in the UI
2. Click Export JSON → save file
3. In Fusion: Tool Library → right-click Local → Import
4. Select your exported JSON
5. New library created with your changes

### ProShop Lookup Column
Type to search ProShop tools by number or description. Click a result to populate Product ID.

### Load Button (in stats bar)
Manually triggers ProShop API fetch. Shows tool count when loaded.

## Product ID Formats

### Standard tools
```
A10    - End mill
D225   - Drill
B259   - Ball end mill
```

### Indexable tools (body + insert)
```
I460/G458   - Body I460 with insert G458
```

## Known Limitations

### Cloud/Local Libraries Don't Save
The Fusion API returns **copies** of library items, not references. Changes don't persist.

**Workaround:** Use Export JSON → reimport as new library.

### Document Libraries Work
Tools in the active CAM document's library can be saved directly.

### ProShop Connection
The ProShop API works from command line but may have issues inside Fusion's Python environment. Use the Load button to retry.

## Files

| File | Purpose |
|------|---------|
| `FusionToolAuditor.py` | Main add-in Python code |
| `FusionToolAuditor.manifest` | Fusion add-in manifest |
| `palette.html` | HTML/CSS/JS for the UI |
| `README.md` | This documentation |

## ProShop API

**Credentials (OAuth 2.0):**
```
Client ID: BA16-EFAF-B154
Scope: parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r
```

**Endpoints:**
```
Token: https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
GraphQL: https://traxismfg.adionsystems.com/api/graphql
```

**Tool fields used:**
- `toolNumber` - ProShop ID (A10, B259, etc.)
- `description` - Tool description
- `cutDiameter` - Diameter in inches
- `approvedBrands.vendorToolId` - EDP numbers

## Version History

### v1.0 (February 2026)
- Initial release
- Library browser with all locations
- Auto-Extract IDs from descriptions
- EDP → Vendor migration
- ProShop lookup integration
- Export JSON for Cloud library workaround

## Future Enhancements

- [ ] Batch processing multiple .f3d files
- [ ] Fix ProShop API connection inside Fusion
- [ ] Direct Cloud library write (if API improves)

## Troubleshooting

**"ProShop: 0 tools"**
- Click the Load button to retry
- Check network connection
- API may have SSL issues in Fusion's environment

**Changes don't save to Cloud library**
- This is an API limitation
- Use Export JSON → reimport workflow

**No Document library in dropdown**
- Open a CAM file with toolpaths
- Tools used in operations appear in Document library

## Author

Traxis Manufacturing - Wolfgang
Built with Claude Code, February 2026
