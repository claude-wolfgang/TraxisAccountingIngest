#!/usr/bin/env python3
"""
Tool Library Updater — CLI for managing ProShop tool library entries.

Subcommands:
    inspect     Query and display current tool records
    create      Create a new tool from manufacturer EDP/catalog number
    find-vpo    Search vendor purchase orders for tool pricing
    scrape      Fetch specs from manufacturer website
    preview     Show before/after diff (dry run, writes nothing)
    update      Execute tool update in ProShop
    download-image  Download product image for manual upload

Usage:
    python tool_update.py inspect D195 D196 --json
    python tool_update.py create --mfg iscar --edp 1955660 --qty 4
    python tool_update.py create --catalog "16ERB 1.25 ISO IC908" --qty 4 --group TN
    python tool_update.py find-vpo D195 --year 2026 --json
    python tool_update.py scrape kennametal "https://kennametal.com/..." --json
    python tool_update.py preview D195 --oal 2.441 --flute-length 0.787 ...
    python tool_update.py update D195 --oal 2.441 ... --confirm
    python tool_update.py download-image "https://..." --output D195.jpg
"""

import argparse
import json
import sys

from proshop_tools import get_clients, get_tool, get_tools, find_tool_vpo_prices, update_tool, add_tool
from description_format import (build_prev_note, append_to_purchasing_notes, map_coating,
                                map_material, map_inscribed_circle, map_insert_shape,
                                build_description, MFG_SHORT)
from mfg_scrapers import scrape_manufacturer, download_product_image
from ai_search import search_tool_specs, map_tool_group


def cmd_inspect(args):
    """Query and display current tool records."""
    tools_client, _ = get_clients()
    tools = get_tools(tools_client, args.tool_numbers)

    if not tools:
        print("No tools found.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(tools, indent=2))
    else:
        for t in tools:
            _print_tool_summary(t)
    return 0


def cmd_find_vpo(args):
    """Search vendor purchase orders for tool pricing."""
    tools_client, _ = get_clients()
    prices = find_tool_vpo_prices(tools_client, args.tool_numbers, year=args.year)

    if args.json:
        print(json.dumps(prices, indent=2))
    else:
        if not prices:
            print("No VPO entries found for these tools.")
            return 1
        for tn, info in sorted(prices.items()):
            print(f"  {tn}: PO {info['po_id']} | {info['date']} | "
                  f"${info['cost_per']}/ea x {info['quantity']} | "
                  f"{info.get('supplier', '')}")
            print(f"         {info['description']}")
    return 0


def cmd_scrape(args):
    """Fetch specs from manufacturer website."""
    specs = scrape_manufacturer(args.manufacturer, args.url)

    if args.json:
        print(json.dumps(specs, indent=2))
    else:
        if specs.get("error"):
            print(f"Error: {specs['error']}", file=sys.stderr)
            return 1
        for k, v in sorted(specs.items()):
            print(f"  {k}: {v}")
    return 0


def cmd_preview(args):
    """Show before/after diff without writing anything."""
    tools_client, _ = get_clients()
    current = get_tool(tools_client, args.tool_number)

    if not current:
        print(f"Tool {args.tool_number} not found.", file=sys.stderr)
        return 1

    changes = _build_update_data(args, current)

    if args.json:
        print(json.dumps({"current": current, "proposed_changes": changes}, indent=2))
    else:
        print(f"\nTool {args.tool_number} -- Proposed Changes:")
        print("-" * 60)
        _print_diff(current, changes, args)
    return 0


def cmd_update(args):
    """Execute tool update in ProShop."""
    tools_client, _ = get_clients()
    current = get_tool(tools_client, args.tool_number)

    if not current:
        print(f"Tool {args.tool_number} not found.", file=sys.stderr)
        return 1

    changes = _build_update_data(args, current)

    if not changes:
        print("No changes to apply.")
        return 0

    # Show preview
    if not args.json:
        print(f"\nTool {args.tool_number} -- Changes to apply:")
        print("-" * 60)
        _print_diff(current, changes, args)

    # Confirm
    if not args.confirm:
        answer = input("\nApply these changes? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return 1

    result = update_tool(tools_client, args.tool_number, changes)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n  {result['toolNumber']} updated successfully.")
        brands = result.get("approvedBrands", {}).get("records", [])
        if brands:
            b = brands[0]
            print(f"  Brand: {b['approvedBrand']} | EDP: {b['vendorToolId']} | ${b['cost']}")
    return 0


def cmd_create(args):
    """Create a new tool from manufacturer specs."""
    # Step 1: Get specs — either from --specs-json or AI search
    if args.specs_json:
        try:
            ai_result = json.loads(args.specs_json)
        except json.JSONDecodeError as e:
            print(f"Invalid --specs-json: {e}", file=sys.stderr)
            return 1
    else:
        if not args.mfg:
            print("--mfg is required unless using --specs-json", file=sys.stderr)
            return 1
        search_id = args.catalog if args.catalog else args.edp
        if not search_id:
            print("--edp or --catalog is required", file=sys.stderr)
            return 1

        print(f"  Searching for {args.mfg.upper()} {search_id}...")
        ai_result = search_tool_specs(args.mfg, args.edp or "", args.catalog)

    if ai_result.get("error"):
        print(f"Error: {ai_result['error']}", file=sys.stderr)
        if ai_result.get("raw"):
            print(f"Raw response:\n{ai_result['raw'][:500]}", file=sys.stderr)
        return 1

    # Step 2: Determine tool group
    tool_type = ai_result.get("tool_type", "unknown")
    group = args.group or map_tool_group(tool_type)
    if not group:
        print(f"Could not determine tool group for type '{tool_type}'.", file=sys.stderr)
        print("Use --group to specify (e.g., --group D, --group EM, --group TN)")
        return 1

    # Step 3: Build create data
    data = _build_create_data(args, ai_result, group)

    # Step 4: Preview
    confidence = ai_result.get("confidence", "unknown")
    source = ai_result.get("source_url", "")

    if args.json:
        print(json.dumps({"tool_type": tool_type, "group": group,
                          "confidence": confidence, "data": data}, indent=2))
        if not args.confirm:
            return 0
    else:
        print(f"\n  New Tool -- Preview")
        print("-" * 60)
        print(f"  Tool Group:  {group} (auto-numbered by ProShop)")
        print(f"  Tool Type:   {tool_type}")
        print(f"  Confidence:  {confidence}")
        if source:
            print(f"  Source:      {source}")
        print()
        for k, v in sorted(data.items()):
            if k == "approvedBrands":
                for b in v:
                    print(f"  {'brand':25s} {b.get('approvedBrand', '?')} | "
                          f"EDP: {b.get('vendorToolId', '?')}")
            else:
                print(f"  {k:25s} {v}")

    # Step 5: Confirm
    if not args.confirm:
        answer = input("\nCreate this tool? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return 1

    # Step 6: Create
    tools_client, _ = get_clients()
    result = add_tool(tools_client, data)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        tn = result.get("toolNumber", "?")
        desc = result.get("description", "")
        print(f"\n  Created {tn}: {desc}")
        print(f"  https://traxismfg.adionsystems.com/procnc/tools/{group}/{tn}")
    return 0


def _build_create_data(args, ai_result, group):
    """Build AddToolInput data from AI search results and CLI args."""
    specs = ai_result.get("specs", {})
    brand_info = ai_result.get("brand", {})
    manufacturer = getattr(args, "mfg", None) or brand_info.get("name", "")

    # Inject metadata into specs for description builder
    specs["_brand"] = brand_info
    specs["_description_hint"] = ai_result.get("description_hint")

    data = {
        "toolGroupLetter": group,
        "status": "Active",
    }

    # Description — always use shop-convention formatter
    tool_type = ai_result.get("tool_type", "unknown")
    data["description"] = build_description(tool_type, specs, manufacturer)

    # Dimensional specs — pass through numeric fields directly
    float_fields = [
        "cutDiameter", "overallLength", "lengthOfCut", "shankDiameter",
        "helixAngle", "cornerRadius", "insertThickness", "numberOfFlutes",
        "numberOfCuttingCorners",
    ]
    for field in float_fields:
        val = specs.get(field)
        if val is not None:
            data[field] = float(val)

    # String fields
    if specs.get("tipAngle"):
        data["tipAngle"] = str(specs["tipAngle"])
    if specs.get("pitch"):
        data["pitch"] = str(specs["pitch"])
    if specs.get("threadsPerInch"):
        data["threadsPerInch"] = str(specs["threadsPerInch"])

    # Boolean fields
    if specs.get("throughCoolant") is not None:
        data["throughCoolant"] = bool(specs["throughCoolant"])
    if specs.get("fullProfile") is not None:
        data["fullProfile"] = bool(specs["fullProfile"])

    # Enum fields — translate from human-readable to ProShop enums
    if specs.get("coating"):
        data["coating"] = map_coating(specs["coating"])
    if specs.get("toolMaterial"):
        mapped = map_material(specs["toolMaterial"])
        if mapped:
            data["toolMaterial"] = mapped
    if specs.get("insertInscribedCircle"):
        mapped = map_inscribed_circle(specs["insertInscribedCircle"])
        if mapped:
            data["insertInscribedCircle"] = mapped
    if specs.get("insertShape"):
        mapped = map_insert_shape(specs["insertShape"])
        if mapped:
            data["insertShape"] = mapped

    # Catalog number
    cat_num = brand_info.get("catalog_number") or brand_info.get("edp")
    if cat_num:
        data["ansiCatalogNumber"] = cat_num

    # Approved brand
    if brand_info.get("name"):
        brand_entry = {"approvedBrand": brand_info["name"].upper()}
        edp = brand_info.get("edp") or brand_info.get("catalog_number")
        if edp:
            brand_entry["vendorToolId"] = str(edp)
        data["approvedBrands"] = [brand_entry]

    # CLI overrides
    if args.qty is not None:
        data["quantity"] = float(args.qty)
    if getattr(args, "location", None):
        data["location"] = args.location

    return data


def cmd_download_image(args):
    """Download product image for manual ProShop upload."""
    saved = download_product_image(args.url, args.output)
    if saved:
        print(f"Saved: {saved}")
        return 0
    else:
        print("Download failed.", file=sys.stderr)
        return 1


def _build_update_data(args, current):
    """Build the update data dict from CLI args."""
    data = {}

    if args.new_description:
        data["description"] = args.new_description
    if args.oal is not None:
        data["overallLength"] = args.oal
    if args.flute_length is not None:
        data["lengthOfCut"] = args.flute_length
    if args.shank_diameter is not None:
        data["shankDiameter"] = args.shank_diameter
    if args.helix_angle is not None:
        data["helixAngle"] = args.helix_angle
    if args.coating:
        data["coating"] = map_coating(args.coating) if args.coating not in (
            "TIALN", "TICN", "C7", "C11", "OTHER"
        ) else args.coating
    if args.catalog_number:
        data["ansiCatalogNumber"] = args.catalog_number
    if args.tip_angle:
        data["tipAngle"] = args.tip_angle

    # Approved brand update
    if args.brand or args.brand_edp or args.brand_cost is not None:
        old_brands = current.get("approvedBrands", {}).get("records", [])
        if old_brands:
            old_edp = old_brands[0].get("vendorToolId", "")
            brand_data = {}
            if args.brand:
                brand_data["approvedBrand"] = args.brand
            if args.brand_edp:
                brand_data["vendorToolId"] = args.brand_edp
            if args.brand_cost is not None:
                brand_data["cost"] = args.brand_cost
            data["approvedBrands"] = [{
                "selector": {"field": "vendorToolId", "value": old_edp},
                "data": brand_data,
            }]

    # Preserve old info in purchasing notes
    if getattr(args, "preserve_old_info", False):
        prev_note = build_prev_note(current)
        existing_notes = current.get("purchasingNotes", "") or ""
        data["purchasingNotes"] = append_to_purchasing_notes(existing_notes, prev_note)

    # Direct specs-json override (for Claude Code integration)
    if getattr(args, "specs_json", None):
        try:
            specs = json.loads(args.specs_json)
            # Merge specs into data (CLI args take precedence)
            for key, value in specs.items():
                if key not in data:
                    data[key] = value
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid --specs-json: {e}", file=sys.stderr)

    return data


def _print_tool_summary(tool):
    """Print a human-readable tool summary."""
    print(f"\n  Tool: {tool['toolNumber']} ({tool.get('status', '?')})")
    print(f"  Description: {tool['description']}")
    print(f"  Cut Dia: {tool.get('cutDiameter', '')} | "
          f"OAL: {tool.get('overallLength', '')} | "
          f"F/L: {tool.get('lengthOfCut', '')} | "
          f"Shank: {tool.get('shankDiameter', '')}")
    print(f"  Flutes: {tool.get('numberOfFlutes', '')} | "
          f"Helix: {tool.get('helixAngle', '')} | "
          f"Coating: {tool.get('coating', '')} | "
          f"Tip: {tool.get('tipAngle', '')}")
    print(f"  Material: {tool.get('toolMaterial', '')} | "
          f"Cat#: {tool.get('ansiCatalogNumber', '')}")
    brands = tool.get("approvedBrands", {}).get("records", [])
    if brands:
        b = brands[0]
        print(f"  Brand: {b.get('approvedBrand', '?')} | "
              f"EDP: {b.get('vendorToolId', '?')} | "
              f"Cost: ${b.get('cost', '?')}")
    notes = tool.get("purchasingNotes", "")
    if notes:
        print(f"  Notes: {notes}")


def _print_diff(current, changes, args):
    """Print a before/after diff of proposed changes."""
    field_labels = {
        "description": "description",
        "overallLength": "overallLength",
        "lengthOfCut": "lengthOfCut (F/L)",
        "shankDiameter": "shankDiameter",
        "helixAngle": "helixAngle",
        "coating": "coating",
        "ansiCatalogNumber": "ansiCatalogNumber",
        "tipAngle": "tipAngle",
        "purchasingNotes": "purchasingNotes",
    }

    for field, label in field_labels.items():
        if field in changes:
            old_val = current.get(field, "")
            new_val = changes[field]
            if str(old_val) != str(new_val):
                # Truncate long values for display
                old_disp = _truncate(str(old_val), 60)
                new_disp = _truncate(str(new_val), 60)
                print(f"  {label:25s} {old_disp}")
                print(f"  {'-->':>25s} {new_disp}")

    if "approvedBrands" in changes:
        old_brands = current.get("approvedBrands", {}).get("records", [])
        if old_brands:
            ob = old_brands[0]
            nb = changes["approvedBrands"][0]["data"]
            print(f"  {'approvedBrand':25s} {ob.get('approvedBrand', '?')} / {ob.get('vendorToolId', '?')} / ${ob.get('cost', '?')}")
            print(f"  {'-->':>25s} {nb.get('approvedBrand', '?')} / {nb.get('vendorToolId', '?')} / ${nb.get('cost', '?')}")


def _truncate(s, maxlen):
    return s if len(s) <= maxlen else s[:maxlen - 3] + "..."


def main():
    parser = argparse.ArgumentParser(
        description="ProShop Tool Library Updater",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── inspect ──────────────────────────────────────────────────────
    p_inspect = sub.add_parser("inspect", help="Query current tool records")
    p_inspect.add_argument("tool_numbers", nargs="+", help="Tool numbers (e.g., D195 D196)")
    p_inspect.add_argument("--json", action="store_true", help="JSON output")

    # ── find-vpo ─────────────────────────────────────────────────────
    p_vpo = sub.add_parser("find-vpo", help="Search VPOs for tool pricing")
    p_vpo.add_argument("tool_numbers", nargs="+", help="Tool numbers")
    p_vpo.add_argument("--year", default="2026", help="PO year (default: 2026)")
    p_vpo.add_argument("--json", action="store_true", help="JSON output")

    # ── scrape ───────────────────────────────────────────────────────
    p_scrape = sub.add_parser("scrape", help="Fetch specs from manufacturer website")
    p_scrape.add_argument("manufacturer", help="Manufacturer name (e.g., kennametal)")
    p_scrape.add_argument("url", help="Product page URL")
    p_scrape.add_argument("--json", action="store_true", help="JSON output")

    # ── create ───────────────────────────────────────────────────────
    p_create = sub.add_parser("create", help="Create a new tool from manufacturer specs")
    p_create.add_argument("--mfg", help="Manufacturer name (e.g., iscar, kennametal)")
    p_create.add_argument("--edp", help="EDP or product number")
    p_create.add_argument("--catalog", help="Catalog/model number (e.g., 16ERB 1.25 ISO IC908)")
    p_create.add_argument("--qty", type=int, default=None, help="Initial quantity")
    p_create.add_argument("--location", help="Storage location")
    p_create.add_argument("--group", help="Override tool group letter (e.g., D, EM, TN)")
    p_create.add_argument("--specs-json", help="JSON string bypassing AI search")
    p_create.add_argument("--confirm", action="store_true", help="Skip interactive confirmation")
    p_create.add_argument("--json", action="store_true", help="JSON output")

    # ── Common update args (shared by preview and update) ────────────
    def add_update_args(p):
        p.add_argument("tool_number", help="Tool number to update")
        p.add_argument("--new-description", help="New tool description")
        p.add_argument("--oal", type=float, help="Overall length (inches)")
        p.add_argument("--flute-length", type=float, help="Flute/cutting length (inches)")
        p.add_argument("--shank-diameter", type=float, help="Shank diameter (inches)")
        p.add_argument("--helix-angle", type=float, help="Helix angle (degrees)")
        p.add_argument("--coating", help="Coating (TIALN, TICN, C7, C11, OTHER, or manufacturer name)")
        p.add_argument("--catalog-number", help="ANSI catalog number")
        p.add_argument("--tip-angle", help="Tip/point angle")
        p.add_argument("--brand", help="Approved brand name (e.g., KENNAMETAL)")
        p.add_argument("--brand-edp", help="Brand vendor tool ID / EDP / catalog number")
        p.add_argument("--brand-cost", type=float, help="Brand unit cost")
        p.add_argument("--preserve-old-info", action="store_true",
                        help="Save old mfg/EDP in purchasing notes")
        p.add_argument("--specs-json", help="JSON string with additional update fields")
        p.add_argument("--json", action="store_true", help="JSON output")

    # ── preview ──────────────────────────────────────────────────────
    p_preview = sub.add_parser("preview", help="Show proposed changes (dry run)")
    add_update_args(p_preview)

    # ── update ───────────────────────────────────────────────────────
    p_update = sub.add_parser("update", help="Execute tool update in ProShop")
    add_update_args(p_update)
    p_update.add_argument("--confirm", action="store_true",
                          help="Skip interactive confirmation")

    # ── download-image ───────────────────────────────────────────────
    p_img = sub.add_parser("download-image", help="Download product image")
    p_img.add_argument("url", help="Image URL")
    p_img.add_argument("--output", "-o", required=True, help="Output file path")

    args = parser.parse_args()

    commands = {
        "inspect": cmd_inspect,
        "create": cmd_create,
        "find-vpo": cmd_find_vpo,
        "scrape": cmd_scrape,
        "preview": cmd_preview,
        "update": cmd_update,
        "download-image": cmd_download_image,
    }

    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
