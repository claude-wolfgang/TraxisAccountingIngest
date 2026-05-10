#!/usr/bin/env python3
"""
Traxis Data Quality Agent — Main Entry Point

Usage:
    python run_audit.py              # Full audit with console + markdown output
    python run_audit.py --quick      # Quick check (system health + field population only)
    python run_audit.py --trend      # Show trend report from historical data
    python run_audit.py --json       # Output findings as JSON
    python run_audit.py --help       # Show this help

Run this on a schedule (e.g., hourly via Windows Task Scheduler) to
continuously monitor and trend data quality across Traxis systems.
"""

import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import config
from proshop_client import ProShopClient
from focas_reader import FocasReader
from audit_db import AuditDB
from audit_engine import AuditEngine
from report import (
    generate_console_report,
    generate_markdown_report,
    save_markdown_report,
    generate_trend_report,
)


def build_proshop_client():
    """Initialize ProShop API client."""
    return ProShopClient(
        graphql_url=config.PROSHOP_GRAPHQL_URL,
        token_url=config.PROSHOP_TOKEN_URL,
        client_id=config.PROSHOP_CLIENT_ID,
        client_secret=config.PROSHOP_CLIENT_SECRET,
        scope=config.PROSHOP_SCOPE,
    )


def build_focas_reader():
    """Initialize FOCAS database reader (or None if unavailable)."""
    db_path = config.get_focas_db_path()
    if db_path:
        try:
            return FocasReader(db_path)
        except FileNotFoundError:
            print(f"  [WARN] FOCAS database not found at {db_path}")
            return None
    print("  [WARN] No FOCAS database path available")
    return None


def run_full_audit(audit_db):
    """Execute a full data quality audit."""
    print("\n  Initializing Traxis Data Quality Agent...")
    start = time.time()

    # Build clients
    print("  Connecting to ProShop API...", end=" ", flush=True)
    ps = build_proshop_client()
    print("OK")

    print("  Opening FOCAS database...", end=" ", flush=True)
    focas = build_focas_reader()
    print("OK" if focas else "SKIPPED")

    print(f"  NC Programs root: {config.NC_PROGRAMS_ROOT or 'NOT CONFIGURED'}")
    print(f"  Part Files root: {config.PART_FILES_ROOT or 'NOT CONFIGURED'}")
    print()

    # Create audit engine
    engine = AuditEngine(
        proshop_client=ps,
        focas_reader=focas,
        nc_programs_root=config.NC_PROGRAMS_ROOT,
        part_files_root=config.PART_FILES_ROOT,
    )

    # Run all checks
    print("  Running audit checks...")
    print("  - System connectivity")
    print("  - ProShop field population")
    print("  - ProShop consistency")
    print("  - Schedule & readiness")
    print("  - Cross-reference: ProShop <-> FOCAS")
    print("  - Cross-reference: ProShop <-> Filesystem")
    print("  - FOCAS health & collection")
    print("  - Financial / overrun analysis")
    print()

    findings, metrics, field_pops = engine.run_all()
    duration = time.time() - start

    # Store results
    run_id = audit_db.start_run()

    for f in findings:
        audit_db.add_finding(
            run_id, f.category, f.check_name, f.severity, f.message,
            subject=f.subject, details=f.details, auto_fixable=f.auto_fixable,
        )

    for name, (value, ctx) in metrics.items():
        audit_db.add_metric(run_id, name, value, context=ctx)

    for fname, level, total, populated in field_pops:
        audit_db.add_field_population(run_id, fname, level, total, populated)

    counts = Counter(f.severity for f in findings)
    audit_db.finish_run(
        run_id,
        duration_s=duration,
        total_checks=len(findings),
        passed=counts.get("pass", 0),
        warnings=counts.get("warning", 0),
        failures=counts.get("failure", 0),
        errors=counts.get("error", 0),
        summary=f"Score: {round(100 * (counts.get('pass', 0) + counts.get('info', 0) * 0.8) / max(len(findings), 1), 1)}%",
    )

    return findings, metrics, field_pops, duration, run_id


def main():
    parser = argparse.ArgumentParser(
        description="Traxis Data Quality Agent",
        epilog="Run without args for a full audit with console + markdown output.",
    )
    parser.add_argument("--quick", action="store_true",
                        help="Quick check (system health only)")
    parser.add_argument("--trend", action="store_true",
                        help="Show trend report from historical data")
    parser.add_argument("--json", action="store_true",
                        help="Output findings as JSON")
    parser.add_argument("--days", type=int, default=30,
                        help="Days of history for trend report (default: 30)")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save markdown report to disk")
    parser.add_argument("--no-alert", action="store_true",
                        help="Suppress Telegram alerts (for testing)")
    args = parser.parse_args()

    # Initialize audit database
    audit_db = AuditDB(config.AUDIT_DB_PATH)

    # Trend report mode
    if args.trend:
        print(generate_trend_report(audit_db, days=args.days))
        return

    # Telegram status
    if not args.no_alert and config.TELEGRAM_ENABLED:
        print("  [INFO] Telegram alerts: enabled")
    elif not args.no_alert:
        print("  [INFO] Telegram alerts: not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")

    # Run the audit
    findings, metrics, field_pops, duration, run_id = run_full_audit(audit_db)

    # Send Telegram alert (before console output so it doesn't delay exit)
    if not args.no_alert and config.TELEGRAM_ENABLED:
        from alerter import send_audit_alert
        send_audit_alert(audit_db, run_id, findings)

    # JSON output mode
    if args.json:
        output = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "duration_s": round(duration, 1),
            "total_checks": len(findings),
            "counts": dict(Counter(f.severity for f in findings)),
            "metrics": {k: v[0] for k, v in metrics.items()},
            "field_populations": [
                {"field": f, "level": l, "total": t, "populated": p,
                 "pct": round(100 * p / max(t, 1), 1)}
                for f, l, t, p in field_pops
            ],
            "findings": [
                {
                    "category": f.category,
                    "check": f.check_name,
                    "severity": f.severity,
                    "message": f.message,
                    "subject": f.subject,
                    "auto_fixable": f.auto_fixable,
                }
                for f in findings
                if f.severity in ("error", "failure", "warning")
            ],
        }
        print(json.dumps(output, indent=2))
        return

    # Console report
    console = generate_console_report(findings, metrics, field_pops, duration)
    print(console)

    # Save markdown report
    if not args.no_save:
        md = generate_markdown_report(findings, metrics, field_pops, duration, run_id)
        filepath = save_markdown_report(md, config.REPORT_DIR)
        print(f"  Report saved: {filepath}")
        print(f"  Latest report: {config.REPORT_DIR / 'latest.md'}")
        print()

    # Quick summary for scheduling
    counts = Counter(f.severity for f in findings)
    if counts.get("failure", 0) > 0 or counts.get("error", 0) > 0:
        sys.exit(1)  # Non-zero exit = issues found (useful for schedulers)


if __name__ == "__main__":
    main()
