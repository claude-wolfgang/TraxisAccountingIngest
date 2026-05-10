"""
Data Quality Audit Engine for Traxis MFG.

Runs checks across three data sources:
  1. ProShop ERP (GraphQL API) — field population, consistency, staleness
  2. FOCAS monitoring (SQLite) — machine health, data collection, cross-reference
  3. Filesystem (Dropbox) — NC program existence, version tracking

Each check method returns a list of Finding dicts.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Finding:
    category: str
    check_name: str
    severity: str  # pass, info, warning, failure, error
    message: str
    subject: Optional[str] = None
    details: Optional[dict] = None
    auto_fixable: bool = False


class AuditEngine:
    """Runs all data quality checks and collects findings."""

    def __init__(self, proshop_client, focas_reader, nc_programs_root=None, part_files_root=None):
        self.ps = proshop_client
        self.focas = focas_reader
        self.nc_root = Path(nc_programs_root) if nc_programs_root else None
        self.pf_root = Path(part_files_root) if part_files_root else None
        self.findings = []
        self.metrics = {}  # metric_name -> value
        self.field_populations = []  # (field_name, level, total, populated)

    def _add(self, category, check_name, severity, message, **kwargs):
        self.findings.append(Finding(
            category=category,
            check_name=check_name,
            severity=severity,
            message=message,
            **kwargs,
        ))

    def _record_metric(self, name, value, context=None):
        self.metrics[name] = (value, context)

    def _record_field_pop(self, field_name, level, total, populated):
        self.field_populations.append((field_name, level, total, populated))

    # ── Master Run ───────────────────────────────────────────────────────

    def run_all(self):
        """Execute all audit checks. Returns (findings, metrics, field_populations)."""
        self.findings = []
        self.metrics = {}
        self.field_populations = []

        # 1. System connectivity
        self.check_proshop_health()
        self.check_focas_health()
        self.check_filesystem_access()

        # 2. ProShop data quality
        wo_data = None
        try:
            wo_data = self.ps.get_all_active_work_orders()
        except Exception as e:
            self._add("proshop", "fetch_work_orders", "error",
                      f"Failed to fetch work orders: {e}")

        if wo_data and wo_data.get("records"):
            wos = wo_data["records"]
            ops = []
            for wo in wos:
                for op in (wo.get("ops") or {}).get("records", []):
                    op["_wo_number"] = wo.get("workOrderNumber")
                    op["_wo_due_date"] = wo.get("dueDate")
                    op["_wo_status"] = wo.get("status")
                    op["_part_number"] = (wo.get("part") or {}).get("partNumber", "")
                    op["_customer_part_number"] = (wo.get("part") or {}).get("customerPartNumber", "")
                    ops.append(op)

            self.check_wo_field_population(wos)
            self.check_op_field_population(ops)
            self.check_wo_consistency(wos)
            self.check_overdue_work_orders(wos)
            self.check_scheduling_gaps(wos, ops)
            self.check_tool_assignments(ops)
            self.check_material_readiness(wos)

            # 3. Cross-reference: ProShop <-> FOCAS
            if self.focas:
                self.check_proshop_focas_crossref(ops)

            # 4. Cross-reference: ProShop <-> Filesystem
            if self.nc_root:
                self.check_nc_program_existence(ops)

        # 5. FOCAS-specific checks
        if self.focas:
            self.check_focas_collection_gaps()
            self.check_focas_schema()
            self.check_alarm_frequency()
            self.check_utilization_anomalies()

        # 6. Overrun analysis (completed jobs)
        try:
            self.check_overrun_patterns()
        except Exception as e:
            self._add("financial", "overrun_analysis", "error",
                      f"Failed to analyze overruns: {e}")

        return self.findings, self.metrics, self.field_populations

    # ══════════════════════════════════════════════════════════════════════
    # SYSTEM CONNECTIVITY CHECKS
    # ══════════════════════════════════════════════════════════════════════

    def check_proshop_health(self):
        """Verify ProShop API is reachable and authenticated."""
        try:
            health = self.ps.check_health()
            if health.get("healthy"):
                self._add("system", "proshop_api", "pass",
                          f"ProShop API healthy. {health.get('active_work_orders', '?')} active WOs. "
                          f"Token age: {health.get('token_age_seconds', '?')}s")
                self._record_metric("proshop_active_wos", health.get("active_work_orders", 0))
            else:
                self._add("system", "proshop_api", "failure",
                          f"ProShop API unhealthy: {health.get('error', 'unknown')}")
        except Exception as e:
            self._add("system", "proshop_api", "error", f"ProShop health check failed: {e}")

    def check_focas_health(self):
        """Verify FOCAS database is accessible and has recent data."""
        if not self.focas:
            self._add("system", "focas_db", "warning", "FOCAS reader not configured (no database path)")
            return

        try:
            health = self.focas.check_health()
            if not health.get("healthy"):
                self._add("system", "focas_db", "failure",
                          f"FOCAS database unhealthy: {health.get('error', 'unknown')}")
                return

            machines = health.get("machines", {})
            for mid, info in machines.items():
                if info.get("stale"):
                    self._add("system", "focas_machine_stale", "warning",
                              f"Machine {mid} last reported {info['age_minutes']:.0f} min ago",
                              subject=mid)
                else:
                    self._add("system", "focas_machine_live", "pass",
                              f"Machine {mid} reporting ({info['age_minutes']:.0f} min ago, "
                              f"{info['total_samples']} total samples)",
                              subject=mid)
            self._record_metric("focas_machines_live",
                                sum(1 for m in machines.values() if not m.get("stale")))
            self._record_metric("focas_machines_stale",
                                sum(1 for m in machines.values() if m.get("stale")))
        except Exception as e:
            self._add("system", "focas_db", "error", f"FOCAS health check failed: {e}")

    def check_filesystem_access(self):
        """Verify NC Programs and Part Files directories exist."""
        if self.nc_root and self.nc_root.exists():
            count = sum(1 for _ in self.nc_root.iterdir() if _.is_dir())
            self._add("system", "nc_programs_dir", "pass",
                      f"NC Programs directory accessible ({count} part folders)")
        elif self.nc_root:
            self._add("system", "nc_programs_dir", "failure",
                      f"NC Programs directory not found: {self.nc_root}")
        else:
            self._add("system", "nc_programs_dir", "warning",
                      "NC Programs root not configured")

        if self.pf_root and self.pf_root.exists():
            self._add("system", "part_files_dir", "pass",
                      f"Part Files directory accessible: {self.pf_root}")
        elif self.pf_root:
            self._add("system", "part_files_dir", "failure",
                      f"Part Files directory not found: {self.pf_root}")

    # ══════════════════════════════════════════════════════════════════════
    # PROSHOP FIELD POPULATION CHECKS
    # ══════════════════════════════════════════════════════════════════════

    def check_wo_field_population(self, wos):
        """Check population rates for key work order fields."""
        n = len(wos)
        if n == 0:
            return

        fields = {
            "scheduledEndDate": lambda wo: wo.get("scheduledEndDate") not in (None, ""),
            "dueDate": lambda wo: wo.get("dueDate") not in (None, ""),
            "programmingPercentComplete": lambda wo: wo.get("programmingPercentComplete") not in (None, 0, "0"),
            "planningPercentComplete": lambda wo: wo.get("planningPercentComplete") not in (None, 0, "0"),
            "planningLevel": lambda wo: wo.get("planningLevel") not in (None, 0, "0"),
            "deliverypriority": lambda wo: wo.get("deliverypriority") not in (None, ""),
            "hoursCurrentTarget": lambda wo: _positive(wo.get("hoursCurrentTarget")),
            "hoursTotalSpent": lambda wo: _positive(wo.get("hoursTotalSpent")),
        }

        for field_name, checker in fields.items():
            populated = sum(1 for wo in wos if checker(wo))
            pct = round(100 * populated / n, 1)
            self._record_field_pop(field_name, "work_order", n, populated)

            severity = "pass" if pct >= 80 else "warning" if pct >= 40 else "failure"
            self._add("proshop_population", f"wo_{field_name}", severity,
                      f"{field_name}: {populated}/{n} ({pct}%) populated across active WOs")

        self._record_metric("active_work_orders", n)

    def check_op_field_population(self, ops):
        """Check population rates for key operation fields."""
        n = len(ops)
        if n == 0:
            return

        # Only check ops that aren't complete
        active_ops = [op for op in ops if not op.get("isOpComplete")]
        na = len(active_ops)

        fields = {
            "runTimeSpent": (lambda op: _positive(op.get("runTimeSpent")), ops),
            "setupTimeSpent": (lambda op: _positive(op.get("setupTimeSpent")), ops),
            "percentComplete": (lambda op: op.get("percentComplete") not in (None, 0, "0"), active_ops),
            "operationDescription": (lambda op: op.get("operationDescription") not in (None, ""), ops),
            "certifiedToRun": (lambda op: op.get("certifiedToRun") is True, active_ops),
            "firstArticleComplete": (lambda op: op.get("firstArticleComplete") is True, ops),
            "preProcessingCheckComplete": (lambda op: op.get("preProcessingCheckComplete") is True, active_ops),
            "breakdownComplete": (lambda op: op.get("breakdownComplete") is True, active_ops),
            "scheduledStartDate": (lambda op: op.get("scheduledStartDate") not in (None, ""), active_ops),
            # outsideProcessing removed — ProShop schema doesn't expose subfields via current scope
        }

        for field_name, (checker, target_ops) in fields.items():
            total = len(target_ops)
            if total == 0:
                continue
            populated = sum(1 for op in target_ops if checker(op))
            pct = round(100 * populated / total, 1)
            self._record_field_pop(field_name, "operation", total, populated)

            severity = "pass" if pct >= 80 else "warning" if pct >= 40 else "failure"
            self._add("proshop_population", f"op_{field_name}", severity,
                      f"{field_name}: {populated}/{total} ({pct}%) populated across operations")

        # Tool assignments and BOM require nested partOperation queries which
        # time out when fetched for all WOs at once. These are checked via
        # separate targeted queries in check_tool_assignments() for soon-due ops.

        self._record_metric("total_operations", n)
        self._record_metric("active_operations", na)

    # ══════════════════════════════════════════════════════════════════════
    # PROSHOP CONSISTENCY CHECKS
    # ══════════════════════════════════════════════════════════════════════

    def check_wo_consistency(self, wos):
        """Check for logical inconsistencies in work order data."""
        for wo in wos:
            wo_num = wo.get("workOrderNumber", "?")

            # Qty complete > qty ordered
            qty_ord = wo.get("quantityOrdered") or 0
            qty_comp = wo.get("qtyComplete") or 0
            if qty_comp > qty_ord and qty_ord > 0:
                self._add("consistency", "qty_exceeds_ordered", "warning",
                          f"Qty complete ({qty_comp}) exceeds qty ordered ({qty_ord})",
                          subject=wo_num)

            # All ops complete but WO still active
            ops = (wo.get("ops") or {}).get("records", [])
            if ops:
                all_complete = all(op.get("isOpComplete") for op in ops)
                if all_complete and wo.get("status") == "active":
                    self._add("consistency", "all_ops_complete_wo_active", "warning",
                              f"All {len(ops)} operations complete but WO still active",
                              subject=wo_num, auto_fixable=True)

            # Hours spent but no target set
            target = _safe_float(wo.get("hoursCurrentTarget"))
            spent = _safe_float(wo.get("hoursTotalSpent"))
            if spent and spent > 0 and (not target or target == 0):
                self._add("consistency", "hours_spent_no_target", "warning",
                          f"Hours spent ({spent:.1f}) but no target hours set",
                          subject=wo_num)

            # Target but no spend on old WOs
            if target and target > 0 and (not spent or spent == 0):
                due = wo.get("dueDate")
                if due:
                    try:
                        due_dt = datetime.fromisoformat(due.replace("Z", "+00:00")).replace(tzinfo=None)
                        if due_dt < datetime.now() - timedelta(days=7):
                            self._add("consistency", "target_no_spend_overdue", "warning",
                                      f"Has target hours ({target:.1f}) but 0 hours spent, past due {due}",
                                      subject=wo_num)
                    except (ValueError, TypeError):
                        pass

    def check_overdue_work_orders(self, wos):
        """Flag work orders past their due date.

        Grace window: <3 days late is recorded in the metric for trend, but no
        finding is emitted. Keeps the digest from screaming at end-of-day slips
        that resolve themselves overnight.
        """
        now = datetime.now()
        overdue_count = 0
        overdue_3plus = 0
        for wo in wos:
            due = wo.get("dueDate")
            if not due:
                continue
            try:
                due_dt = datetime.fromisoformat(due.replace("Z", "+00:00")).replace(tzinfo=None)
                if due_dt < now:
                    days_late = (now - due_dt).days
                    overdue_count += 1
                    if days_late < 3:
                        continue  # Grace window — counted in metric, no finding
                    overdue_3plus += 1
                    severity = "failure" if days_late > 14 else "warning"
                    self._add("schedule", "overdue_wo", severity,
                              f"Overdue by {days_late} days (due {due_dt.strftime('%Y-%m-%d')})",
                              subject=wo.get("workOrderNumber"))
            except (ValueError, TypeError):
                pass

        self._record_metric("overdue_work_orders", overdue_count)
        self._record_metric("overdue_wo_3plus", overdue_3plus)

    def check_scheduling_gaps(self, wos, ops):
        """Check for operations without scheduled dates on soon-due WOs."""
        now = datetime.now()
        soon = now + timedelta(days=14)

        for wo in wos:
            due = wo.get("dueDate")
            if not due:
                continue
            try:
                due_dt = datetime.fromisoformat(due.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue

            if due_dt > soon:
                continue  # Not due soon, skip

            wo_num = wo.get("workOrderNumber")
            wo_ops = [op for op in ops if op.get("_wo_number") == wo_num and not op.get("isOpComplete")]
            unscheduled = [op for op in wo_ops if not op.get("scheduledStartDate")]

            if unscheduled:
                self._add("schedule", "unscheduled_ops_due_soon", "warning",
                          f"Due within 14 days but {len(unscheduled)} of {len(wo_ops)} "
                          f"active ops have no scheduledStartDate",
                          subject=wo_num,
                          details={"unscheduled_ops": [op.get("operationNumber") for op in unscheduled]})

    def check_tool_assignments(self, ops):
        """Check that operations starting soon have been reviewed.
        Note: Tool assignment data requires per-WO queries (too heavy for bulk).
        This check flags uncertified ops starting within 3 days (digest-actionable
        window). Metric also records 7-day count for trending."""
        now = datetime.now()
        soon_3 = now + timedelta(days=3)
        soon_7 = now + timedelta(days=7)
        uncertified_3day = 0
        uncertified_7day = 0

        for op in ops:
            if op.get("isOpComplete"):
                continue
            sched = op.get("scheduledStartDate")
            if not sched:
                continue
            try:
                sched_dt = datetime.fromisoformat(sched.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue

            if sched_dt > soon_7:
                continue
            if op.get("certifiedToRun"):
                continue

            uncertified_7day += 1
            if sched_dt <= soon_3:
                uncertified_3day += 1

        self._record_metric("uncertified_starting_3day", uncertified_3day)
        self._record_metric("uncertified_starting_7day", uncertified_7day)
        if uncertified_3day > 0:
            self._add("readiness", "uncertified_starting_soon", "warning",
                      f"{uncertified_3day} operations start within 3 days but are not certified to run")

    def check_material_readiness(self, wos):
        """Check material status for active WOs (limited by API scope)."""
        try:
            vpo_data = self.ps.get_outstanding_material_pos()
            if isinstance(vpo_data, dict) and vpo_data.get("error") == "scope_missing":
                self._add("readiness", "material_pos", "info",
                          "Cannot check material POs — vendorPOs scope not available. "
                          "Need contacts:r+purchaseOrders:r scope.")
                return

            total = vpo_data.get("totalRecords", 0)
            self._add("readiness", "material_pos", "info",
                      f"Found {total} outstanding material POs")
            self._record_metric("outstanding_material_pos", total)
        except Exception as e:
            self._add("readiness", "material_pos", "info",
                      f"Material PO check unavailable: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # CROSS-REFERENCE: PROSHOP <-> FOCAS
    # ══════════════════════════════════════════════════════════════════════

    def check_proshop_focas_crossref(self, ops):
        """Cross-reference ProShop operations with FOCAS machine data."""
        from config import PROSHOP_TO_FOCAS

        # Get current FOCAS status
        try:
            statuses = self.focas.get_latest_status()
        except Exception as e:
            self._add("crossref", "focas_status", "error",
                      f"Cannot read FOCAS status: {e}")
            return

        focas_by_id = {s["machine_id"]: s for s in statuses}

        # Get today's utilization
        try:
            utilization = self.focas.get_utilization_today()
        except Exception:
            utilization = {}

        # Check each FOCAS-connected machine
        for ps_name, focas_id in PROSHOP_TO_FOCAS.items():
            if not focas_id:
                self._add("crossref", "machine_not_monitored", "info",
                          f"{ps_name} has no FOCAS connection (blind spot)",
                          subject=ps_name)
                continue

            status = focas_by_id.get(focas_id)
            if not status:
                self._add("crossref", "machine_no_data", "warning",
                          f"{ps_name} ({focas_id}) has no FOCAS data",
                          subject=ps_name)
                continue

            # Report utilization
            util = utilization.get(focas_id, {})
            util_pct = util.get("utilization_pct", 0)
            self._record_metric(f"utilization_{focas_id}", util_pct)

            if util_pct < 5:
                self._add("crossref", "low_utilization", "warning",
                          f"{ps_name} ({focas_id}) utilization today: {util_pct}%",
                          subject=ps_name)
            elif util_pct < 20:
                self._add("crossref", "below_target_utilization", "info",
                          f"{ps_name} ({focas_id}) utilization today: {util_pct}%",
                          subject=ps_name)
            else:
                self._add("crossref", "utilization_ok", "pass",
                          f"{ps_name} ({focas_id}) utilization today: {util_pct}%",
                          subject=ps_name)

            # Check if machine is running but FOCAS says idle (or vice versa)
            is_running = status.get("run_status") in ("STRT", "MSTR")
            spindle_on = (status.get("spindle_speed") or 0) > 0 and (
                (status.get("spindle_speed") or 0) < SPINDLE_SPEED_MAX_VALID
            )

            # Find active ops scheduled on this machine
            machine_ops = [
                op for op in ops
                if op.get("workCenterPlainText") == ps_name
                and not op.get("isOpComplete")
            ]

            if not machine_ops and (is_running or spindle_on):
                prog = status.get("program_number")
                self._add("crossref", "running_no_wo", "info",
                          f"{ps_name} is running (program O{prog:04d}) but no active ops "
                          f"assigned to this machine in ProShop",
                          subject=ps_name)

    # ══════════════════════════════════════════════════════════════════════
    # CROSS-REFERENCE: PROSHOP <-> FILESYSTEM
    # ══════════════════════════════════════════════════════════════════════

    def check_nc_program_existence(self, ops):
        """Check if NC program files exist on disk for programming-type operations."""
        if not self.nc_root or not self.nc_root.exists():
            return

        checked = 0
        found = 0
        missing_for_active = []

        for op in ops:
            if op.get("isOpComplete"):
                continue
            # Only check machining-type operations (not inspection, assembly, etc.)
            op_type = (op.get("operationType") or "").lower()
            if op_type in ("inspection", "assembly", "shipping", "outside processing", ""):
                continue

            # Skip non-machining op numbers (3000+ = deburr, clean, ship, etc.)
            op_num_raw = op.get("operationNumber") or ""
            try:
                if int(str(op_num_raw).rstrip("FfAaBb")) >= 3000:
                    continue
            except (ValueError, TypeError):
                pass

            # Skip by work center keywords
            wc = (op.get("workCenterPlainText") or "").lower()
            if any(kw in wc for kw in ("deburr", "clean", "ship", "pack", "wash", "bench")):
                continue

            part_num = op.get("_part_number", "")
            cust_part_num = op.get("_customer_part_number", "")
            if not part_num and not cust_part_num:
                continue

            checked += 1
            # Check if a folder exists for this part number or customer part number
            part_dir = self.nc_root / part_num if part_num else None
            cust_dir = self.nc_root / cust_part_num if cust_part_num else None

            if part_dir and part_dir.exists():
                nc_files = list(part_dir.glob("*.nc")) + list(part_dir.glob("*.ncf"))
                if nc_files:
                    found += 1
                else:
                    missing_for_active.append({
                        "wo": op.get("_wo_number"),
                        "op": op.get("operationNumber"),
                        "part": part_num,
                        "reason": "folder_exists_no_nc_files",
                    })
            elif cust_dir and cust_dir.exists():
                nc_files = list(cust_dir.glob("*.nc")) + list(cust_dir.glob("*.ncf"))
                if nc_files:
                    found += 1
                else:
                    missing_for_active.append({
                        "wo": op.get("_wo_number"),
                        "op": op.get("operationNumber"),
                        "part": cust_part_num,
                        "reason": "folder_exists_no_nc_files",
                    })
            else:
                # Try case-insensitive substring match against folder names
                alt_found = False
                for child in self.nc_root.iterdir():
                    if not child.is_dir():
                        continue
                    child_lower = child.name.lower()
                    if (part_num and part_num.lower() in child_lower) or \
                       (cust_part_num and cust_part_num.lower() in child_lower):
                        alt_found = True
                        found += 1
                        break
                if not alt_found:
                    missing_for_active.append({
                        "wo": op.get("_wo_number"),
                        "op": op.get("operationNumber"),
                        "part": part_num or cust_part_num,
                        "reason": "no_folder",
                    })

        if checked > 0:
            pct = round(100 * found / checked, 1)
            self._record_metric("nc_programs_found_pct", pct)
            self._record_field_pop("nc_program_on_disk", "operation", checked, found)

            if missing_for_active:
                # Group by WO for cleaner output
                by_wo = {}
                for m in missing_for_active:
                    wo = m["wo"]
                    if wo not in by_wo:
                        by_wo[wo] = []
                    by_wo[wo].append(m["op"])

                for wo, op_nums in by_wo.items():
                    self._add("readiness", "nc_program_missing", "warning",
                              f"No NC program found on disk for ops {op_nums}",
                              subject=wo,
                              details={"ops": op_nums})

    # ══════════════════════════════════════════════════════════════════════
    # FOCAS-SPECIFIC CHECKS
    # ══════════════════════════════════════════════════════════════════════

    def check_focas_collection_gaps(self):
        """Check for gaps in FOCAS data collection."""
        if not self.focas:
            return
        try:
            health = self.focas.check_health()
            for mid in (health.get("machines") or {}).keys():
                gaps = self.focas.find_collection_gaps(mid, days=3, gap_threshold_minutes=10)
                if gaps:
                    worst = max(gaps, key=lambda g: g["gap_minutes"])
                    severity = "failure" if worst["gap_minutes"] > 60 else "warning"
                    self._add("focas", "collection_gap", severity,
                              f"Machine {mid}: {len(gaps)} data gaps in last 3 days. "
                              f"Worst: {worst['gap_minutes']:.0f} min gap at {worst['start']}",
                              subject=mid,
                              details={"gaps": gaps[:5]})  # Store first 5
                else:
                    self._add("focas", "collection_continuous", "pass",
                              f"Machine {mid}: No collection gaps >10 min in last 3 days",
                              subject=mid)
        except Exception as e:
            self._add("focas", "collection_gaps", "error", f"Gap analysis failed: {e}")

    def check_focas_schema(self):
        """Check that FOCAS database schema matches expected structure."""
        if not self.focas:
            return
        try:
            schema = self.focas.get_schema_info()

            expected_tables = [
                "machine_samples", "tool_wear_samples", "tool_life_samples",
                "alarm_history", "parameter_snapshots", "program_directory",
            ]
            for table in expected_tables:
                if table in schema:
                    cols = schema[table]["column_count"]
                    self._add("focas", f"schema_{table}", "pass",
                              f"Table {table} exists ({cols} columns)")
                else:
                    self._add("focas", f"schema_{table}", "warning",
                              f"Table {table} missing from database")

            # Check machine_samples has expected minimum columns
            ms_cols = schema.get("machine_samples", {}).get("column_count", 0)
            if ms_cols < 40:
                self._add("focas", "schema_machine_samples_short", "warning",
                          f"machine_samples has only {ms_cols} columns (expected 40+). "
                          f"May be running old schema version.")
            self._record_metric("focas_schema_columns", ms_cols)

        except Exception as e:
            self._add("focas", "schema_check", "error", f"Schema check failed: {e}")

    def check_alarm_frequency(self):
        """Check if alarm frequency is abnormal."""
        if not self.focas:
            return
        try:
            counts = self.focas.get_alarm_counts(days=7)
            total_alarms = sum(c.get("alarm_count", 0) for c in counts.values())
            self._record_metric("alarms_7day", total_alarms)

            for mid, data in counts.items():
                count = data.get("alarm_count", 0)
                unique = data.get("unique_alarms", 0)
                if count > 20:
                    self._add("focas", "high_alarm_frequency", "warning",
                              f"Machine {mid}: {count} alarms in 7 days ({unique} unique types)",
                              subject=mid)
                elif count > 0:
                    self._add("focas", "alarm_activity", "info",
                              f"Machine {mid}: {count} alarms in 7 days ({unique} unique types)",
                              subject=mid)
        except Exception as e:
            self._add("focas", "alarm_check", "error", f"Alarm analysis failed: {e}")

    def check_utilization_anomalies(self):
        """Check for machines with unusually low or dropping utilization."""
        if not self.focas:
            return
        try:
            trend = self.focas.get_utilization_range(days=7)
            for mid, days_data in trend.items():
                if len(days_data) < 2:
                    continue
                avg_util = sum(d["utilization_pct"] for d in days_data) / len(days_data)
                self._record_metric(f"avg_util_7d_{mid}", round(avg_util, 1))

                if avg_util < 10:
                    self._add("focas", "chronically_low_utilization", "warning",
                              f"Machine {mid}: 7-day average utilization {avg_util:.1f}%",
                              subject=mid)

                # Check for declining trend
                if len(days_data) >= 5:
                    first_half = sum(d["utilization_pct"] for d in days_data[:len(days_data)//2])
                    second_half = sum(d["utilization_pct"] for d in days_data[len(days_data)//2:])
                    first_avg = first_half / (len(days_data) // 2)
                    second_avg = second_half / (len(days_data) - len(days_data) // 2)
                    if second_avg < first_avg * 0.5 and first_avg > 10:
                        self._add("focas", "declining_utilization", "warning",
                                  f"Machine {mid}: utilization dropped from "
                                  f"{first_avg:.1f}% to {second_avg:.1f}% over 7 days",
                                  subject=mid)
        except Exception as e:
            self._add("focas", "utilization_trend", "error", f"Trend analysis failed: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # FINANCIAL / OVERRUN CHECKS
    # ══════════════════════════════════════════════════════════════════════

    def check_overrun_patterns(self):
        """Analyze completed jobs for quoting accuracy.

        Two passes:
          - Lifetime metrics (every completed WO ever) — kept for historical trend.
          - Recent-window metrics (last 90 days by dueDate) — what the digest headlines.
            Severe-overrun (>20% over target) is the actionable signal; binary overrun
            depends on quoting philosophy and is not a useful headline alone.
        """
        completed = self.ps.get_completed_work_orders()
        if not completed:
            self._add("financial", "overrun_analysis", "info",
                      "No completed work orders to analyze")
            return

        cutoff = datetime.now() - timedelta(days=90)

        with_hours = []
        for wo in completed:
            target = _safe_float(wo.get("hoursCurrentTarget"))
            actual = _safe_float(wo.get("hoursTotalSpent"))
            if not (target and target > 0 and actual and actual > 0):
                continue
            due_dt = None
            due_raw = wo.get("dueDate")
            if due_raw:
                try:
                    due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass
            with_hours.append({
                "wo": wo.get("workOrderNumber"),
                "target": target,
                "actual": actual,
                "overrun_pct": round((actual / target - 1) * 100, 1),
                "hours_over": round(actual - target, 1),
                "part": (wo.get("part") or {}).get("partNumber", ""),
                "family": (wo.get("part") or {}).get("family", ""),
                "due_dt": due_dt,
            })

        if not with_hours:
            self._add("financial", "overrun_analysis", "info",
                      "No completed WOs have both target and actual hours")
            return

        # Lifetime (kept for trending only — not headlined by the digest)
        total = len(with_hours)
        overrun = [w for w in with_hours if w["overrun_pct"] > 0]
        severe = [w for w in with_hours if w["overrun_pct"] > 20]
        overrun_rate = round(100 * len(overrun) / total, 1)
        avg_overrun_pct = round(
            sum(w["overrun_pct"] for w in overrun) / len(overrun), 1
        ) if overrun else 0
        total_hours_over = round(sum(w["hours_over"] for w in with_hours if w["hours_over"] > 0), 1)

        self._record_metric("completed_wos_with_hours", total)
        self._record_metric("overrun_rate_pct", overrun_rate)
        self._record_metric("avg_overrun_pct", avg_overrun_pct)
        self._record_metric("total_hours_over_target", total_hours_over)

        # Last-90-day window — drives the digest headline
        recent = [w for w in with_hours if w["due_dt"] is not None and w["due_dt"] >= cutoff]
        recent_total = len(recent)
        if recent_total > 0:
            recent_overrun = [w for w in recent if w["overrun_pct"] > 0]
            recent_severe = [w for w in recent if w["overrun_pct"] > 20]
            recent_overrun_rate = round(100 * len(recent_overrun) / recent_total, 1)
            recent_severe_rate = round(100 * len(recent_severe) / recent_total, 1)
            recent_hours_over = round(sum(w["hours_over"] for w in recent if w["hours_over"] > 0), 1)

            self._record_metric("recent_completed_wos", recent_total)
            self._record_metric("recent_overrun_rate_pct", recent_overrun_rate)
            self._record_metric("severe_overrun_rate_pct", recent_severe_rate)
            self._record_metric("recent_hours_over_target", recent_hours_over)
            self._record_metric("recent_severe_overrun_count", len(recent_severe))

            # Severity now driven by severe-overrun rate on recent window
            severity = "failure" if recent_severe_rate > 30 else "warning" if recent_severe_rate > 15 else "pass"
            self._add("financial", "overrun_rate", severity,
                      f"Last 90d: {recent_severe_rate}% severe (>20% over) on {recent_total} WOs. "
                      f"Any-overrun: {recent_overrun_rate}%. "
                      f"Hours over: {recent_hours_over}h. "
                      f"(Lifetime: {overrun_rate}% over {total} WOs, {total_hours_over}h.)")
        else:
            self._add("financial", "overrun_rate", "info",
                      f"No completed WOs in last 90 days. "
                      f"Lifetime: {overrun_rate}% on {total} WOs, {total_hours_over}h over.")

        # Top 5 worst overruns
        worst = sorted(with_hours, key=lambda w: w["hours_over"], reverse=True)[:5]
        for w in worst:
            if w["hours_over"] > 2:
                self._add("financial", "worst_overrun", "info",
                          f"WO {w['wo']}: target {w['target']:.1f}h, actual {w['actual']:.1f}h "
                          f"({w['overrun_pct']:+.1f}%, {w['hours_over']:+.1f}h over)",
                          subject=w["wo"],
                          details={"part": w["part"], "family": w["family"]})

        # Overrun by family (if available)
        families = {}
        for w in with_hours:
            fam = w.get("family") or "Unknown"
            if fam not in families:
                families[fam] = {"total": 0, "overrun": 0, "hours_over": 0}
            families[fam]["total"] += 1
            if w["overrun_pct"] > 0:
                families[fam]["overrun"] += 1
                families[fam]["hours_over"] += w["hours_over"]

        for fam, data in sorted(families.items(), key=lambda x: -x[1]["hours_over"]):
            if data["total"] >= 3 and data["hours_over"] > 5:
                rate = round(100 * data["overrun"] / data["total"], 1)
                self._add("financial", "family_overrun", "info",
                          f"Part family '{fam}': {rate}% overrun rate "
                          f"({data['overrun']}/{data['total']} jobs, "
                          f"{data['hours_over']:.1f}h total over)",
                          details={"family": fam})


# ── Helpers ──────────────────────────────────────────────────────────────

SPINDLE_SPEED_MAX_VALID = 100_000


def _safe_float(val):
    """Safely convert to float, return None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _positive(val):
    """Check if a value is a positive number."""
    f = _safe_float(val)
    return f is not None and f > 0
