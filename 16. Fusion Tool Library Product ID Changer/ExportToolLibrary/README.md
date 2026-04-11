# ExportToolLibrary v2.0

Fusion 360 script that exports tool libraries to JSON and CSV files for ProShop ERP integration.

## Installation

### Windows
Copy the entire `ExportToolLibrary` folder to:
```
%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\
```

### Mac
Copy the entire `ExportToolLibrary` folder to:
```
~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/
```

The folder should contain:
- `ExportToolLibrary.py`
- `ExportToolLibrary.manifest`
- `README.md` (optional)

## Usage

1. Open Fusion 360
2. Go to **Utilities** > **Scripts and Add-Ins** (or press Shift+S)
3. In the Scripts tab, find **ExportToolLibrary**
4. Click **Run**
5. A dialog will show all available tool libraries:
   - **Local** - Libraries stored on your computer
   - **Cloud** - Libraries in your Autodesk cloud account
   - **Fusion360** - Built-in Fusion 360 sample libraries
   - **Document** - Tools in the currently open CAM document
6. Enter the number of the library you want to export
7. Choose an output folder
8. The script exports two files:
   - `{library}_full.json` - Complete tool data including individual tool JSON
   - `{library}_summary.csv` - Flattened spreadsheet-friendly format

## Output Files

### CSV Columns

| Column | Description | Notes |
|--------|-------------|-------|
| Tool Number | The tool number (T1, T2, etc.) | From post-process settings |
| Description | Tool description | e.g., "1/2 4FL EM" |
| Product ID | Product ID field | **Key field for ProShop mapping** |
| Type | Tool type | e.g., "flat end mill", "drill" |
| Diameter (in) | Tool diameter | Converted to inches |
| Flute Length (in) | Cutting flute length | Converted to inches |
| Body Length (in) | Length below holder | Maps to ProShop "OOH" |
| Overall Length (in) | Total tool length | Converted to inches |
| Number of Flutes | Flute count | |
| Corner Radius (in) | Corner radius | For bull/ball endmills |
| Vendor | Tool vendor/manufacturer | |
| Comment | Tool comment | |
| Holder Description | Holder/collet info | |
| GUID | Fusion internal ID | Unique identifier |

### JSON Structure

The `_full.json` file contains:
```json
{
  "library_name": "MyLibrary",
  "tool_count": 50,
  "library_json": { ... },  // Raw library export
  "tools": [                // Array of individual tool exports
    {
      "description": "1/2 4FL EM",
      "product-id": "I460",
      "type": "flat end mill",
      "geometry": {
        "DC": 12.7,    // diameter in mm
        "LCF": 25.4,   // flute length in mm
        "LB": 50.8,    // body length in mm
        "OAL": 76.2    // overall length in mm
      },
      ...
    }
  ]
}
```

## ProShop Integration

The **Product ID** field is the key link between Fusion tools and ProShop ERP:

1. Export your library using this script
2. Review the CSV to identify which Product IDs are ProShop IDs vs vendor catalog numbers
3. ProShop tool IDs at Traxis follow patterns like `I460`, `D225` (letter prefix + number)
4. Vendor numbers are typically all-numeric (`4611`) or catalog-style (`A-2-3-015`)

## Troubleshooting

**"No tool libraries found"**
- Make sure you have tool libraries in Fusion. Check the Manufacture workspace > Tool Library panel.
- Cloud libraries require an internet connection.

**Library shows 0 tools**
- The library file may be empty or corrupted.
- Try opening it in Fusion's Tool Library panel to verify.

**Parameters showing as blank**
- Some tool types have different parameters. Lathe tools won't have flute count, etc.
- The script handles missing parameters gracefully.

**Error loading Cloud library**
- Cloud libraries may have access restrictions.
- Try exporting Local libraries first.

## Version History

- **v2.0** - Full rewrite with recursive folder walking, JSON+CSV export, unit conversion
- **v1.0** - Initial prototype
