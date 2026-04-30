# Project 33: Tool Library Updater

CLI utility for managing ProShop ERP tool library entries. Can create new tool
records from a manufacturer EDP/catalog number (AI-powered spec lookup), update
existing tools when switching manufacturers, query VPO pricing, and preserve
history in purchasing notes.

## Usage

```bash
cd "33. Tool Library Updater"

# Create a new tool from manufacturer catalog number (AI web search)
python tool_update.py create --mfg iscar --catalog "16ERB 1.25 ISO IC908" --qty 4
python tool_update.py create --mfg kennametal --catalog B041A03455CPG --qty 2 --group D

# Create with pre-gathered specs (skips AI search, useful for Claude Code integration)
python tool_update.py create --mfg iscar --edp 1955660 --specs-json '{"tool_type":"insert",...}'

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

- `tool_update.py` — CLI entry point (argparse subcommands: inspect, create, find-vpo, scrape, preview, update, download-image)
- `proshop_tools.py` — ProShop GraphQL client (OAuth, tool queries/mutations, VPO queries)
- `ai_search.py` — AI-powered tool spec lookup using Anthropic API + web_search server-side tool
- `description_format.py` — Shop-convention description builder, PREV note formatter, enum mappings
- `mfg_scrapers.py` — Manufacturer website scrapers (Kennametal supported, extensible)

## Auth / Scope

Uses BA16-EFAF-B154 client from `.traxis.env` with scope:
`tools:rwdp+purchaseorders:r` (VPO queries without supplier names).
For supplier names, falls back to AccountingConnector client with `contacts:r`.

## AI Search

The `create` subcommand uses Claude Haiku with the `web_search_20250305` server-side tool
to find manufacturer specs from distributor sites (MSC, Grainger, Penn Tool, etc.).
Cost: ~$0.02/lookup. Requires `ANTHROPIC_API_KEY` in `.traxis.env`.

The AI classifies the tool type (drill/endmill/insert/tap/etc.) and extracts structured
specs. Tool type maps to ProShop `toolGroupLetter` via `TOOL_GROUP_MAP`. Override with `--group`.

## Interfaces

Produces: New and updated tool records in ProShop (description, dimensions, coating, brand, cost, notes), downloaded product images for manual upload
Consumes: ProShop GraphQL API (tools, purchaseOrders), Anthropic API (Claude Haiku + web_search), .traxis.env credentials, manufacturer product pages (Kennametal)
Contracts: Uses same .traxis.env format as all other Traxis projects. Tool descriptions follow shop convention format (e.g., "#29(.1360)3xD DR 2FL 25/32" F/L KENNA GODRILL KC7325"). Old tool info preserved in purchasingNotes with "PREV:" prefix and "|" separator. ANTHROPIC_API_KEY required in .traxis.env for create subcommand.
