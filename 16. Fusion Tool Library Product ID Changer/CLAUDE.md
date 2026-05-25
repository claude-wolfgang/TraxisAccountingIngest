# CLAUDE.md — Fusion Tool Library Export & ProShop ID Mapping

## Project Overview

Fusion 360 tools for auditing and fixing Product IDs in tool libraries for ProShop ERP integration. This is part of the Traxis Manufacturing automation effort to bridge Fusion 360 CAM data into ProShop ERP.

**Location:** `Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\16. Fusion Tool Library Product ID Changer`

**Owner:** Wolfgang (CAM programmer, Traxis Manufacturing — 5-person CNC machine shop in Austin, TX)

**Status:** v1.0 Complete (February 2026)

---

## The Problem

Fusion 360 tools have a **Product ID** field (`tool_productId`). We use this field to store the **ProShop tool ID** (e.g., "A10", "B259"). However, many tools have the **manufacturer's EDP/catalog number** in that field instead (e.g., "74456-C3", "20165").

**Solution:** FusionToolAuditor add-in to:
1. View all tools in any library
2. Auto-extract ProShop IDs from descriptions
3. Move EDPs to Vendor field
4. Look up EDPs in ProShop to find tool numbers
5. Export modified libraries for reimport

---

## Project Components

### 1. FusionToolAuditor (Add-in) — PRIMARY TOOL

**Purpose:** Interactive UI to audit and edit Product IDs

**Features:**
| Button | Function |
|--------|----------|
| **Auto-Extract IDs** | Extract "A10" from "A10 3FL 3/8" Flat Endmill" |
| **Lookup by EDP** | Find ProShop ID from EDP number |
| **EDP → Vendor** | Move EDP to Vendor field, lookup ProShop ID |
| **Export JSON** | Save modified library for reimport |
| **Save Changes** | Write to Document library (only) |

**Files:**
```
FusionToolAuditor/
  FusionToolAuditor.py        # Main add-in code
  FusionToolAuditor.manifest  # Fusion manifest
  palette.html                # UI (HTML/CSS/JS)
  README.md                   # Full documentation
```

**Installation:**
```
Windows: %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToolAuditor\
Mac:     ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionToolAuditor/
```

### 2. ExportToolLibrary (Script)

**Purpose:** Export tool libraries to JSON/CSV for analysis

**Files:**
```
ExportToolLibrary/
  ExportToolLibrary.py
  ExportToolLibrary.manifest
  README.md
```

### 3. TestScripts

**Purpose:** Sanity checks for API patterns

**Files:**
```
TestScripts/
  Test1_DiscoverLibraries.py
  Test2_ReadOneTool.py
  Test3_ToJsonStructure.py
```

---

## Key Technical Findings

### API Limitation: Cloud/Local Libraries Are Read-Only

From Autodesk docs:
> "Items in a library don't have a distinct identity... the API object is a **temporary copy** of the data."

**What this means:**
- `toolLib.item(0)` returns a COPY, not a reference
- Modifying the copy doesn't change the library
- Only `DocumentToolLibrary.update()` persists changes

**Workaround:**
1. Make changes in FusionToolAuditor UI
2. Click "Export JSON" → saves modified library
3. In Fusion: Tool Library → right-click Local → Import
4. Creates new library with changes

### ProShop API

**Credentials:** Loaded from `.traxis.env` (searches `~/.traxis.env`, `~/Dropbox/MACHINE COMM Traxis/Keys/.traxis.env`, then project-relative fallback). Keys: `PROSHOP_CLIENT_ID`, `PROSHOP_CLIENT_SECRET`, `PROSHOP_SCOPE`.

**Endpoints:**
```
Token: https://traxismfg.adionsystems.com/home/member/oauth/accesstoken
GraphQL: https://traxismfg.adionsystems.com/api/graphql
```

**Key tool fields:**
- `toolNumber` — ProShop ID (A10, B259, D225)
- `description` — Tool description
- `cutDiameter` — Diameter in inches
- `approvedBrands.vendorToolId` — EDP numbers

**Note:** API works from command line but has SSL issues inside Fusion's Python environment. Use Load button to retry.

---

## ProShop Tool ID Patterns

**ProShop IDs (what we want in Product ID):**
- `A10` — End mill
- `B259` — Ball end mill
- `D225` — Drill
- `I460` — Indexable
- `I460/G458` — Indexable body/insert combo

**EDPs (manufacturer numbers to move to Vendor):**
- `74456-C3` — Harvey Tool
- `20165` — Gorilla Mill
- `65250045` — Accupro

---

## Fusion 360 API Reference

### Library Locations
```python
camMgr = adsk.cam.CAMManager.get()
toolLibs = camMgr.libraryManager.toolLibraries

# Get URL for a location
localURL = toolLibs.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
cloudURL = toolLibs.urlByLocation(adsk.cam.LibraryLocations.CloudLibraryLocation)

# Load library
toolLib = toolLibs.toolLibraryAtURL(libURL)
```

### Document Library (supports write)
```python
cam_product = doc.products.itemByProductType('CAMProductType')
cam_obj = adsk.cam.CAM.cast(cam_product)
docToolLib = cam_obj.documentToolLibrary

# Modify and save
tool = docToolLib.item(0)
tool.parameters.itemByName('tool_productId').value.value = "A10"
docToolLib.update(tool, True)  # This actually saves!
```

### Key Parameters
| Parameter | UI Label | JSON Key |
|-----------|----------|----------|
| `tool_productId` | Product ID | `product-id` |
| `tool_vendor` | Vendor | `vendor` |
| `tool_description` | Description | `description` |
| `tool_diameter` | Diameter | `geometry.DC` (mm) |

### Units
- API: centimeters
- JSON geometry: millimeters
- Display: convert to inches (`/ 25.4` for mm, `/ 2.54` for cm)

---

## Project Status

### Completed ✓
- [x] ExportToolLibrary script (JSON/CSV export)
- [x] FusionToolAuditor add-in
- [x] Library browser (Local, Cloud, Document)
- [x] Auto-Extract IDs from descriptions
- [x] EDP → Vendor migration
- [x] ProShop EDP lookup (900 tools, via API)
- [x] Export JSON workaround for Cloud libraries
- [x] Full documentation

### Known Issues
- [ ] ProShop API connection unreliable inside Fusion (works from CLI)
- [ ] Cloud/Local library saves don't persist (API limitation)

### Future Enhancements
- [ ] Batch processing multiple .f3d files
- [ ] Fix ProShop SSL issues in Fusion Python
- [ ] Direct Cloud library write (if API improves)

---

## Usage Workflow

### For Cloud Libraries (most common)
1. Run FusionToolAuditor add-in
2. Select Cloud library from dropdown
3. Click **Auto-Extract IDs** (extracts from descriptions)
4. Click **EDP → Vendor** (moves EDPs, looks up ProShop IDs)
5. Manually fix any remaining tools
6. Click **Export JSON**
7. In Fusion Tool Library: right-click Local → Import
8. Select exported JSON file

### For Document Libraries
1. Open CAM file with toolpaths
2. Run FusionToolAuditor
3. Select [Document] library
4. Make changes
5. Click **Save Changes** (directly persists)

---

## File Locations

**Project folder:**
```
C:\Users\AbsoluteArm\Dropbox\MACHINE COMM Traxis\
  Proshop Automation and Claude Projects\
    16. Fusion Tool Library Product ID Changer\
```

**Fusion 360 installation:**
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionToolAuditor\
```

**ProShop credentials:**
```
C:\Users\AbsoluteArm\Dropbox\MACHINE COMM Traxis\
  Proshop Automation and Claude Projects\
    1. Proshop Automations\.traxis.env
```

---

## Development Notes

### Fusion Python Environment
- Embedded interpreter, no pip
- Use stdlib + adsk modules only
- urllib works, but SSL can be problematic
- Background threads work but custom events are unreliable

### Debugging
- Errors show in Fusion message boxes
- Add try/except everywhere
- Use `_ui.messageBox()` for debugging output

---

## Interfaces

Produces: Modified Fusion tool-library JSON files (`{"data":[...],"version":N}`) via FusionToolAuditor "Export JSON" and ExportToolLibrary's `_full.json` / `_summary.csv`. Each tool object carries normalized top-level keys (`description`, `product-id`, `vendor`, `type`, `BMC`, `guid`) + nested `geometry` (coded keys: `DC`/`NOF`/`LCF`/`LB`/`OAL`/`RE`/`SFDM`), `post-process` (`number` = tool #), `holder`, `start-values.presets[]` (per-operation feeds/speeds), and a parallel single-quoted `expressions` block.
Consumes: ProShop GraphQL `tools` query (toolNumber/description/cutDiameter/numberOfFlutes/approvedBrands.vendorToolId for EDP lookup); Fusion CAM `libraryManager` (Local/Cloud/Fusion360/Document tool libraries); `.traxis.env` credentials.
Contracts: At Traxis, the Fusion tool `product-id` field holds the **ProShop tool number** (A15, I460/G458), NOT the manufacturer EDP — required for ProShop Bridge tool matching. **External consumer: Toolpath (toolpath.com)** reads the same exported `.json`/`.tools` libraries (static upload) or two-way cloud-syncs them ("Toolpath Managed Libraries" folder). Toolpath's per-operation "Magic Presets" appear to be generated from `geometry` + `BMC` material (not catalog-matched on `product-id`), so the ProShop-ID repurposing of `product-id` is *probably* invisible to Toolpath — UNVERIFIED (see Next Steps).

## Next Steps

- **[Toolpath] Empirically verify whether Toolpath reads `product-id`** (surfaced 2026-05-25). Whole "perfect library for Toolpath" question hinges on this. Test: upload one exported library to Toolpath, note the generated feeds/speeds; change one tool's `product-id` (e.g. `UGMH12S905`→`ZZZ999`) leaving geometry identical, re-upload. Recipes unchanged → product-id is cosmetic to Toolpath and P16's ProShop-ID overwrite causes no conflict (leading hypothesis). Recipes change / catalog match breaks → real conflict, decide where ProShop ID lives. Needs a Toolpath account (Claude can't reach authenticated pages).
- **[Toolpath] Decide ingest path: static `.json`/`.tools` upload vs. live cloud sync.** Cloud sync round-trip is also the most reliable field-mapping probe — enable sync on a throwaway library, let it round-trip, re-export from Fusion, diff against original; whatever Toolpath writes back is the canonical field set. Determines what "perfect" means (write-back safety for cloud sync vs. snapshot simplicity for upload).

---

*Last updated: May 25, 2026 (Toolpath investigation — Interfaces + Next Steps added)*
*Built with Claude Code*
