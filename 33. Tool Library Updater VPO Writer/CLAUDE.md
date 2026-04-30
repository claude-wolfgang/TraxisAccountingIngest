# Project 33: Tool Library Updater

CLI utility for updating ProShop ERP tool library entries when tools are switched
between manufacturers. Queries existing tool data, fetches manufacturer specs,
finds VPO pricing, and updates tool records while preserving history in notes.

## Usage

```bash
cd "33. Tool Library Updater"

# Inspect current tool records
python tool_update.py inspect D195 D196

# Find VPO pricing
python tool_update.py find-vpo D195 D196 --year 2026

# Preview changes (dry run)
python tool_update.py preview D195 \
    --new-description "#29(.1360)3xD DR 2FL 25/32\" F/L KENNA GODRILL KC7325" \
    --oal 2.441 --flute-length 0.787 --shank-diameter 0.236 \
    --coating TIALN --helix-angle 30 --catalog-number B041A03455CPG \
    --brand KENNAMETAL --brand-edp B041A03455CPG --brand-cost 46.37 \
    --preserve-old-info

# Execute update
python tool_update.py update D195 ... --confirm

# All subcommands support --json for machine-readable output
python tool_update.py inspect D195 --json
```

## Key Files

- `tool_update.py` — CLI entry point (argparse subcommands)
- `proshop_tools.py` — ProShop GraphQL client (OAuth, tool queries, VPO queries, mutations)
- `description_format.py` — Shop-convention description builder, PREV note formatter
- `mfg_scrapers.py` — Manufacturer website scrapers (Kennametal supported, extensible)

## Auth / Scope

Uses BA16-EFAF-B154 client from `.traxis.env` with scope:
`tools:rwdp+purchaseorders:r` (VPO queries without supplier names).
For supplier names, falls back to AccountingConnector client with `contacts:r`.

## Interfaces

Produces: Updated tool records in ProShop (description, dimensions, coating, brand, cost, notes), downloaded product images for manual upload
Consumes: ProShop GraphQL API (tools, purchaseOrders), .traxis.env credentials, manufacturer product pages (Kennametal)
Contracts: Uses same .traxis.env format as all other Traxis projects. Tool descriptions follow shop convention format (e.g., "#29(.1360)3xD DR 2FL 25/32" F/L KENNA GODRILL KC7325"). Old tool info preserved in purchasingNotes with "PREV:" prefix and "|" separator.
