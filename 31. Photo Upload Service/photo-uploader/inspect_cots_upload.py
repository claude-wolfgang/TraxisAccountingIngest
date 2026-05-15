"""Inspect a ProShop COTS detail page to discover where COTS photos can land.

Models inspect_user_page.py: logs in, navigates to the COTS page, probes it in
both VIEW mode and EDIT mode (after CHECKOUT), and reports:
  - whether any CKEditor instance materializes (→ candidate for P31's
    base64-image insertion path)
  - whether real file <input type="file"> elements appear (→ candidate for a
    different upload path, not currently in P31's worker)
  - what CHECKOUT/SAVE controls and sub-form links are visible
  - which $formName= variants the sidebar exposes

The big unknown the screenshot couldn't answer is "does CHECKOUT cause a
CKEditor to materialize?" — this script answers that.

Outputs:
  data/logs/inspect_cots_<cots>_<phase>_<ts>.png  one screenshot per phase
  data/logs/inspect_cots_<cots>_<ts>.json         machine-readable summary
  inspect_cots_upload.log                         human-readable trace

Usage:
    python inspect_cots_upload.py --cots PAC-223
    python inspect_cots_upload.py --cots PAC-223 --keep-open
    python inspect_cots_upload.py --cots PAC-223 --no-checkout    # skip edit-mode probe

Requires PROSHOP_USERNAME and PROSHOP_PASSWORD in .traxis.env
"""

import argparse
import json
import logging
import os
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(__file__))

import config

BASE_URL = "https://traxismfg.adionsystems.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOGS_DIR / "inspect_cots_upload.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("inspect-cots")


# $formName= variants worth probing on a COTS page. Empty string = the
# default landing form. The script will also extract real sidebar forms
# from anchor hrefs after page load so unknown ones get covered.
CANDIDATE_FORMS = [
    "",  # default landing
    "writtenDescription",
    "description",
    "notes",
    "attachments",
    "files",
    "fileStorage",
    "photos",
    "documents",
    "salesDescription",
    "resources",
    "inventory",
]


def _safe_navigate(driver, url):
    from selenium.common.exceptions import TimeoutException
    try:
        driver.get(url)
    except TimeoutException:
        log.warning(f"Page load timed out for {url} — stopping")
        try:
            driver.execute_script("window.stop()")
        except Exception:
            pass


def _login(driver, username, password):
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import NoSuchElementException

    log.info("Navigating to ProShop login...")
    _safe_navigate(driver, f"{BASE_URL}/procnc/")
    time.sleep(2)

    def find(selectors):
        for selector in selectors:
            try:
                return driver.find_element(*selector)
            except NoSuchElementException:
                continue
        return None

    user_field = find([
        (By.NAME, "mailAddress"), (By.ID, "mailAddress"),
        (By.NAME, "username"), (By.CSS_SELECTOR, "input[type='text']"),
    ])
    pw_field = find([
        (By.NAME, "password"), (By.ID, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ])
    if not user_field or not pw_field:
        log.error("Login form not found")
        return False

    user_field.clear(); user_field.send_keys(username)
    pw_field.clear(); pw_field.send_keys(password)

    submit = find([
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(translate(text(),'login','LOGIN'),'LOGIN')]"),
        (By.CSS_SELECTOR, "input[type='submit']"),
    ])
    if not submit:
        log.error("Submit button not found")
        return False

    submit.click()
    time.sleep(3)

    if "invalid" in driver.page_source.lower() or "incorrect" in driver.page_source.lower():
        log.error("Login failed — invalid credentials")
        return False

    log.info("Login successful")
    return True


def _split_cots_id(cots_id):
    """Split 'PAC-223' → ('PAC', '223'). Bare numbers return ('', '223')."""
    s = cots_id.strip().upper()
    if "-" in s:
        prefix, number = s.split("-", 1)
        return prefix, number
    return "", s


def _switch_into_content_frame(driver):
    """ProShop sometimes serves the form inside a <frame>/<iframe>. Mirror
    the worker's behavior so the probe sees the same DOM the worker would."""
    from selenium.webdriver.common.by import By
    frames = driver.find_elements(By.TAG_NAME, "frame")
    if not frames:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            has_content = driver.execute_script("""
                return (typeof CKEDITOR !== 'undefined') ||
                       document.querySelectorAll('input[type=file]').length > 0 ||
                       document.querySelectorAll('button').length > 5;
            """)
            if has_content:
                return True
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
    return False


def _dump_page_state(driver):
    """Run the same DOM enumeration over whatever frame is currently active."""
    return driver.execute_script(r"""
        function visible(el) {
            if (!el) return false;
            var s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            return el.offsetParent !== null || el.tagName === 'INPUT';
        }

        var ck_count = 0;
        var ck_names = [];
        var ck_details = [];
        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
            ck_names = Object.keys(CKEDITOR.instances);
            ck_count = ck_names.length;
            for (var i = 0; i < ck_names.length; i++) {
                try {
                    var inst = CKEDITOR.instances[ck_names[i]];
                    ck_details.push({
                        name: ck_names[i],
                        status: inst.status,
                        elementName: inst.element ? inst.element.getName() : '',
                        elementId: inst.element ? inst.element.$.id : '',
                        dataLength: (inst.getData ? (inst.getData() || '').length : -1)
                    });
                } catch(e) {
                    ck_details.push({name: ck_names[i], error: e.toString()});
                }
            }
        }

        var file_inputs = [];
        document.querySelectorAll('input[type=file]').forEach(function(el) {
            file_inputs.push({
                name: el.name || '',
                id: el.id || '',
                accept: el.accept || '',
                formAction: el.form ? el.form.action : '(no form)',
                visible: visible(el)
            });
        });

        var textareas = [];
        document.querySelectorAll('textarea').forEach(function(el) {
            textareas.push({
                name: el.name || '',
                id: el.id || '',
                visible: visible(el),
                valueLength: (el.value || '').length
            });
        });

        var buttons = [];
        document.querySelectorAll('button, input[type=submit]').forEach(function(el) {
            if (visible(el)) {
                var t = (el.textContent || el.value || '').trim();
                if (t) buttons.push({
                    text: t.substring(0, 60),
                    id: el.id || '',
                    className: (el.className || '').toString().substring(0, 80)
                });
            }
        });

        var nav_forms = [];
        document.querySelectorAll('a[href*="$formName="]').forEach(function(el) {
            var href = el.getAttribute('href') || '';
            var match = href.match(/\$formName=([^&]+)/);
            if (match) nav_forms.push({
                form: decodeURIComponent(match[1]),
                text: (el.textContent||'').trim().substring(0, 60),
                href: href.substring(0, 200)
            });
        });

        var related_links = [];
        document.querySelectorAll('a').forEach(function(el) {
            var t = (el.textContent || '').trim();
            if (/where used|attachment|file|document|photo|image/i.test(t)) {
                related_links.push({
                    text: t.substring(0, 60),
                    href: (el.getAttribute('href') || '').substring(0, 200)
                });
            }
        });

        return {
            url: window.location.href,
            title: document.title,
            ckeditor_count: ck_count,
            ckeditor_names: ck_names,
            ckeditor_details: ck_details,
            file_input_count: file_inputs.length,
            file_inputs: file_inputs,
            textarea_count: textareas.length,
            textareas: textareas,
            visible_buttons: buttons.slice(0, 50),
            sidebar_forms: nav_forms.slice(0, 50),
            related_links: related_links.slice(0, 30)
        };
    """)


def _shoot(driver, prefix):
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = config.LOGS_DIR / f"{prefix}_{ts}.png"
    try:
        driver.save_screenshot(str(path))
        return str(path.name)
    except Exception as e:
        log.debug(f"Screenshot error: {e}")
        return None


def _find_button(driver, predicate):
    """Find first visible button matching predicate(text_uppercased)."""
    from selenium.webdriver.common.by import By
    for btn in driver.find_elements(By.TAG_NAME, "button"):
        try:
            if not btn.is_displayed():
                continue
            txt = (btn.text or "").strip().upper()
            if predicate(txt):
                return btn
        except Exception:
            continue
    return None


def _wait_for(checker, timeout=30, label="element"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = checker()
            if r:
                return r
        except Exception as e:
            log.debug(f"Poll ({label}): {type(e).__name__}: {e}")
        time.sleep(0.5)
    return None


def _try_checkout(driver, timeout=45):
    """Click CHECKOUT and wait for SAVE to appear. Returns True/False."""
    save_first = _find_button(driver, lambda t: "SAVE" in t)
    if save_first:
        log.info("Already in edit mode (SAVE present without CHECKOUT click)")
        return True

    checkout = _find_button(driver, lambda t: "CHECKOUT" in t and "RECONCILE" not in t)
    if not checkout:
        log.warning("No CHECKOUT button found in current frame")
        return False

    log.info("Clicking CHECKOUT...")
    try:
        driver.execute_script(
            "var el = arguments[0]; setTimeout(function(){ el.click(); }, 0)",
            checkout,
        )
    except Exception as e:
        log.warning(f"CHECKOUT click failed: {e}")
        return False

    save_btn = _wait_for(
        lambda: _find_button(driver, lambda t: "SAVE" in t),
        timeout=timeout, label="SAVE button",
    )
    if save_btn:
        log.info(f"CHECKOUT transition confirmed (SAVE visible after wait)")
        return True
    log.warning(f"CHECKOUT did not transition to edit mode within {timeout}s")
    return False


def _wait_ckeditor_ready(driver, timeout=30):
    """Poll for at least one CKEditor instance in 'ready'/'loaded' state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready = driver.execute_script("""
            if (typeof CKEDITOR === 'undefined' || !CKEDITOR.instances) return false;
            var names = Object.keys(CKEDITOR.instances);
            for (var i = 0; i < names.length; i++) {
                var s = CKEDITOR.instances[names[i]].status;
                if (s === 'ready' || s === 'loaded') return true;
            }
            return false;
        """)
        if ready:
            return True
        time.sleep(0.5)
    return False


def _probe_url(driver, cots_label, phase, url):
    """Navigate + dump (view mode). Returns summary dict."""
    log.info(f"[{phase}] -> {url}")
    _safe_navigate(driver, url)
    time.sleep(2)
    _switch_into_content_frame(driver)

    summary = _dump_page_state(driver)
    summary["phase"] = phase
    summary["screenshot"] = _shoot(driver, f"inspect_cots_{cots_label}_{phase}")

    log.info(
        f"  [{phase}] CKEditors={summary['ckeditor_count']}  "
        f"file_inputs={summary['file_input_count']}  "
        f"textareas={summary['textarea_count']}  "
        f"buttons={len(summary['visible_buttons'])}"
    )
    if summary["ckeditor_names"]:
        log.info(f"  [{phase}] CKEditor instances: {summary['ckeditor_names']}")
    if summary["file_inputs"]:
        log.info(f"  [{phase}] File inputs: {summary['file_inputs']}")

    driver.switch_to.default_content()
    return summary


def _probe_with_checkout(driver, cots_label, url):
    """Visit url, dump view mode, click CHECKOUT, dump edit mode."""
    log.info(f"[checkout-probe] -> {url}")
    _safe_navigate(driver, url)
    time.sleep(2)
    _switch_into_content_frame(driver)

    view_summary = _dump_page_state(driver)
    view_summary["phase"] = "before_checkout"
    view_summary["screenshot"] = _shoot(driver, f"inspect_cots_{cots_label}_before_checkout")
    log.info(
        f"  [before_checkout] CKEditors={view_summary['ckeditor_count']}  "
        f"file_inputs={view_summary['file_input_count']}  "
        f"textareas={view_summary['textarea_count']}"
    )

    checkout_ok = _try_checkout(driver, timeout=45)
    if not checkout_ok:
        _shoot(driver, f"inspect_cots_{cots_label}_checkout_failed")
        return {
            "before_checkout": view_summary,
            "checkout_success": False,
            "after_checkout": None,
            "ckeditor_ready_in_edit_mode": False,
        }

    ck_ready = _wait_ckeditor_ready(driver, timeout=30)
    log.info(f"  CKEditor ready within 30s after CHECKOUT: {ck_ready}")

    time.sleep(1)
    edit_summary = _dump_page_state(driver)
    edit_summary["phase"] = "after_checkout"
    edit_summary["screenshot"] = _shoot(driver, f"inspect_cots_{cots_label}_after_checkout")
    log.info(
        f"  [after_checkout] CKEditors={edit_summary['ckeditor_count']}  "
        f"file_inputs={edit_summary['file_input_count']}  "
        f"textareas={edit_summary['textarea_count']}"
    )
    if edit_summary["ckeditor_names"]:
        log.info(f"  [after_checkout] CKEditor instances: {edit_summary['ckeditor_names']}")
    if edit_summary["file_inputs"]:
        log.info(f"  [after_checkout] File inputs: {edit_summary['file_inputs']}")

    # Don't leave the frame yet — Phase 4 wants to click ADD PICTURE from
    # whatever frame we're in.
    return {
        "before_checkout": view_summary,
        "checkout_success": True,
        "after_checkout": edit_summary,
        "ckeditor_ready_in_edit_mode": ck_ready,
    }


def _probe_add_picture_click(driver, cots_label):
    """After CHECKOUT, click the 'Add picture' button and dump what appears.

    Caller must have already navigated + checked out. Driver is expected to
    be in whatever frame holds the edit-mode form (we don't switch_to.default_content
    in _probe_with_checkout for this reason).
    """
    from selenium.webdriver.common.by import By

    log.info("[add-picture-probe] Looking for 'Add picture' button...")
    target = _find_button(driver, lambda t: "ADD PICTURE" in t)
    if not target:
        log.warning("[add-picture-probe] No 'Add picture' button found in current frame")
        # Try default content as a fallback
        driver.switch_to.default_content()
        target = _find_button(driver, lambda t: "ADD PICTURE" in t)
        if not target:
            log.warning("[add-picture-probe] No 'Add picture' button in default content either")
            return {"button_found": False}

    # Snapshot frame state BEFORE click for diff. Also dump the HTML around
    # the button so we can spot a sibling hidden <input type=file> or any
    # data-* attribute that hints at the click handler.
    pre = driver.execute_script("""
        var btn = arguments[0];
        var ancestor = btn;
        for (var i = 0; i < 4 && ancestor.parentElement; i++) {
            ancestor = ancestor.parentElement;
        }
        var parentHtml = ancestor ? ancestor.outerHTML.substring(0, 3000) : '';

        // List all attributes on the button itself
        var btnAttrs = {};
        for (var j = 0; j < btn.attributes.length; j++) {
            btnAttrs[btn.attributes[j].name] = btn.attributes[j].value;
        }

        return {
            file_input_count: document.querySelectorAll('input[type=file]').length,
            iframe_count: document.querySelectorAll('iframe').length,
            modal_count: document.querySelectorAll('.modal, [role=dialog], .ui-dialog, .cke_dialog').length,
            body_html_length: document.body.innerHTML.length,
            button_attributes: btnAttrs,
            parent_html_excerpt: parentHtml
        };
    """, target)
    log.info(f"[add-picture-probe] Pre-click state: file_inputs={pre['file_input_count']}  "
             f"iframes={pre['iframe_count']}  modals={pre['modal_count']}")
    log.info(f"[add-picture-probe] Button attributes: {pre.get('button_attributes')}")
    _shoot(driver, f"inspect_cots_{cots_label}_pre_add_picture")

    # Install a MutationObserver so we catch any <input type=file> that
    # appears even briefly (some handlers create+click+remove an input).
    driver.execute_script("""
        window.__traxisFileInputs = [];
        if (window.__traxisObserver) try { window.__traxisObserver.disconnect(); } catch(e) {}
        window.__traxisObserver = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var node = added[j];
                    if (!node.querySelectorAll) continue;
                    if (node.tagName === 'INPUT' && node.type === 'file') {
                        window.__traxisFileInputs.push({
                            via: 'direct', name: node.name, id: node.id,
                            accept: node.accept || '', multiple: !!node.multiple,
                            outerHtml: node.outerHTML.substring(0, 500)
                        });
                    }
                    node.querySelectorAll('input[type=file]').forEach(function(el) {
                        window.__traxisFileInputs.push({
                            via: 'descendant', name: el.name, id: el.id,
                            accept: el.accept || '', multiple: !!el.multiple,
                            outerHtml: el.outerHTML.substring(0, 500)
                        });
                    });
                }
            }
        });
        window.__traxisObserver.observe(document.body, {childList: true, subtree: true});
    """)

    log.info("[add-picture-probe] Clicking 'Add picture' via native Selenium click...")
    try:
        target.click()  # native click — propagates user-gesture better than JS .click()
    except Exception as e:
        log.warning(f"[add-picture-probe] Native click failed: {e}, falling back to JS click")
        try:
            driver.execute_script("arguments[0].click();", target)
        except Exception as e2:
            log.error(f"[add-picture-probe] JS click also failed: {e2}")
            return {"button_found": True, "click_error": str(e2)}

    # Give the UI time to render whatever it's going to render
    time.sleep(3)
    _shoot(driver, f"inspect_cots_{cots_label}_post_add_picture")

    # Collect any inputs the MutationObserver saw (even if they were already
    # removed by the time we polled).
    observer_hits = driver.execute_script(
        "return window.__traxisFileInputs || [];"
    )
    log.info(f"[add-picture-probe] MutationObserver caught {len(observer_hits)} file input(s)")
    for hit in observer_hits:
        log.info(f"  observer-hit: {hit}")

    # Look for new file inputs / modals / iframes anywhere on the page
    post = driver.execute_script(r"""
        function visible(el) {
            if (!el) return false;
            var s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            return el.offsetParent !== null || el.tagName === 'INPUT';
        }

        var file_inputs = [];
        document.querySelectorAll('input[type=file]').forEach(function(el) {
            file_inputs.push({
                name: el.name || '',
                id: el.id || '',
                accept: el.accept || '',
                multiple: !!el.multiple,
                formAction: el.form ? el.form.action : '(no form)',
                formMethod: el.form ? el.form.method : '',
                formEnctype: el.form ? el.form.enctype : '',
                visible: visible(el),
                parentTag: el.parentElement ? el.parentElement.tagName : '',
                parentClass: el.parentElement ? (el.parentElement.className || '').toString().substring(0, 80) : ''
            });
        });

        var iframes = [];
        document.querySelectorAll('iframe').forEach(function(el) {
            iframes.push({
                name: el.name || '',
                id: el.id || '',
                src: (el.src || '').substring(0, 200),
                visible: visible(el)
            });
        });

        var modals = [];
        document.querySelectorAll('.modal, [role=dialog], .ui-dialog, .cke_dialog').forEach(function(el) {
            if (visible(el)) {
                modals.push({
                    className: (el.className || '').toString().substring(0, 100),
                    id: el.id || '',
                    role: el.getAttribute('role') || '',
                    htmlPrefix: (el.outerHTML || '').substring(0, 500)
                });
            }
        });

        // Any newly-visible buttons (Upload, Send, Save, etc.)
        var new_buttons = [];
        document.querySelectorAll('button, input[type=submit], a.btn').forEach(function(el) {
            if (visible(el)) {
                var t = (el.textContent || el.value || '').trim();
                if (t) new_buttons.push({
                    text: t.substring(0, 60),
                    id: el.id || '',
                    className: (el.className || '').toString().substring(0, 80)
                });
            }
        });

        return {
            file_input_count: file_inputs.length,
            file_inputs: file_inputs,
            iframe_count: iframes.length,
            iframes: iframes,
            modal_count: modals.length,
            modals: modals,
            visible_buttons: new_buttons.slice(0, 60),
            body_html_length: document.body.innerHTML.length
        };
    """)
    log.info(f"[add-picture-probe] Post-click: file_inputs={post['file_input_count']}  "
             f"iframes={post['iframe_count']}  modals={post['modal_count']}  "
             f"buttons={len(post['visible_buttons'])}")
    for fi in post["file_inputs"]:
        log.info(f"  file_input: {fi}")
    for md in post["modals"]:
        log.info(f"  modal: cls={md['className']!r} role={md['role']!r}")
    for ifr in post["iframes"]:
        if ifr["visible"]:
            log.info(f"  iframe: name={ifr['name']!r} src={ifr['src']!r}")

    # If a file input materialized, also check whether there's a sibling
    # progress / "send to server" button (Selenium can usually send_keys()
    # the local path directly into the input even when it's offscreen).
    return {
        "button_found": True,
        "pre_click": pre,
        "post_click": post,
        "observer_hits": observer_hits,
    }


def main():
    parser = argparse.ArgumentParser(description="Inspect ProShop COTS detail page upload surface")
    parser.add_argument("--cots", default="PAC-223",
                        help="COTS ID, e.g. PAC-223 (default: PAC-223, the live failing case)")
    parser.add_argument("--no-checkout", action="store_true",
                        help="Skip the CHECKOUT click — only probe view mode")
    parser.add_argument("--keep-open", action="store_true",
                        help="Don't close the browser after inspection")
    args = parser.parse_args()

    prefix, number = _split_cots_id(args.cots)
    if not number:
        log.error(f"Could not parse COTS ID: {args.cots}")
        return 1
    cots_label = f"{prefix}-{number}" if prefix else number

    # Both URL forms the worker / extension reference
    url_with_prefix = (f"{BASE_URL}/procnc/ots/{prefix}/{prefix}-{number}"
                      if prefix else None)
    url_bare_number = (f"{BASE_URL}/procnc/ots/{prefix}/{number}"
                      if prefix else f"{BASE_URL}/procnc/ots/{number}")

    username = config.PROSHOP_USERNAME
    password = config.PROSHOP_PASSWORD
    if not username or not password:
        log.error("PROSHOP_USERNAME / PROSHOP_PASSWORD not set in .traxis.env")
        return 1

    try:
        from selenium import webdriver
    except ImportError:
        log.error("selenium not installed: pip install selenium webdriver-manager")
        return 1

    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--disable-gpu")

    log.info("Launching Chrome (visible)...")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(25)

    report = {
        "cots_id": cots_label,
        "url_with_prefix": url_with_prefix,
        "url_bare_number": url_bare_number,
        "url_probes": {},
        "form_probes": {},
        "checkout_probe": None,
    }

    try:
        if not _login(driver, username, password):
            log.error("Login failed — aborting")
            return 1

        # ── Phase 1: probe both URL forms in view mode ────────────────────
        log.info("=" * 70)
        log.info("Phase 1 — probe both URL forms (view mode)")
        log.info("=" * 70)
        candidates = []
        if url_with_prefix:
            candidates.append(("prefixed", url_with_prefix))
        candidates.append(("bare_number", url_bare_number))

        for tag, url in candidates:
            try:
                report["url_probes"][tag] = _probe_url(driver, cots_label, tag, url)
            except Exception as e:
                log.error(f"URL probe {tag} failed: {e}", exc_info=True)
                report["url_probes"][tag] = {"error": str(e)}

        # Decide canonical URL — prefer the prefixed form if both load
        canonical_url = url_with_prefix or url_bare_number
        if url_with_prefix:
            prefixed = report["url_probes"].get("prefixed", {})
            if not isinstance(prefixed, dict) or prefixed.get("ckeditor_count") is None:
                canonical_url = url_bare_number
        log.info(f"Canonical URL for further probes: {canonical_url}")

        # ── Phase 2: probe $formName= variants (still view mode) ──────────
        log.info("=" * 70)
        log.info(f"Phase 2 — probe {len(CANDIDATE_FORMS)-1} candidate sub-forms")
        log.info("=" * 70)
        # Collect any sidebar forms surfaced in Phase 1
        discovered = set()
        for probe in report["url_probes"].values():
            if isinstance(probe, dict):
                for entry in probe.get("sidebar_forms", []) or []:
                    discovered.add(entry.get("form", ""))
        log.info(f"Sidebar forms surfaced in Phase 1: {sorted(discovered)}")

        seen_lower = set()
        forms_to_probe = []
        for f in CANDIDATE_FORMS + sorted(discovered):
            key = f.lower()
            if key in seen_lower or f == "":
                continue
            seen_lower.add(key)
            forms_to_probe.append(f)

        for form_name in forms_to_probe:
            url = f"{canonical_url}$formName={quote(form_name)}"
            try:
                report["form_probes"][form_name] = _probe_url(
                    driver, cots_label, f"form_{form_name}", url
                )
            except Exception as e:
                log.error(f"Form probe {form_name} failed: {e}")
                report["form_probes"][form_name] = {"error": str(e)}

        # ── Phase 3: the big question — CHECKOUT on canonical URL ─────────
        if not args.no_checkout:
            log.info("=" * 70)
            log.info("Phase 3 - CHECKOUT on canonical URL, dump edit-mode DOM")
            log.info("=" * 70)
            try:
                report["checkout_probe"] = _probe_with_checkout(
                    driver, cots_label, canonical_url
                )
            except Exception as e:
                log.error(f"Checkout probe failed: {e}", exc_info=True)
                report["checkout_probe"] = {"error": str(e)}

            # ── Phase 4: click ADD PICTURE, dump what materializes ───────
            log.info("=" * 70)
            log.info("Phase 4 - click 'Add picture' and dump materialized UI")
            log.info("=" * 70)
            ck_probe = report.get("checkout_probe") or {}
            if isinstance(ck_probe, dict) and ck_probe.get("checkout_success"):
                try:
                    report["add_picture_probe"] = _probe_add_picture_click(
                        driver, cots_label
                    )
                except Exception as e:
                    log.error(f"Add-picture probe failed: {e}", exc_info=True)
                    report["add_picture_probe"] = {"error": str(e)}
            else:
                log.warning("Skipping Phase 4 - CHECKOUT did not succeed")
                report["add_picture_probe"] = {"skipped": "checkout failed"}
            driver.switch_to.default_content()

        # ── Verdict ───────────────────────────────────────────────────────
        log.info("=" * 70)
        log.info("Verdict")
        log.info("=" * 70)

        def _has_ck(s):
            return isinstance(s, dict) and s.get("ckeditor_count", 0) > 0

        def _has_file(s):
            return isinstance(s, dict) and s.get("file_input_count", 0) > 0

        ck_locations = []
        file_locations = []
        for tag, probe in report["url_probes"].items():
            if _has_ck(probe):
                ck_locations.append(f"url:{tag}")
            if _has_file(probe):
                file_locations.append(f"url:{tag}")
        for fname, probe in report["form_probes"].items():
            if _has_ck(probe):
                ck_locations.append(f"form:{fname}")
            if _has_file(probe):
                file_locations.append(f"form:{fname}")

        checkout_probe = report.get("checkout_probe") or {}
        if isinstance(checkout_probe, dict):
            after = checkout_probe.get("after_checkout") or {}
            if _has_ck(after):
                ck_locations.append("after_checkout")
            if _has_file(after):
                file_locations.append("after_checkout")
            log.info(f"CHECKOUT succeeded: {checkout_probe.get('checkout_success')}")
            log.info(f"CKEditor ready in edit mode: {checkout_probe.get('ckeditor_ready_in_edit_mode')}")

        log.info(f"Places with CKEditor (P31 base64-image path could work): {ck_locations}")
        log.info(f"Places with file inputs (different upload path): {file_locations}")

        # Phase 4 verdict
        ap = report.get("add_picture_probe") or {}
        if isinstance(ap, dict) and ap.get("button_found"):
            post = ap.get("post_click") or {}
            pre = ap.get("pre_click") or {}
            new_file_inputs = (post.get("file_input_count", 0)
                               - pre.get("file_input_count", 0))
            new_iframes = post.get("iframe_count", 0) - pre.get("iframe_count", 0)
            new_modals = post.get("modal_count", 0) - pre.get("modal_count", 0)
            log.info(f"ADD PICTURE click produced: "
                     f"+{new_file_inputs} file inputs, "
                     f"+{new_iframes} iframes, "
                     f"+{new_modals} modals")
            if new_file_inputs > 0:
                log.info(">>> Real <input type=file> appears after ADD PICTURE click.")
                log.info(">>> Selenium can drive this with send_keys(local_path).")
            elif new_modals > 0 or new_iframes > 0:
                log.info(">>> Modal/iframe opens on ADD PICTURE click.")
                log.info(">>> Inspect modal HTML in the JSON report for upload mechanism.")

        ts = time.strftime("%Y%m%d_%H%M%S")
        out = config.LOGS_DIR / f"inspect_cots_{cots_label}_{ts}.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        log.info(f"Full report: {out}")

        if args.keep_open:
            log.info("Browser kept open — close manually when done")
            try:
                input("Press Enter to close browser... ")
            except (KeyboardInterrupt, EOFError):
                pass

    finally:
        if not args.keep_open:
            try:
                driver.quit()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
