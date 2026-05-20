"""
Traxis Customer PO Pusher — lightweight drop-in tool.

Sweeps tom@traxismfg.com / Orders for PDF attachments, classifies + extracts
each as a Customer PO via Claude, and pushes to ProShop via addCustomerPo.
Manual: you click "Sweep", review each candidate's customer + line items,
then push (per row or batch).

Reuses production pieces from accounting_ingest.py so today's accuracy fixes
(Drawing#, Traxis part resolution, ISO date, Rev mirroring, PO prefix) flow
automatically:
  - ProShopClient                 (basic-auth addCustomerPo, lookup_part)
  - AIExtractor.classify/.extract (Claude vision)
  - download_proshop_confirmation (Selenium → PDF, then flip confirmationSent)
  - helpers (_normalize_iso_date, _to_int, _to_float, _looks_like_part_id,
             _clean_drawing_number)

Skips the email polling daemon, ingest_queue.db, QBO side, scan/burst pipeline,
and every doc type other than CUSTOMER_PO.

Provenance tag in ProShop notes: "[P27 CPO drop-in]" — distinguishable from
queue-pushed records ("[P27 ingest q#XX]") in the ProShop UI.

State sidecar: cpo_pusher_state.json — tracks processed Graph message IDs so
re-sweeps don't double-push. No mailbox-side mutation (no read flags, no moves).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

import reconcile_folders as rf
import accounting_ingest as ai

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

MAILBOX = "tom@traxismfg.com"
FOLDER_NAME = "Orders"
LOOKBACK_DAYS = 30
DROPIN_TAG = "[P27 CPO drop-in]"

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_PATH = SCRIPT_DIR / "cpo_pusher_state.json"
WORK_DIR = SCRIPT_DIR / "cpo_pusher_pdfs"
LOG_PATH = SCRIPT_DIR / "cpo_pusher.log"


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"processed_message_ids": [], "last_sweep": None}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"processed_message_ids": [], "last_sweep": None}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _find_orders_folder() -> str:
    folders = rf.list_all_folders(MAILBOX)
    for f in folders:
        if f["displayName"].lower() == FOLDER_NAME.lower():
            return f["id"]
    raise RuntimeError(f"{FOLDER_NAME!r} folder not found in {MAILBOX}")


def _fetch_pdf_attachments(msg_id: str) -> list[Path]:
    """Download every PDF on the message into WORK_DIR. Returns saved paths."""
    import base64 as _b64

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://graph.microsoft.com/v1.0/users/{MAILBOX}/messages/{msg_id}/attachments"
    data = rf.graph_get(url)
    saved: list[Path] = []
    for att in data.get("value", []):
        if att.get("isInline"):
            continue
        name = att.get("name", "") or ""
        if not name.lower().endswith(".pdf"):
            continue
        full = rf.graph_get(f"{url}/{att['id']}")
        content_b64 = full.get("contentBytes")
        if not content_b64:
            continue
        safe = name.replace("/", "_").replace("\\", "_")
        out = WORK_DIR / f"{msg_id[:12]}__{safe}"
        out.write_bytes(_b64.b64decode(content_b64))
        saved.append(out)
    return saved


_CONTACTS_CACHE: dict = {"records": None, "ts": 0.0}


def fetch_contacts_via_basic(proshop: ai.ProShopClient, log) -> list[dict]:
    """Pull ProShop contacts via the basic-auth session and cache for 1h.

    Mirrors ProShopClient.get_contacts but uses the basic-auth path because
    the OAuth client's allowed-scope list doesn't include workorders:rwdp,
    which was added to ACCOUNTING_SCOPE on 2026-05-18 — every proshop.query()
    call now returns 403 invalid_scope. The basic-auth handshake accepts the
    expanded scope, so reads work there."""
    import time as _t
    if _CONTACTS_CACHE["records"] is not None and (_t.time() - _CONTACTS_CACHE["ts"] < 3600):
        return _CONTACTS_CACHE["records"]
    session = proshop._get_basic_session()
    try:
        data = session.execute("{ contacts(pageSize: 500) { records { name companyName } } }")
    except Exception as e:
        log(f"Contacts read failed: {e}")
        return []
    records = (data.get("contacts") or {}).get("records") or []
    _CONTACTS_CACHE["records"] = records
    _CONTACTS_CACHE["ts"] = _t.time()
    return records


def fuzzy_match_contact_basic(proshop: ai.ProShopClient, company_name: str,
                              log) -> list[tuple[float, dict]]:
    """Return [(score, contact), ...] sorted best-first. Empty list on no
    contacts loaded. Reuses ai._name_match_score for parity with the existing
    fuzzy matcher."""
    if not company_name:
        return []
    contacts = fetch_contacts_via_basic(proshop, log)
    scored = [(ai._name_match_score(company_name, c.get("companyName") or ""), c)
              for c in contacts]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:5]


def check_proshop_cpo_duplicate(proshop: ai.ProShopClient, ref_number: str, log) -> str | None:
    """Look for an existing Customer PO in ProShop with the same clientPONumber
    within the last 6 months. Returns a URL string (with optional date suffix)
    on match, or None on no match.

    Specialized for CUSTOMER_PO only — the queue-path version in
    accounting_ingest._check_proshop_duplicate handles all five doc types.
    Logic mirrors that version: normalize PO/P.O./PO# prefix, try normalized
    and raw forms, filter to last 183d client-side (GraphQL date-range syntax
    isn't documented at our scope). Uses OAuth read (proshop.query) since
    reads aren't gated by acceptNewRecord."""
    raw = str(ref_number or "").strip()
    if not raw:
        return None
    norm = re.sub(r'^(p\s*[/\.]?\s*o\s*[#:\-]?\s*|inv(?:oice)?\s*[#:\-]?\s*)',
                  '', raw, flags=re.I).strip()
    candidates: list[str] = []
    for v in (norm, raw):
        if v and v not in candidates:
            candidates.append(v)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=183)).date()
    # OAuth is dead since auth_010 was deleted 2026-05-06 — both reads and
    # writes for customerPOs go through the basic-auth session.
    session = proshop._get_basic_session()

    def _parse_loose(s: str):
        s = str(s or "").strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
            except ValueError:
                continue
        return None

    for cand in candidates:
        safe = cand.replace('"', '\\"')
        gql = (
            '{ customerPOs(filter: {clientPONumber: ["' + safe + '"]}, pageSize: 10) '
            '{ records { proshopUrl dateEntered } } }'
        )
        try:
            data = session.execute(gql)
        except Exception as e:
            log(f"Dup-check query failed (clientPONumber={cand!r}): {e}")
            continue
        records = (data.get("customerPOs") or {}).get("records") or []
        for rec in records:
            date_str = rec.get("dateEntered") or ""
            rec_date = _parse_loose(date_str)
            if rec_date and rec_date < cutoff:
                continue
            url = rec.get("proshopUrl") or "(existing record found)"
            suffix = f"  (dated {date_str})" if date_str else ""
            if cand != raw:
                suffix += f"  [matched normalized '{cand}']"
            return url + suffix
    return None


def _build_cpo_payload(extracted: dict, contact_name: str, proshop: ai.ProShopClient,
                       log) -> dict:
    """Build the addCustomerPo payload from extracted JSON.

    Mirrors ProShopUploader._upload_customer_po + _build_cpo_items in
    accounting_ingest.py but with DROPIN_TAG instead of the queue tag, and no
    queue_id dependency. Field-shape decisions stay in sync with the audited
    production path."""
    po_number = extracted.get("po_number") or extracted.get("quote_number") or ""
    raw_date = extracted.get("po_date") or extracted.get("quote_date") or ""
    po_date = ai._normalize_iso_date(raw_date) or ""
    if raw_date and not po_date:
        log(f"dateEntered unparseable ({raw_date!r}); sending blank")

    payload: dict = {}
    if contact_name:
        payload["client"] = contact_name
    if po_number:
        payload["clientPONumber"] = po_number
    if po_date:
        payload["dateEntered"] = po_date
    if extracted.get("buyer_name"):
        payload["buyer"] = extracted["buyer_name"]
    if extracted.get("payment_terms"):
        payload["paymentTerms"] = extracted["payment_terms"]

    notes_existing = extracted.get("notes") or ""
    payload["notes"] = (f"{DROPIN_TAG}\n\n{notes_existing}" if notes_existing else DROPIN_TAG)

    if extracted.get("ship_to"):
        payload["shiptoAddress"] = extracted["ship_to"]
    disc_pct = ai._to_int(extracted.get("payment_terms_discount_percent"))
    if disc_pct is not None:
        payload["paymentTermsDiscount"] = disc_pct
    disc_days = ai._to_int(extracted.get("payment_terms_discount_days"))
    if disc_days is not None:
        payload["paymentTermsDiscountDays"] = disc_days
    if extracted.get("currency"):
        payload["currency"] = extracted["currency"]

    # partsOrdered is intentionally NOT included here. ProShop's bulk-insert
    # resolver sorts the input lines (apparently by clientPartNumber with a
    # natural-sort collation — confirmed empirically by bulk_order_scatter_test.py
    # across raw + padded itemNumber, identical scatter both runs) before
    # assigning originalSortPosition. Neither itemNumber padding nor any other
    # writable field controls the order. Caller pushes lines serially via
    # updateCustomerPo so each line's transaction commits before the next,
    # giving monotonic originalSortPosition that matches input order. Same
    # mechanism as ProShopBridge.push_sequence_details (line 1525).
    payload["year"] = po_date[:4] or str(datetime.now().year)
    return payload


def _build_cpo_items(line_items, default_due_date, client_code, proshop, log) -> list[dict]:
    """Build UpdateCustomerPoPartOrderedDataInput records — one per extracted
    line item.

    Important: itemNumber must be ZERO-PADDED to a fixed width. ProShop sorts
    partsOrdered by itemNumber lexicographically (string sort), so plain
    "1","2",...,"20" displays as "1, 10, 11, 12, …, 19, 2, 20, 3, …". Padding
    to "001".."020" makes lexicographic == numeric. Verified empirically by
    bulk_order_scatter_test.py: 5 consecutive bulk pushes of 20 lines all
    produced the same lexicographic-by-itemNumber ordering.
    """
    width = max(2, len(str(len(line_items))))  # "01".."09" for ≤9 lines; "001" for ≥100
    out: list[dict] = []
    for idx, li in enumerate(line_items, 1):
        item: dict = {}
        item["itemNumber"] = str(idx).zfill(width)
        pn_field = (li.get("part_number") or "").strip()
        if pn_field:
            item["clientPartNumber"] = pn_field
        if li.get("description"):
            item["lineItemNotes"] = str(li["description"])
        qty = ai._to_int(li.get("quantity"))
        if qty is not None:
            item["quantityOrdered"] = qty
        price = ai._to_float(li.get("unit_price"))
        if price is not None:
            item["pricePer"] = price
        due = li.get("required_date") or default_due_date
        if due:
            item["dueDate"] = str(due)
        rev = li.get("drawing_rev") or li.get("part_rev")
        if rev:
            item["drawingRev"] = str(rev)
            item["partRev"] = str(rev)
        if li.get("first_article_required") is True:
            item["firstArticleRequired"] = True
        # Resolve internal Traxis part: prefer Drawing#, fall back to PN if it
        # looks like a part identifier.
        if client_code:
            lookup_key = ai._clean_drawing_number(li.get("drawing_number"))
            if not lookup_key and ai._looks_like_part_id(pn_field):
                lookup_key = pn_field
            if lookup_key:
                canonical = proshop.lookup_part(client_code, lookup_key)
                if canonical:
                    item["part"] = canonical
                else:
                    log(f"line {idx}: no Traxis part for {client_code}-{lookup_key}")
        if item:
            out.append(item)
    return out


# ─── UI ───────────────────────────────────────────────────────────────────────

class Candidate:
    """One row in the candidate list.

    Source is either:
      - 'email': msg_id is the Graph message id, sender/received come from headers
      - 'file' : msg_id is 'file:<sha1-of-abspath>' so it persists across runs
                  and uniquely identifies the dropped PDF
    """
    def __init__(self, msg: dict | None = None, pdf_path: Path | None = None):
        if msg is not None:
            self.source = "email"
            self.msg_id = msg["id"]
            self.subject = msg.get("subject", "") or ""
            self.sender = ((msg.get("from") or {}).get("emailAddress") or {}).get("address", "")
            self.received = (msg.get("receivedDateTime") or "")[:10]
            self.pdf_paths: list[Path] = []
        elif pdf_path is not None:
            self.source = "file"
            p = pdf_path.resolve()
            self.msg_id = "file:" + hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:16]
            self.subject = p.name
            self.sender = "(dropped file)"
            self.received = datetime.now().strftime("%Y-%m-%d")
            self.pdf_paths = [p]
        else:
            raise ValueError("Candidate needs msg or pdf_path")
        self.extracted: dict | None = None
        self.contact_name: str = ""
        self.status: str = "NEW"   # NEW, PROCESSING, READY, PUSHED, FAILED, SKIPPED, DUPLICATE
        self.error: str = ""
        self.proshop_url: str = ""
        self.override_dup: bool = False  # set True if operator chooses to push past a dup match


_BaseTk = TkinterDnD.Tk if HAS_DND else tk.Tk


class CPOPusherApp(_BaseTk):
    def __init__(self):
        super().__init__()
        self.title("Customer PO Pusher")
        self.geometry("1200x780")
        self.minsize(900, 600)

        self.state_data = _load_state()
        self.proshop = ai.ProShopClient()
        self.extractor = ai.AIExtractor()
        self.candidates: dict[str, Candidate] = {}

        self._build_ui()
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self._log("Drag-and-drop ready — drop PDFs anywhere on this window.")
        else:
            self._log("(tkinterdnd2 not installed — use 'Add PDF…' button to load files.)")
        self._log(f"Email source: {MAILBOX} / {FOLDER_NAME} (last {LOOKBACK_DAYS}d).")
        if self.state_data.get("last_sweep"):
            self._log(f"Last sweep: {self.state_data['last_sweep']}")

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side="top", fill="x")
        self.sweep_btn = ttk.Button(top, text=f"Sweep {FOLDER_NAME}", command=self._on_sweep)
        self.sweep_btn.pack(side="left")
        self.add_btn = ttk.Button(top, text="Add PDF…", command=self._on_add_pdfs)
        self.add_btn.pack(side="left", padx=(8, 0))
        self.extract_btn = ttk.Button(top, text="Extract selected",
                                      command=self._on_extract_selected, state="disabled")
        self.extract_btn.pack(side="left", padx=(8, 0))
        self.push_all_btn = ttk.Button(top, text="Push All READY",
                                       command=self._on_push_all, state="disabled")
        self.push_all_btn.pack(side="left", padx=(8, 0))
        self.status_lbl = ttk.Label(top, text="Idle.")
        self.status_lbl.pack(side="left", padx=12)

        body = ttk.PanedWindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Top half: candidates table
        tbl_frame = ttk.Frame(body)
        body.add(tbl_frame, weight=2)
        cols = ("received", "from", "subject", "customer", "po", "lines", "status")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=10)
        for c, w, anchor in [
            ("received", 90, "w"), ("from", 220, "w"), ("subject", 320, "w"),
            ("customer", 160, "w"), ("po", 110, "w"), ("lines", 50, "center"),
            ("status", 90, "center"),
        ]:
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "subject"))
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Bottom half: preview + per-row actions + log
        bot = ttk.Frame(body)
        body.add(bot, weight=3)

        actions = ttk.Frame(bot, padding=(0, 4))
        actions.pack(side="top", fill="x")
        ttk.Label(actions, text="Customer:").pack(side="left")
        self.customer_var = tk.StringVar()
        self.customer_entry = ttk.Entry(actions, textvariable=self.customer_var, width=30)
        self.customer_entry.pack(side="left", padx=(4, 12))
        self.push_btn = ttk.Button(actions, text="Push to ProShop",
                                   command=self._on_push_selected, state="disabled")
        self.push_btn.pack(side="left")
        self.skip_btn = ttk.Button(actions, text="Skip (mark processed)",
                                   command=self._on_skip_selected, state="disabled")
        self.skip_btn.pack(side="left", padx=(8, 0))
        self.open_btn = ttk.Button(actions, text="Open PDF",
                                   command=self._on_open_pdf, state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))

        preview = ttk.LabelFrame(bot, text="Extracted JSON (read-only)")
        preview.pack(fill="both", expand=True, pady=(4, 4))
        self.preview_txt = tk.Text(preview, wrap="word", height=12)
        self.preview_txt.pack(side="left", fill="both", expand=True)
        psb = ttk.Scrollbar(preview, orient="vertical", command=self.preview_txt.yview)
        psb.pack(side="right", fill="y")
        self.preview_txt.configure(yscrollcommand=psb.set, state="disabled")

        log_frame = ttk.LabelFrame(bot, text="Log")
        log_frame.pack(fill="both", expand=True)
        self.log_txt = tk.Text(log_frame, wrap="word", height=8)
        self.log_txt.pack(side="left", fill="both", expand=True)
        lsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_txt.yview)
        lsb.pack(side="right", fill="y")
        self.log_txt.configure(yscrollcommand=lsb.set, state="disabled")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        ts_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ts_short = ts_iso[11:]
        line = f"[{ts_short}] {msg}\n"
        # Tee to file so the log is tailable outside the GUI.
        try:
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(f"{ts_iso} {msg}\n")
        except Exception:
            pass

        def _append():
            self.log_txt.configure(state="normal")
            self.log_txt.insert("end", line)
            self.log_txt.see("end")
            self.log_txt.configure(state="disabled")

        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.after(0, _append)

    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.status_lbl.configure(text=msg))

    def _refresh_row(self, cand: Candidate) -> None:
        po = (cand.extracted or {}).get("po_number") or ""
        cust = cand.contact_name or ""
        lines = len((cand.extracted or {}).get("line_items") or [])
        values = (cand.received, cand.sender, cand.subject, cust, po,
                  str(lines) if cand.extracted else "", cand.status)
        if self.tree.exists(cand.msg_id):
            self.tree.item(cand.msg_id, values=values)
        else:
            self.tree.insert("", "end", iid=cand.msg_id, values=values)
        # Enable Push All button if any READY exist
        any_ready = any(c.status == "READY" for c in self.candidates.values())
        self.push_all_btn.configure(state="normal" if any_ready else "disabled")

    def _selected(self) -> Candidate | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.candidates.get(sel[0])

    # ── Sweep ───────────────────────────────────────────────────────────────

    def _on_sweep(self):
        self.sweep_btn.configure(state="disabled")
        self._set_status("Sweeping…")
        threading.Thread(target=self._sweep_worker, daemon=True).start()

    def _sweep_worker(self):
        """Stage 1: just list messages with attachments. No PDF download, no
        Claude calls. Cheap — pure Graph metadata fetch. Per-row 'Extract'
        does the expensive work one at a time so you can pace it."""
        try:
            folder_id = _find_orders_folder()
            msgs = rf.messages_in_folder(MAILBOX, folder_id, LOOKBACK_DAYS)
        except Exception as e:
            self._log(f"Sweep failed: {e}")
            self._set_status("Sweep failed.")
            self.after(0, lambda: self.sweep_btn.configure(state="normal"))
            return

        seen = set(self.state_data.get("processed_message_ids", []))
        new_msgs = [m for m in msgs if m["id"] not in seen and m.get("hasAttachments")]
        self._log(f"Found {len(msgs)} messages in {FOLDER_NAME} "
                  f"(lookback {LOOKBACK_DAYS}d), {len(new_msgs)} unprocessed w/ attachments.")
        self._set_status(f"{len(new_msgs)} candidate(s) listed — select one and click Extract.")

        for m in new_msgs:
            cand = Candidate(m)
            self.candidates[cand.msg_id] = cand
            self.after(0, lambda c=cand: self._refresh_row(c))

        self.state_data["last_sweep"] = datetime.now().isoformat(timespec="seconds")
        _save_state(self.state_data)
        self.after(0, lambda: self.sweep_btn.configure(state="normal"))

    # ── Drag-drop / Add PDF ─────────────────────────────────────────────────

    def _on_drop(self, event):
        # tkinterdnd2 hands us a Tcl-list string. Use splitlist to respect
        # paths-with-spaces wrapped in {braces}.
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        self._add_pdf_paths([Path(p) for p in paths])

    def _on_add_pdfs(self):
        paths = filedialog.askopenfilenames(
            title="Add customer PO PDF(s)",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if paths:
            self._add_pdf_paths([Path(p) for p in paths])

    def _add_pdf_paths(self, paths: list[Path]):
        added = 0
        for p in paths:
            if not p.exists() or p.suffix.lower() != ".pdf":
                self._log(f"Skipped (not a PDF or missing): {p}")
                continue
            cand = Candidate(pdf_path=p)
            if cand.msg_id in self.candidates:
                self._log(f"Already in list: {p.name}")
                # Re-select the existing row so the operator sees it.
                if self.tree.exists(cand.msg_id):
                    self.tree.selection_set(cand.msg_id)
                    self.tree.see(cand.msg_id)
                continue
            self.candidates[cand.msg_id] = cand
            self._refresh_row(cand)
            added += 1
        if added:
            self._log(f"Added {added} PDF(s). Select a row and click Extract.")

    # ── Extract (per row, on demand) ────────────────────────────────────────

    def _on_extract_selected(self):
        cand = self._selected()
        if not cand or cand.status not in ("NEW", "FAILED"):
            return
        cand.status = "PROCESSING"
        self._refresh_row(cand)
        self.extract_btn.configure(state="disabled")
        threading.Thread(target=self._extract_worker, args=(cand,), daemon=True).start()

    def _extract_worker(self, cand: Candidate):
        try:
            if not cand.pdf_paths:
                cand.pdf_paths = _fetch_pdf_attachments(cand.msg_id)
            if not cand.pdf_paths:
                cand.status = "SKIPPED"
                cand.error = "no PDF attachments"
                self._log(f"{cand.subject!r}: no PDF attachments — skipped.")
                return
            pdf = cand.pdf_paths[0]
            self._log(f"Classifying {pdf.name}…")
            doc_type = self.extractor.classify(str(pdf), cand.subject, cand.sender)
            if doc_type != "CUSTOMER_PO":
                cand.status = "SKIPPED"
                cand.error = f"classified as {doc_type}"
                self._log(f"{pdf.name}: classified as {doc_type}, not CUSTOMER_PO — skipped.")
                return
            self._log(f"Extracting {pdf.name}…")
            extracted = self.extractor.extract(str(pdf), "CUSTOMER_PO")
            cand.extracted = extracted
            cust_name = (extracted.get("customer_name") or "").strip()
            contact_code = ""
            if cust_name:
                matches = fuzzy_match_contact_basic(self.proshop, cust_name, self._log)
                if matches and matches[0][0] >= 0.7:
                    contact_code = matches[0][1].get("name") or ""
            cand.contact_name = contact_code
            cand.status = "READY"
            self._log(f"READY: customer {cust_name!r} (matched {contact_code or '—'}), "
                      f"{len(extracted.get('line_items') or [])} lines.")
        except Exception as e:
            cand.status = "FAILED"
            cand.error = str(e)
            self._log(f"Extract failed: {e}")
        finally:
            self.after(0, lambda: self._refresh_row(cand))
            self.after(0, self._on_select)

    # ── Selection / preview ─────────────────────────────────────────────────

    def _on_select(self, _event=None):
        cand = self._selected()
        if not cand:
            return
        self.customer_var.set(cand.contact_name)
        self.preview_txt.configure(state="normal")
        self.preview_txt.delete("1.0", "end")
        if cand.extracted:
            self.preview_txt.insert("1.0", json.dumps(cand.extracted, indent=2))
        elif cand.error:
            self.preview_txt.insert("1.0", f"(no extraction)\n\nError: {cand.error}")
        self.preview_txt.configure(state="disabled")
        self.push_btn.configure(state="normal" if cand.status in ("READY", "DUPLICATE") else "disabled")
        self.extract_btn.configure(state="normal" if cand.status in ("NEW", "FAILED") else "disabled")
        self.skip_btn.configure(state="normal" if cand.status in ("NEW", "READY", "FAILED", "SKIPPED", "DUPLICATE") else "disabled")
        self.open_btn.configure(state="normal" if cand.pdf_paths else "disabled")

    def _on_open_pdf(self):
        cand = self._selected()
        if cand and cand.pdf_paths:
            import os
            os.startfile(str(cand.pdf_paths[0]))

    # ── Push actions ────────────────────────────────────────────────────────

    def _push(self, cand: Candidate):
        if cand.status != "READY":
            return
        # Pick up any operator edit to customer name.
        contact_name = self.customer_var.get().strip() or cand.contact_name
        if not contact_name:
            messagebox.showwarning("Missing customer",
                                   "Customer is empty — set a ProShop contact name first.")
            return
        cand.contact_name = contact_name
        cand.status = "PROCESSING"
        self._refresh_row(cand)
        self.push_btn.configure(state="disabled")
        threading.Thread(target=self._push_worker, args=(cand,), daemon=True).start()

    def _push_worker(self, cand: Candidate):
        try:
            # Dup-check (skip if operator already overrode after a prior prompt).
            extracted = cand.extracted or {}
            ref_number = (extracted.get("po_number") or extracted.get("quote_number") or "").strip()
            if ref_number and not cand.override_dup:
                self._log(f"Dup-check: clientPONumber={ref_number!r}…")
                existing = check_proshop_cpo_duplicate(self.proshop, ref_number, self._log)
                if existing:
                    self._log(f"DUPLICATE: {ref_number!r} already in ProShop → {existing}")
                    cand.status = "DUPLICATE"
                    cand.error = f"already in ProShop: {existing}"
                    cand.proshop_url = existing.split("  (")[0].strip()  # strip date suffix for URL
                    # Ask on the UI thread, then re-dispatch if operator overrides.
                    self.after(0, lambda c=cand, e=existing, r=ref_number:
                               self._prompt_dup_override(c, e, r))
                    return
            payload = _build_cpo_payload(extracted, cand.contact_name,
                                         self.proshop, self._log)
            line_items = _build_cpo_items(
                extracted.get("line_items", []) or [],
                default_due_date=extracted.get("required_date"),
                client_code=cand.contact_name,
                proshop=self.proshop,
                log=self._log,
            )
            self._log(f"Pushing → addCustomerPo (client={cand.contact_name}, "
                      f"clientPONumber={payload.get('clientPONumber','')}, "
                      f"lines pending={len(line_items)})")
            result = self.proshop.add_customer_po(payload)
            rec = result.get("addCustomerPo") or {}
            po_id = rec.get("poId")
            proshop_url = rec.get("proshopUrl") or ""
            if not po_id:
                raise RuntimeError(f"addCustomerPo returned no poId: {result}")
            cand.proshop_url = proshop_url
            self._log(f"Created header: poId={po_id}  url={proshop_url}")
            # Push each line individually so each transaction commits before the
            # next starts, giving monotonic originalSortPosition matching input
            # order. Bulk-add gets sorted by ProShop on insert (see scatter test).
            for i, item in enumerate(line_items, 1):
                self._log(f"  line {i}/{len(line_items)}: itemNumber={item.get('itemNumber')!r} "
                          f"clientPartNumber={item.get('clientPartNumber','')!r}")
                self.proshop.update_customer_po(po_id, {"partsOrdered": [{"data": item}]})
            cand.status = "PUSHED"
            self._log(f"Pushed all {len(line_items)} line(s) for {po_id}.")
            # Record in state so re-sweeps skip this message.
            ids = self.state_data.setdefault("processed_message_ids", [])
            if cand.msg_id not in ids:
                ids.append(cand.msg_id)
                _save_state(self.state_data)
            # Confirmation PDF + flip confirmationSent — background.
            threading.Thread(target=self._confirmation_worker,
                             args=(cand, po_id, proshop_url), daemon=True).start()
        except Exception as e:
            cand.status = "FAILED"
            cand.error = str(e)
            self._log(f"Push failed: {e}")
        finally:
            self.after(0, lambda: self._refresh_row(cand))
            self.after(0, self._on_select)

    def _prompt_dup_override(self, cand: Candidate, existing: str, ref_number: str) -> None:
        """Modal: a matching CustomerPo already exists. Offer to open it,
        skip (mark processed), or override and push anyway."""
        self._refresh_row(cand)
        self.push_btn.configure(state="disabled")

        win = tk.Toplevel(self)
        win.title("Possible duplicate")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, padding=12, wraplength=520, justify="left",
                  text=(f"ProShop already has a Customer PO with clientPONumber "
                        f"{ref_number!r} in the last 6 months:\n\n{existing}\n\n"
                        f"Push anyway to create a second record, or skip?")).pack()
        btns = ttk.Frame(win, padding=(12, 0, 12, 12))
        btns.pack(fill="x")

        def _open_existing():
            url = cand.proshop_url
            if url:
                import webbrowser
                webbrowser.open(url)

        def _skip():
            win.destroy()
            cand.status = "SKIPPED"
            ids = self.state_data.setdefault("processed_message_ids", [])
            if cand.msg_id not in ids:
                ids.append(cand.msg_id)
                _save_state(self.state_data)
            self._refresh_row(cand)
            self._on_select()
            self._log(f"Skipped (duplicate of existing): {ref_number}")

        def _override():
            win.destroy()
            cand.override_dup = True
            cand.status = "READY"
            cand.error = ""
            self._refresh_row(cand)
            self._log(f"Operator override: pushing duplicate {ref_number!r} anyway")
            self._push(cand)

        def _cancel():
            win.destroy()
            cand.status = "READY"  # leave the row pushable again later
            self._refresh_row(cand)
            self._on_select()

        ttk.Button(btns, text="Open existing in browser",
                   command=_open_existing).pack(side="left")
        ttk.Button(btns, text="Skip (mark processed)",
                   command=_skip).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Cancel", command=_cancel).pack(side="right")
        ttk.Button(btns, text="Override and push anyway",
                   command=_override).pack(side="right", padx=(0, 8))

    def _confirmation_worker(self, cand: Candidate, po_id: str, proshop_url: str):
        try:
            pdf_path = ai.download_proshop_confirmation(proshop_url, po_id, self._log)
            if not pdf_path:
                return
            self.proshop.update_customer_po(po_id, {
                "confirmationSent": True,
                "confirmationSentBy": ai.ENV.get("PROSHOP_USERNAME", "P27"),
                "confirmationNotes": f"Auto-generated via P27 CPO Pusher -> {pdf_path}",
            })
            self._log(f"CPO {po_id}: confirmationSent flag set in ProShop")
        except Exception as e:
            self._log(f"CPO {po_id}: confirmation step failed (PDF may still be saved): {e}")

    def _on_push_selected(self):
        cand = self._selected()
        if cand:
            self._push(cand)

    def _on_push_all(self):
        ready = [c for c in self.candidates.values() if c.status == "READY"]
        if not ready:
            return
        if not messagebox.askyesno("Push all READY",
                                   f"Push {len(ready)} READY record(s) to ProShop?"):
            return
        for c in ready:
            self._push(c)

    def _on_skip_selected(self):
        cand = self._selected()
        if not cand:
            return
        cand.status = "SKIPPED"
        ids = self.state_data.setdefault("processed_message_ids", [])
        if cand.msg_id not in ids:
            ids.append(cand.msg_id)
            _save_state(self.state_data)
        self._refresh_row(cand)
        self._log(f"Marked processed (skipped): {cand.subject!r}")


def main():
    app = CPOPusherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
