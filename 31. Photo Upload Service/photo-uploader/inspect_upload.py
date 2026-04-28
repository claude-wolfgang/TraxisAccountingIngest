"""Photo Upload Service — CKEditor Image Upload Discovery Script.

Launches Chrome in VISIBLE mode, logs into ProShop, navigates to a WO
operation's written description page, checks it out, and automatically
opens the CKEditor image dialog to inspect its DOM structure.

Saves screenshots and dialog HTML dumps to data/logs/ for offline analysis.

Usage:
    python inspect_upload.py --wo 26-0019 --op 15
    python inspect_upload.py --auto          # auto-pick first active WO

Requires PROSHOP_USERNAME and PROSHOP_PASSWORD in .traxis.env
"""

import sys
import os
import time
import json
import argparse
import logging

sys.path.insert(0, os.path.dirname(__file__))

import config
from proshop_client import ProShopClient

BASE_URL = "https://traxismfg.adionsystems.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOGS_DIR / "inspect_upload.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("inspect-upload")


# ── Selenium helpers ─────────────────────────────────────────────────────

def _safe_navigate(driver, url):
    from selenium.common.exceptions import TimeoutException
    try:
        driver.get(url)
    except TimeoutException:
        log.warning("Page load timed out — stopping and continuing")
        try:
            driver.execute_script("window.stop()")
        except Exception:
            pass


def _find_element(driver, selectors):
    from selenium.common.exceptions import NoSuchElementException
    for selector in selectors:
        try:
            return driver.find_element(*selector)
        except NoSuchElementException:
            continue
    return None


def _wait_for(driver, checker_fn, timeout=30, label="element"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = checker_fn(driver)
            if result:
                return result
        except Exception as e:
            log.debug(f"Poll ({label}): {type(e).__name__}: {e}")
        time.sleep(0.5)
    return None


def _switch_to_editor_frame(driver):
    from selenium.webdriver.common.by import By
    frames = driver.find_elements(By.TAG_NAME, "frame")
    if not frames:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    if not frames:
        log.info("No frames detected — staying in default content")
        return
    log.info(f"Frameset detected with {len(frames)} frames")
    for i, frame in enumerate(frames):
        try:
            driver.switch_to.frame(frame)
            has_button = driver.execute_script("""
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var t = (buttons[i].textContent || '').toUpperCase();
                    if (t.indexOf('CHECKOUT') >= 0 || t.indexOf('SAVE') >= 0) return true;
                }
                return typeof CKEDITOR !== 'undefined';
            """)
            if has_button:
                log.info(f"Switched to content frame {i}")
                return
            driver.switch_to.default_content()
        except Exception as e:
            log.debug(f"Frame {i}: {e}")
            driver.switch_to.default_content()


def _wait_for_ckeditor(driver, timeout=30):
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


def _checkout_page(driver):
    from selenium.webdriver.common.by import By

    def _find_save_button(drv):
        for btn in drv.find_elements(By.TAG_NAME, "button"):
            try:
                if btn.is_displayed() and "SAVE" in (btn.text or "").upper():
                    return True
            except Exception:
                pass
        return None

    if _find_save_button(driver):
        log.info("Already in edit mode")
        return True

    buttons = driver.find_elements(By.TAG_NAME, "button")
    checkout_btn = None
    for btn in buttons:
        try:
            if btn.is_displayed():
                txt = (btn.text or "").strip().upper()
                if "CHECKOUT" in txt and "RECONCILE" not in txt:
                    checkout_btn = btn
                    break
        except Exception:
            pass

    if not checkout_btn:
        log.error("No CHECKOUT button found")
        return False

    log.info("Clicking CHECKOUT...")
    driver.execute_script(
        "var el = arguments[0]; setTimeout(function(){ el.click(); }, 0)",
        checkout_btn,
    )

    save_found = _wait_for(driver, _find_save_button, timeout=45, label="SAVE button")
    return save_found is not None


def _save_screenshot(driver, label):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_label = label.replace(" ", "_").replace("/", "_")[:40]
    path = config.LOGS_DIR / f"inspect_{safe_label}_{timestamp}.png"
    driver.save_screenshot(str(path))
    log.info(f"Screenshot: {path}")
    return path


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Inspect CKEditor image upload dialog in ProShop")
    parser.add_argument("--wo", help="Work order number (e.g. 26-0019)")
    parser.add_argument("--op", help="Operation number (e.g. 15)")
    parser.add_argument("--auto", action="store_true", help="Auto-pick first active WO with mfg ops")
    parser.add_argument("--headless", action="store_true", help="Run headless (no visible window)")
    args = parser.parse_args()

    client = ProShopClient()

    # ── Resolve WO and op ────────────────────────────────────────────────
    if args.auto or (not args.wo):
        log.info("Auto-picking a work order...")
        wos = client._fetch_work_orders()
        detail = None
        for wo in wos:
            if wo.get("status") != "Active":
                continue
            try:
                d = client.get_work_order_detail(wo["workOrderNumber"])
                if d and d.get("ops"):
                    detail = d
                    break
            except Exception:
                continue
        if not detail:
            log.error("No active WO with operations found")
            sys.exit(1)
        wo_number = detail["workOrderNumber"]
        # Pick first op
        op_number = args.op or detail["ops"][0]["opNumber"]
        log.info(f"Auto-selected: WO={wo_number} Op={op_number} Part={detail['partNumber']}")
    else:
        wo_number = args.wo
        op_number = args.op
        if not op_number:
            log.error("--op is required when using --wo")
            sys.exit(1)
        log.info(f"Looking up WO {wo_number}...")
        detail = client.get_work_order_detail(wo_number)
        if not detail:
            log.error(f"Work order {wo_number} not found")
            sys.exit(1)

    part_number = detail["partNumber"]
    customer = detail["customerName"]
    log.info(f"Part: {part_number} | Customer prefix: {customer}")

    # Validate credentials
    username = config.PROSHOP_USERNAME
    password = config.PROSHOP_PASSWORD
    if not username or not password:
        log.error("PROSHOP_USERNAME or PROSHOP_PASSWORD not set in .traxis.env")
        sys.exit(1)

    # ── Launch Chrome ────────────────────────────────────────────────────
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    options = webdriver.ChromeOptions()
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    mode = "headless" if args.headless else "visible"
    log.info(f"Launching Chrome ({mode})...")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(25)

    results = {
        "wo": wo_number, "op": op_number, "part": part_number,
        "customer": customer, "steps": [],
    }

    def step(label, data=None):
        log.info(f"--- {label} ---")
        results["steps"].append({"step": label, "data": data})

    try:
        # ── Login ────────────────────────────────────────────────────────
        step("login_start")
        _safe_navigate(driver, f"{BASE_URL}/procnc/")
        time.sleep(2)

        username_field = _find_element(driver, [
            (By.NAME, "mailAddress"), (By.ID, "mailAddress"),
            (By.NAME, "username"), (By.CSS_SELECTOR, "input[type='text']"),
        ])
        password_field = _find_element(driver, [
            (By.NAME, "password"), (By.ID, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ])
        if not username_field or not password_field:
            step("login_failed", {"reason": "form fields not found"})
            _save_screenshot(driver, "login_form_missing")
            return

        username_field.clear()
        username_field.send_keys(username)
        password_field.clear()
        password_field.send_keys(password)

        submit_btn = _find_element(driver, [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(),'LOGIN')]"),
            (By.XPATH, "//button[contains(text(),'Login')]"),
            (By.CSS_SELECTOR, "input[type='submit']"),
        ])
        if not submit_btn:
            step("login_failed", {"reason": "submit button not found"})
            _save_screenshot(driver, "login_no_submit")
            return

        submit_btn.click()
        time.sleep(3)

        page_source = driver.page_source.lower()
        if "invalid" in page_source or "incorrect" in page_source:
            step("login_failed", {"reason": "invalid credentials"})
            _save_screenshot(driver, "login_invalid")
            return

        step("login_success")
        _save_screenshot(driver, "01_logged_in")

        # ── Navigate to written description ──────────────────────────────
        url = (f"{BASE_URL}/procnc/parts/{customer}/{part_number}"
               f"$formName=writtenDescription&opId={op_number}")
        step("navigate", {"url": url})
        _safe_navigate(driver, url)

        def _page_has_action_button(drv):
            for btn in drv.find_elements(By.TAG_NAME, "button"):
                try:
                    if btn.is_displayed():
                        txt = (btn.text or "").upper()
                        if "CHECKOUT" in txt or "SAVE" in txt:
                            return btn
                except Exception:
                    pass
            return None

        action_btn = _wait_for(driver, _page_has_action_button, timeout=45, label="CHECKOUT/SAVE")
        if not action_btn:
            step("page_load_failed", {"reason": "no CHECKOUT or SAVE button found"})
            _save_screenshot(driver, "02_page_no_action")
            return

        step("page_loaded")
        _save_screenshot(driver, "02_page_loaded")

        # ── Switch to editor frame ───────────────────────────────────────
        _switch_to_editor_frame(driver)

        # ── Checkout ─────────────────────────────────────────────────────
        step("checkout_start")
        if not _checkout_page(driver):
            step("checkout_failed")
            _save_screenshot(driver, "03_checkout_failed")
            return

        step("checkout_success")
        _save_screenshot(driver, "03_checked_out")

        # ── Wait for CKEditor ────────────────────────────────────────────
        step("waiting_ckeditor")
        if not _wait_for_ckeditor(driver, timeout=30):
            step("ckeditor_timeout")
            _save_screenshot(driver, "04_ckeditor_timeout")
            return

        step("ckeditor_ready")

        # ── Dump toolbar info ────────────────────────────────────────────
        toolbar_info = driver.execute_script("""
            var result = {};
            if (typeof CKEDITOR === 'undefined') return {error: 'no CKEDITOR'};

            var names = Object.keys(CKEDITOR.instances);
            result.instanceCount = names.length;
            result.instanceNames = names;
            if (names.length === 0) return result;
            var editor = CKEDITOR.instances[names[0]];

            // Toolbar buttons
            result.toolbarButtons = [];
            try {
                var toolbox = editor.ui.space('toolbox');
                if (toolbox) {
                    var buttons = toolbox.$.querySelectorAll('.cke_button');
                    for (var i = 0; i < buttons.length; i++) {
                        var btn = buttons[i];
                        result.toolbarButtons.push({
                            title: btn.title || btn.getAttribute('title') || '',
                            id: btn.id || '',
                            command: btn.getAttribute('data-cke-tooltip') || ''
                        });
                    }
                }
            } catch(e) { result.toolbarError = e.toString(); }

            // Commands
            result.commands = Object.keys(editor.commands || {});
            result.imageCommands = result.commands.filter(function(c) {
                var cl = c.toLowerCase();
                return cl.indexOf('image') >= 0 || cl.indexOf('upload') >= 0 || cl.indexOf('file') >= 0;
            });

            // Filebrowser config
            try {
                result.filebrowserUploadUrl = editor.config.filebrowserUploadUrl || null;
                result.filebrowserImageUploadUrl = editor.config.filebrowserImageUploadUrl || null;
                result.filebrowserBrowseUrl = editor.config.filebrowserBrowseUrl || null;
            } catch(e) {}

            // Plugins
            result.plugins = Object.keys(CKEDITOR.plugins.registered || {});
            result.imagePlugins = result.plugins.filter(function(p) {
                var pl = p.toLowerCase();
                return pl.indexOf('image') >= 0 || pl.indexOf('upload') >= 0;
            });

            return result;
        """)

        step("toolbar_info", toolbar_info)
        log.info(f"Instances: {toolbar_info.get('instanceNames')}")
        log.info(f"Image commands: {toolbar_info.get('imageCommands')}")
        log.info(f"Image plugins: {toolbar_info.get('imagePlugins')}")
        log.info(f"filebrowserImageUploadUrl: {toolbar_info.get('filebrowserImageUploadUrl')}")
        log.info(f"filebrowserUploadUrl: {toolbar_info.get('filebrowserUploadUrl')}")

        buttons = toolbar_info.get("toolbarButtons", [])
        log.info(f"Toolbar buttons ({len(buttons)}):")
        for btn in buttons:
            log.info(f"  - {btn.get('title')}  [id={btn.get('id')}]")

        # ── Open image dialog programmatically ───────────────────────────
        step("open_image_dialog")
        dialog_opened = driver.execute_script("""
            try {
                var names = Object.keys(CKEDITOR.instances);
                if (names.length === 0) return {error: 'no instances'};
                var editor = CKEDITOR.instances[names[0]];
                editor.execCommand('image');
                return {ok: true};
            } catch(e) {
                return {error: e.toString()};
            }
        """)
        log.info(f"execCommand('image') result: {dialog_opened}")

        if not dialog_opened or dialog_opened.get("error"):
            # Try 'image2' or 'imageUpload'
            for cmd in ["image2", "Image", "uploadimage"]:
                log.info(f"Trying execCommand('{cmd}')...")
                alt = driver.execute_script(f"""
                    try {{
                        var names = Object.keys(CKEDITOR.instances);
                        var editor = CKEDITOR.instances[names[0]];
                        editor.execCommand('{cmd}');
                        return {{ok: true, cmd: '{cmd}'}};
                    }} catch(e) {{
                        return {{error: e.toString()}};
                    }}
                """)
                if alt and alt.get("ok"):
                    log.info(f"Command '{cmd}' worked")
                    break

        time.sleep(2)  # Let dialog render
        _save_screenshot(driver, "05_dialog_opened")

        # ── Dump dialog DOM ──────────────────────────────────────────────
        step("dump_dialog")
        dialog_info = driver.execute_script("""
            var result = {};
            try {
                var dialog = CKEDITOR.dialog.getCurrent();
                if (!dialog) return {error: 'no dialog open'};

                result.dialogName = dialog.getName();
                result.dialogTitle = dialog.getElement().$.querySelector('.cke_dialog_title')
                    ? dialog.getElement().$.querySelector('.cke_dialog_title').textContent : '';

                // Tabs
                var tabs = dialog.getElement().$.querySelectorAll('.cke_dialog_tab');
                result.tabs = [];
                for (var i = 0; i < tabs.length; i++) {
                    result.tabs.push({
                        text: tabs[i].textContent.trim(),
                        className: tabs[i].className,
                        id: tabs[i].id || ''
                    });
                }

                // All form fields
                result.fields = [];
                var inputs = dialog.getElement().$.querySelectorAll('input, select, textarea, button, a.cke_dialog_ui_button');
                for (var j = 0; j < inputs.length; j++) {
                    var inp = inputs[j];
                    result.fields.push({
                        tag: inp.tagName,
                        type: inp.type || '',
                        name: inp.name || '',
                        id: inp.id || '',
                        className: (inp.className || '').substring(0, 100),
                        value: (inp.value || '').substring(0, 50),
                        text: inp.textContent ? inp.textContent.trim().substring(0, 80) : '',
                        visible: inp.offsetParent !== null
                    });
                }

                // File inputs
                var fileInputs = dialog.getElement().$.querySelectorAll('input[type="file"]');
                result.fileInputCount = fileInputs.length;
                result.fileInputs = [];
                for (var k = 0; k < fileInputs.length; k++) {
                    var fi = fileInputs[k];
                    result.fileInputs.push({
                        name: fi.name, id: fi.id,
                        accept: fi.accept || '',
                        formAction: fi.form ? fi.form.action : 'no form',
                        parentId: fi.parentElement ? fi.parentElement.id : '',
                        visible: fi.offsetParent !== null
                    });
                }

                // Iframes (CKEditor uses iframe for file upload form)
                var iframes = dialog.getElement().$.querySelectorAll('iframe');
                result.iframeCount = iframes.length;
                result.iframes = [];
                for (var m = 0; m < iframes.length; m++) {
                    result.iframes.push({
                        name: iframes[m].name || '',
                        id: iframes[m].id || '',
                        src: iframes[m].src || ''
                    });
                }

                // Dialog buttons (OK, Cancel, etc.)
                result.dialogButtons = [];
                var btnDefs = ['ok', 'cancel', 'apply'];
                for (var b = 0; b < btnDefs.length; b++) {
                    try {
                        var dbtn = dialog.getButton(btnDefs[b]);
                        if (dbtn) result.dialogButtons.push(btnDefs[b]);
                    } catch(e) {}
                }

                // Full HTML (first 10K chars)
                result.dialogHtml = dialog.getElement().$.outerHTML.substring(0, 10000);

            } catch(e) {
                result.error = e.toString();
            }
            return result;
        """)

        step("dialog_dump_info_tab", dialog_info)

        if dialog_info and not dialog_info.get("error"):
            log.info(f"\nDialog name: {dialog_info.get('dialogName')}")
            log.info(f"Dialog title: {dialog_info.get('dialogTitle')}")
            log.info(f"Tabs: {[t['text'] for t in dialog_info.get('tabs', [])]}")
            log.info(f"File inputs: {dialog_info.get('fileInputCount')}")
            log.info(f"Iframes: {dialog_info.get('iframeCount')}")
            log.info(f"Dialog buttons: {dialog_info.get('dialogButtons')}")

            for fi in dialog_info.get("fileInputs", []):
                log.info(f"  File input: name={fi['name']}, id={fi['id']}, "
                         f"accept={fi['accept']}, form={fi['formAction']}, visible={fi['visible']}")

            for iframe in dialog_info.get("iframes", []):
                log.info(f"  Iframe: name={iframe['name']}, src={iframe['src']}")

            # Visible fields
            visible_fields = [f for f in dialog_info.get("fields", []) if f.get("visible")]
            log.info(f"\nVisible fields ({len(visible_fields)}):")
            for f in visible_fields:
                log.info(f"  <{f['tag']} type={f['type']} name={f['name']} "
                         f"id={f['id']} text=\"{f['text'][:50]}\">")

            # Save dialog HTML
            html = dialog_info.get("dialogHtml", "")
            if html:
                dump_path = config.LOGS_DIR / "dialog_dump_info.html"
                with open(dump_path, "w", encoding="utf-8") as fh:
                    fh.write(html)
                log.info(f"Dialog HTML saved to: {dump_path}")
        else:
            log.error(f"Dialog dump failed: {dialog_info}")

        # ── Click Upload tab if it exists ────────────────────────────────
        has_upload_tab = False
        for tab in dialog_info.get("tabs", []):
            if "upload" in tab["text"].lower():
                has_upload_tab = True
                break

        if has_upload_tab:
            step("switch_upload_tab")
            tab_result = driver.execute_script("""
                try {
                    var dialog = CKEDITOR.dialog.getCurrent();
                    if (!dialog) return {error: 'no dialog'};
                    var tabs = dialog.getElement().$.querySelectorAll('.cke_dialog_tab');
                    for (var i = 0; i < tabs.length; i++) {
                        if (tabs[i].textContent.trim().toLowerCase().indexOf('upload') >= 0) {
                            tabs[i].click();
                            return {ok: true, tab: tabs[i].textContent.trim()};
                        }
                    }
                    return {error: 'upload tab not found'};
                } catch(e) {
                    return {error: e.toString()};
                }
            """)
            log.info(f"Upload tab click: {tab_result}")
            time.sleep(1)
            _save_screenshot(driver, "06_upload_tab")

            # Dump Upload tab content
            upload_info = driver.execute_script("""
                var result = {};
                try {
                    var dialog = CKEDITOR.dialog.getCurrent();
                    if (!dialog) return {error: 'no dialog'};

                    // File inputs (may now be visible)
                    var fileInputs = dialog.getElement().$.querySelectorAll('input[type="file"]');
                    result.fileInputCount = fileInputs.length;
                    result.fileInputs = [];
                    for (var k = 0; k < fileInputs.length; k++) {
                        var fi = fileInputs[k];
                        result.fileInputs.push({
                            name: fi.name, id: fi.id,
                            accept: fi.accept || '',
                            formAction: fi.form ? fi.form.action : 'no form',
                            parentId: fi.parentElement ? fi.parentElement.id : '',
                            visible: fi.offsetParent !== null
                        });
                    }

                    // Buttons (Send to Server, etc.)
                    result.buttons = [];
                    var btns = dialog.getElement().$.querySelectorAll('a.cke_dialog_ui_button, button');
                    for (var b = 0; b < btns.length; b++) {
                        if (btns[b].offsetParent !== null) {
                            result.buttons.push({
                                text: btns[b].textContent.trim(),
                                id: btns[b].id || '',
                                className: (btns[b].className || '').substring(0, 100),
                                tag: btns[b].tagName
                            });
                        }
                    }

                    // Iframes (upload form target)
                    var iframes = dialog.getElement().$.querySelectorAll('iframe');
                    result.iframes = [];
                    for (var m = 0; m < iframes.length; m++) {
                        result.iframes.push({
                            name: iframes[m].name || '',
                            id: iframes[m].id || '',
                            src: iframes[m].src || ''
                        });
                    }

                    // Check for file inputs inside iframes
                    result.iframeFileInputs = [];
                    for (var n = 0; n < iframes.length; n++) {
                        try {
                            var iframeDoc = iframes[n].contentDocument || iframes[n].contentWindow.document;
                            var ifi = iframeDoc.querySelectorAll('input[type="file"]');
                            for (var p = 0; p < ifi.length; p++) {
                                result.iframeFileInputs.push({
                                    iframeName: iframes[n].name,
                                    name: ifi[p].name, id: ifi[p].id,
                                    formAction: ifi[p].form ? ifi[p].form.action : 'no form'
                                });
                            }
                        } catch(e) {
                            result.iframeFileInputs.push({
                                iframeName: iframes[n].name,
                                error: e.toString()
                            });
                        }
                    }

                    result.dialogHtml = dialog.getElement().$.outerHTML.substring(0, 10000);
                } catch(e) {
                    result.error = e.toString();
                }
                return result;
            """)

            step("upload_tab_dump", upload_info)

            if upload_info:
                log.info(f"\nUpload tab — file inputs: {upload_info.get('fileInputCount')}")
                for fi in upload_info.get("fileInputs", []):
                    log.info(f"  File input: name={fi['name']}, id={fi['id']}, "
                             f"form={fi['formAction']}, visible={fi['visible']}")
                log.info(f"Iframe file inputs: {upload_info.get('iframeFileInputs')}")
                log.info(f"Visible buttons:")
                for btn in upload_info.get("buttons", []):
                    log.info(f"  [{btn['tag']}] \"{btn['text']}\"  id={btn['id']}")

                html2 = upload_info.get("dialogHtml", "")
                if html2:
                    dump_path2 = config.LOGS_DIR / "dialog_dump_upload.html"
                    with open(dump_path2, "w", encoding="utf-8") as fh:
                        fh.write(html2)
                    log.info(f"Upload tab HTML saved to: {dump_path2}")
        else:
            step("no_upload_tab", {"tabs": [t["text"] for t in dialog_info.get("tabs", [])]})
            log.warning("No Upload tab found — CKEditor may not have file upload configured")

        # ── Close dialog ─────────────────────────────────────────────────
        driver.execute_script("""
            try {
                var dialog = CKEDITOR.dialog.getCurrent();
                if (dialog) dialog.hide();
            } catch(e) {}
        """)

        # ── Save full results ────────────────────────────────────────────
        results_path = config.LOGS_DIR / "inspect_results.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        log.info(f"\nFull results saved to: {results_path}")

        # ── Summary ─────────────────────────────────────────────────────
        log.info("\n" + "=" * 60)
        log.info("INSPECTION COMPLETE — SUMMARY")
        log.info("=" * 60)
        log.info(f"WO: {wo_number} | Op: {op_number} | Part: {part_number}")
        log.info(f"Dialog name: {dialog_info.get('dialogName', 'N/A')}")
        log.info(f"Tabs: {[t['text'] for t in dialog_info.get('tabs', [])]}")
        log.info(f"File inputs in dialog: {dialog_info.get('fileInputCount', 0)}")
        if has_upload_tab and upload_info:
            log.info(f"File inputs in Upload tab: {upload_info.get('fileInputCount', 0)}")
            log.info(f"File inputs in iframes: {len(upload_info.get('iframeFileInputs', []))}")
        log.info(f"filebrowserImageUploadUrl: {toolbar_info.get('filebrowserImageUploadUrl')}")
        log.info(f"Image commands: {toolbar_info.get('imageCommands')}")
        log.info("=" * 60)

        if not args.headless:
            log.info("\nBrowser is still open — you can inspect manually.")
            log.info("Press Enter to close.")
            try:
                input(">>> ")
            except (KeyboardInterrupt, EOFError):
                pass

    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        _save_screenshot(driver, "error_unexpected")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        log.info("Browser closed.")


if __name__ == "__main__":
    main()
