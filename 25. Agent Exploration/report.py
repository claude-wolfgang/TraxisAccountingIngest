"""
Report generator for Traxis Data Quality Agent.
Produces both console output and markdown reports.
"""

import os
from datetime import datetime
from pathlib import Path
from collections import Counter


def generate_console_report(findings, metrics, field_populations, duration_s=0):
    """Print a formatted console report."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Header
    lines.append("")
    lines.append("=" * 72)
    lines.append(f"  TRAXIS DATA QUALITY AUDIT -- {now}")
    lines.append(f"  Duration: {duration_s:.1f}s | Checks: {len(findings)}")
    lines.append("=" * 72)

    # Summary counts
    counts = Counter(f.severity for f in findings)
    passed = counts.get("pass", 0)
    info = counts.get("info", 0)
    warnings = counts.get("warning", 0)
    failures = counts.get("failure", 0)
    errors = counts.get("error", 0)

    lines.append("")
    lines.append(f"  PASS: {passed}  |  INFO: {info}  |  WARN: {warnings}  |  FAIL: {failures}  |  ERROR: {errors}")
    lines.append("")

    # Score (simple weighted score)
    total = len(findings)
    if total > 0:
        score = round(100 * (passed + info * 0.8) / total, 1)
        bar_len = 40
        filled = int(bar_len * score / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        label = "GOOD" if score >= 70 else "NEEDS WORK" if score >= 40 else "CRITICAL"
        lines.append(f"  Data Quality Score: {score}% [{bar}] {label}")
    lines.append("")

    # Field Population Table
    if field_populations:
        lines.append("-" * 72)
        lines.append("  FIELD POPULATION RATES")
        lines.append("-" * 72)
        lines.append(f"  {'Field':<35} {'Level':<12} {'Pop/Total':<12} {'Rate':>6}")
        lines.append(f"  {'-' * 35} {'-' * 11} {'-' * 11} {'-' * 6}")
        for fname, level, total, populated in sorted(field_populations, key=lambda x: x[3] / max(x[2], 1)):
            pct = round(100 * populated / total, 1) if total > 0 else 0
            indicator = "!!" if pct < 20 else "! " if pct < 50 else "  "
            lines.append(f"{indicator}{fname:<35} {level:<12} {populated:>4}/{total:<6} {pct:>5.1f}%")
        lines.append("")

    # Key Metrics
    if metrics:
        lines.append("-" * 72)
        lines.append("  KEY METRICS")
        lines.append("-" * 72)
        for name, (value, context) in sorted(metrics.items()):
            ctx = f" ({context})" if context else ""
            if isinstance(value, float):
                lines.append(f"  {name:<40} {value:>10.1f}{ctx}")
            else:
                lines.append(f"  {name:<40} {value:>10}{ctx}")
        lines.append("")

    # Findings by category (failures and warnings only for console)
    categories = {}
    for f in findings:
        if f.severity in ("failure", "error", "warning"):
            cat = f.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f)

    if categories:
        lines.append("-" * 72)
        lines.append("  ISSUES REQUIRING ATTENTION")
        lines.append("-" * 72)

        severity_order = {"error": 0, "failure": 1, "warning": 2}
        for cat in sorted(categories.keys()):
            cat_findings = sorted(categories[cat], key=lambda f: severity_order.get(f.severity, 9))
            lines.append(f"\n  [{cat.upper()}]")
            for f in cat_findings:
                icon = {"error": "XX", "failure": "!!", "warning": "! "}[f.severity]
                subj = f" [{f.subject}]" if f.subject else ""
                fix = " (auto-fixable)" if f.auto_fixable else ""
                lines.append(f"  {icon} {f.message}{subj}{fix}")

    # Auto-fixable summary
    auto_fixable = [f for f in findings if f.auto_fixable]
    if auto_fixable:
        lines.append("")
        lines.append("-" * 72)
        lines.append(f"  AUTO-FIXABLE ISSUES: {len(auto_fixable)}")
        lines.append("-" * 72)
        for f in auto_fixable:
            subj = f" [{f.subject}]" if f.subject else ""
            lines.append(f"  -> {f.message}{subj}")

    lines.append("")
    lines.append("=" * 72)
    lines.append(f"  End of audit -- {now}")
    lines.append("=" * 72)
    lines.append("")

    return "\n".join(lines)


def generate_markdown_report(findings, metrics, field_populations, duration_s=0, run_id=None):
    """Generate a markdown report file."""
    now = datetime.now()
    counts = Counter(f.severity for f in findings)
    passed = counts.get("pass", 0)
    info_count = counts.get("info", 0)
    warnings = counts.get("warning", 0)
    failures = counts.get("failure", 0)
    errors = counts.get("error", 0)
    total = len(findings)
    score = round(100 * (passed + info_count * 0.8) / total, 1) if total > 0 else 0

    lines = []
    lines.append(f"# Traxis Data Quality Audit Report")
    lines.append(f"**Date:** {now.strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"**Run ID:** {run_id or 'N/A'}  ")
    lines.append(f"**Duration:** {duration_s:.1f}s  ")
    lines.append(f"**Total Checks:** {total}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Status | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Pass | {passed} |")
    lines.append(f"| Info | {info_count} |")
    lines.append(f"| Warning | {warnings} |")
    lines.append(f"| Failure | {failures} |")
    lines.append(f"| Error | {errors} |")
    lines.append(f"| **Score** | **{score}%** |")
    lines.append("")

    # Field Population
    if field_populations:
        lines.append("## Field Population Rates")
        lines.append("")
        lines.append("| Field | Level | Populated | Total | Rate |")
        lines.append("|-------|-------|-----------|-------|------|")
        for fname, level, total_f, populated in sorted(
            field_populations, key=lambda x: x[3] / max(x[2], 1)
        ):
            pct = round(100 * populated / total_f, 1) if total_f > 0 else 0
            flag = " [!!]" if pct < 20 else " [!]" if pct < 50 else ""
            lines.append(f"| {fname} | {level} | {populated} | {total_f} | {pct}%{flag} |")
        lines.append("")

    # Key Metrics
    if metrics:
        lines.append("## Key Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for name, (value, context) in sorted(metrics.items()):
            ctx = f" ({context})" if context else ""
            if isinstance(value, float):
                lines.append(f"| {name} | {value:.1f}{ctx} |")
            else:
                lines.append(f"| {name} | {value}{ctx} |")
        lines.append("")

    # Issues
    issue_findings = [f for f in findings if f.severity in ("error", "failure", "warning")]
    if issue_findings:
        lines.append("## Issues Requiring Attention")
        lines.append("")

        # Group by category
        categories = {}
        for f in issue_findings:
            cat = f.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f)

        for cat in sorted(categories.keys()):
            lines.append(f"### {cat.replace('_', ' ').title()}")
            lines.append("")
            for f in sorted(categories[cat], key=lambda x: {"error": 0, "failure": 1, "warning": 2}.get(x.severity, 9)):
                icon = {"error": "[ERROR]", "failure": "[FAIL]", "warning": "[WARN]"}[f.severity]
                subj = f" **[{f.subject}]**" if f.subject else ""
                fix = " *(auto-fixable)*" if f.auto_fixable else ""
                lines.append(f"- {icon} {f.message}{subj}{fix}")
            lines.append("")

    # Auto-fixable
    auto_fixable = [f for f in findings if f.auto_fixable]
    if auto_fixable:
        lines.append("## Auto-Fixable Issues")
        lines.append("")
        lines.append(f"**{len(auto_fixable)} issues** could be resolved automatically:")
        lines.append("")
        for f in auto_fixable:
            subj = f" [{f.subject}]" if f.subject else ""
            lines.append(f"- {f.message}{subj}")
        lines.append("")

    # Passes (collapsed)
    pass_findings = [f for f in findings if f.severity == "pass"]
    if pass_findings:
        lines.append("<details>")
        lines.append(f"<summary>Passing Checks ({len(pass_findings)})</summary>")
        lines.append("")
        for f in pass_findings:
            subj = f" [{f.subject}]" if f.subject else ""
            lines.append(f"- {f.message}{subj}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by Traxis Data Quality Agent*")
    return "\n".join(lines)


def save_markdown_report(content, report_dir):
    """Save markdown report to the reports directory."""
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"audit_{timestamp}.md"
    filepath = report_dir / filename
    filepath.write_text(content, encoding="utf-8")

    # Also save as latest.md for quick access
    latest = report_dir / "latest.md"
    latest.write_text(content, encoding="utf-8")

    return filepath


def generate_trend_report(audit_db, days=30):
    """Generate a trend analysis from historical audit data."""
    runs = audit_db.get_run_history(days=days)
    if len(runs) < 2:
        return "Not enough historical data for trend analysis (need at least 2 runs)."

    lines = []
    lines.append(f"# Data Quality Trend -- Last {days} Days")
    lines.append(f"**Runs analyzed:** {len(runs)}")
    lines.append("")

    # Overall score trend
    lines.append("## Score Trend")
    lines.append("")
    lines.append("| Date | Checks | Pass | Warn | Fail | Score |")
    lines.append("|------|--------|------|------|------|-------|")
    for run in runs:
        total = run.get("total_checks", 0)
        passed = run.get("passed", 0)
        score = round(100 * passed / total, 1) if total > 0 else 0
        ts = run.get("timestamp", "")[:10]
        lines.append(
            f"| {ts} | {total} | {passed} | {run.get('warnings', 0)} | "
            f"{run.get('failures', 0)} | {score}% |"
        )
    lines.append("")

    # Field population trends
    key_fields = [
        "runTimeSpent", "setupTimeSpent", "certifiedToRun",
        "toolAssignments", "scheduledStartDate", "programmingPercentComplete",
    ]
    lines.append("## Field Population Trends")
    lines.append("")
    for field_name in key_fields:
        trend = audit_db.get_field_population_trend(field_name, days=days)
        if len(trend) >= 2:
            first = trend[0]["pct"]
            last = trend[-1]["pct"]
            delta = last - first
            arrow = "UP" if delta > 0 else "DN" if delta < 0 else "->"
            lines.append(f"- **{field_name}**: {first}% -> {last}% ({arrow} {delta:+.1f}pp)")
    lines.append("")

    # Metric trends
    lines.append("## Key Metric Trends")
    lines.append("")
    for metric_name in ["overrun_rate_pct", "overdue_work_orders", "alarms_7day"]:
        trend = audit_db.get_metric_trend(metric_name, days=days)
        if len(trend) >= 2:
            first = trend[0]["metric_value"]
            last = trend[-1]["metric_value"]
            delta = last - first
            arrow = "UP" if delta > 0 else "DN" if delta < 0 else "->"
            better = "DN" if metric_name in ("overrun_rate_pct", "overdue_work_orders", "alarms_7day") else "UP"
            good = (arrow == "DN") if better == "DN" else (arrow == "UP")
            indicator = " (improving)" if good else " (worsening)" if not good and delta != 0 else ""
            lines.append(f"- **{metric_name}**: {first:.1f} -> {last:.1f} ({arrow} {delta:+.1f}){indicator}")
    lines.append("")

    return "\n".join(lines)
