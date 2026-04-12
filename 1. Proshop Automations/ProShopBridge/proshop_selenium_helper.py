"""
ProShop Selenium Helper — Sequence Detail & Written Description Automation
Called as a subprocess from ProShopBridge (Fusion 360 add-in).

Modes:
  sequence-detail (default):
    Sorts rows by Seq # ascending, extracts T## into G-Code Tool # fields, saves.

  written-description:
    Reads HTML from stdin, navigates to written description page,
    checks out, sets CKEditor content, saves.

Usage:
    python proshop_selenium_helper.py --part-number TRA1-10983 --op-number 60
    python proshop_selenium_helper.py --mode written-description --part-number TRA1-10983 --op-number 60 < content.html
    python proshop_selenium_helper.py --mode written-description --part-number TRA1-10983 --op-number 60 --visible

Reads PROSHOP_USERNAME and PROSHOP_PASSWORD from ~/.traxis.env

Version: 2.1
"""

import sys
import os
import time
import argparse
import logging
import logging.handlers
import glob as globmod

BASE_URL = "https://traxismfg.adionsystems.com"

# Module-level logger — configured in _setup_logging()
_log = logging.getLogger("selenium_helper")


# ===========================================================================
# Logging Setup
# ===========================================================================

def _setup_logging():
    """Configure dual logging: stdout (for parent process) + rotating file."""
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass

    _log.setLevel(logging.DEBUG)
    _log.propagate = False

    # Stdout handler — INFO+ only, STATUS: prefix for parent process parsing
    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setLevel(logging.INFO)
    stdout_h.setFormatter(logging.Formatter("STATUS: %(message)s"))
    _log.addHandler(stdout_h)

    # File handler — DEBUG+, full detail
    log_file = os.path.join(log_dir, "selenium.log")
    try:
        file_h = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_h.setLevel(logging.DEBUG)
        file_h.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        _log.addHandler(file_h)
    except Exception as e:
        print(f"WARNING: Could not create log file: {e}", file=sys.stderr)

    # Cleanup old failure screenshots (>7 days)
    try:
        cutoff = time.time() - 7 * 86400
        for png in globmod.glob(os.path.join(log_dir, "fail_*.png")):
            if os.path.getmtime(png) < cutoff:
                os.remove(png)
    except Exception:
        pass


def _dump_page_state(driver, label):
    """Capture full browser state for diagnosing failures.
    Saves screenshot + logs URL, title, frames, buttons, CKEditor status, console errors."""
    _log.error(f"=== PAGE STATE DUMP: {label} ===")

    # URL and title
    try:
        _log.error(f"  URL: {driver.current_url}")
        _log.error(f"  Title: {driver.title}")
    except Exception as e:
        _log.error(f"  Could not read URL/title: {e}")

    # Frame inventory
    try:
        from selenium.webdriver.common.by import By
        frames = driver.find_elements(By.TAG_NAME, "frame")
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        _log.error(f"  Frames: {len(frames)} <frame>, {len(iframes)} <iframe>")
    except Exception as e:
        _log.error(f"  Frame check error: {e}")

    # Button inventory
    try:
        from selenium.webdriver.common.by import By
        buttons = driver.find_elements(By.TAG_NAME, "button")
        visible_buttons = []
        for btn in buttons:
            try:
                if btn.is_displayed():
                    visible_buttons.append(btn.text.strip() or "(empty)")
            except Exception:
                pass
        _log.error(f"  Visible buttons ({len(visible_buttons)}): {visible_buttons}")
    except Exception as e:
        _log.error(f"  Button inventory error: {e}")

    # CKEditor status
    try:
        ck_info = driver.execute_script("""
            if (typeof CKEDITOR === 'undefined') return {present: false};
            if (!CKEDITOR.instances) return {present: true, instances: 0};
            var names = Object.keys(CKEDITOR.instances);
            var details = [];
            for (var i = 0; i < names.length; i++) {
                var inst = CKEDITOR.instances[names[i]];
                details.push({name: names[i], status: inst.status, dataLen: (inst.getData() || '').length});
            }
            return {present: true, instances: names.length, details: details};
        """)
        _log.error(f"  CKEditor: {ck_info}")
    except Exception as e:
        _log.error(f"  CKEditor check error: {e}")

    # Chrome console errors
    try:
        browser_logs = driver.get_log("browser")
        errors = [e for e in browser_logs if e.get("level") in ("SEVERE", "WARNING")]
        if errors:
            _log.error(f"  Chrome console errors ({len(errors)}):")
            for entry in errors[:20]:
                _log.error(f"    [{entry.get('level')}] {entry.get('message', '')[:200]}")
        else:
            _log.error(f"  Chrome console: no errors ({len(browser_logs)} total entries)")
    except Exception as e:
        _log.error(f"  Console log capture error: {e}")

    # Screenshot
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_label = label.replace(" ", "_").replace("/", "_")[:40]
        screenshot_path = os.path.join(log_dir, f"fail_{safe_label}_{timestamp}.png")
        driver.save_screenshot(screenshot_path)
        _log.error(f"  Screenshot: {screenshot_path}")
    except Exception as e:
        _log.error(f"  Screenshot error: {e}")

    _log.error(f"=== END PAGE STATE DUMP ===")


# ===========================================================================
# Helpers
# ===========================================================================

def load_env():
    """Read key=value pairs from ~/.traxis.env."""
    env_path = os.path.join(os.path.expanduser("~"), ".traxis.env")
    creds = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
    return creds


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="ProShop Selenium helper for sequence detail and written description pages")
    parser.add_argument("--mode", default="sequence-detail",
                        choices=["sequence-detail", "written-description"],
                        help="Which page to automate")
    parser.add_argument("--part-number", required=True, help="Part number (e.g., TRA1-10983)")
    parser.add_argument("--op-number", required=True, help="Operation number (e.g., 60)")
    parser.add_argument("--visible", action="store_true", help="Show browser window (for debugging)")
    args = parser.parse_args()

    _setup_logging()
    _log.info(f"=== Started: mode={args.mode}, part={args.part_number}, op={args.op_number}, visible={args.visible} ===")

    # For written-description mode, read HTML from stdin
    html_content = None
    if args.mode == "written-description":
        html_content = sys.stdin.read()
        if not html_content.strip():
            _log.error("No HTML content provided on stdin")
            print("ERROR: No HTML content provided on stdin")
            sys.exit(1)
        _log.info(f"Read {len(html_content)} bytes of HTML from stdin")

    driver = _setup_and_login(args)
    try:
        if args.mode == "sequence-detail":
            _run_sequence_detail(driver, args)
        elif args.mode == "written-description":
            _run_written_description(driver, args, html_content)
    except Exception as e:
        _log.error(f"Unhandled exception: {e}", exc_info=True)
        _dump_page_state(driver, "unhandled_exception")
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _setup_and_login(args):
    """Common setup: load credentials, launch browser, log in. Returns driver."""
    from selenium.webdriver.common.by import By

    creds = load_env()
    username = creds.get("PROSHOP_USERNAME", "")
    password = creds.get("PROSHOP_PASSWORD", "")
    if not username or not password:
        _log.error("PROSHOP_USERNAME or PROSHOP_PASSWORD not found in ~/.traxis.env")
        print("ERROR: PROSHOP_USERNAME or PROSHOP_PASSWORD not found in ~/.traxis.env")
        sys.exit(1)

    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    except ImportError:
        _log.error("selenium not installed")
        print("ERROR: selenium not installed. Run: pip install selenium")
        sys.exit(1)

    options = webdriver.ChromeOptions()
    if not args.visible:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    # Enable browser logging for console capture
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    t0 = time.time()
    _log.info("Launching Chrome...")
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        _log.error(f"Chrome launch FAILED: {e}", exc_info=True)
        print(f"ERROR: Chrome launch failed: {e}")
        sys.exit(1)

    # Log Chrome + ChromeDriver versions
    try:
        caps = driver.capabilities
        chrome_ver = caps.get("browserVersion", caps.get("version", "unknown"))
        driver_ver = caps.get("chrome", {}).get("chromedriverVersion", "unknown")
        if isinstance(driver_ver, str):
            driver_ver = driver_ver.split(" ")[0]
        _log.info(f"[chrome] Launched in {time.time() - t0:.1f}s — Chrome {chrome_ver}, ChromeDriver {driver_ver}")
    except Exception as e:
        _log.debug(f"Could not read Chrome versions: {e}")
        _log.info(f"[chrome] Launched in {time.time() - t0:.1f}s")

    # Keep page load timeout short — we use window.stop() + element polling
    # instead of waiting for slow file-server resources to finish loading.
    driver.set_page_load_timeout(20)

    # Login
    t0 = time.time()
    _log.info("Logging in...")
    _safe_navigate(driver, f"{BASE_URL}/procnc/")
    time.sleep(2)

    username_field = _find_element(driver, [
        (By.NAME, "mailAddress"), (By.ID, "mailAddress"),
        (By.NAME, "username"), (By.ID, "username"),
        (By.CSS_SELECTOR, "input[type='text']"),
    ])
    password_field = _find_element(driver, [
        (By.NAME, "password"), (By.ID, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ])
    if not username_field or not password_field:
        _log.error("Could not find login form fields")
        _dump_page_state(driver, "login_form_not_found")
        driver.quit()
        print("ERROR: Could not find login form fields")
        sys.exit(1)

    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)

    submit_btn = _find_element(driver, [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(text(),'LOGIN')]"),
        (By.XPATH, "//button[contains(text(),'Login')]"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (By.XPATH, "//input[@value='Login']"),
    ])
    if not submit_btn:
        _log.error("Could not find login button")
        _dump_page_state(driver, "login_button_not_found")
        driver.quit()
        print("ERROR: Could not find login button")
        sys.exit(1)

    submit_btn.click()
    time.sleep(3)

    page_source = driver.page_source.lower()
    if "invalid" in page_source or "incorrect" in page_source:
        _log.error("Login failed — invalid credentials")
        _dump_page_state(driver, "login_failed")
        driver.quit()
        print("ERROR: Login failed — invalid credentials")
        sys.exit(1)

    _log.info(f"[login] Completed in {time.time() - t0:.1f}s")
    return driver


def _run_sequence_detail(driver, args):
    """Sequence detail mode: sort rows, fix G-Code Tool #, save."""
    customer = args.part_number.split("-")[0] if "-" in args.part_number else args.part_number
    url = (f"{BASE_URL}/procnc/parts/{customer}/{args.part_number}"
           f"?formName=toolDetail&opId={args.op_number}")

    t0 = time.time()
    _log.info("Navigating to sequence details...")
    _log.debug(f"  URL: {url}")
    _safe_navigate(driver, url)

    # Poll for the Seq # header instead of fixed sleep
    seq_header = _wait_for_element(driver, _find_seq_header, timeout=30)
    if not seq_header:
        url2 = (f"{BASE_URL}/procnc/parts/{args.part_number}/{args.part_number}"
                f"?formName=toolDetail&opId={args.op_number}")
        _log.info("Trying alternate URL...")
        _log.debug(f"  URL: {url2}")
        _safe_navigate(driver, url2)
        seq_header = _wait_for_element(driver, _find_seq_header, timeout=30)

    if not seq_header:
        _log.error("Could not find sequence detail table (no 'Seq #' header)")
        _dump_page_state(driver, "seq_header_not_found")
        print("ERROR: Could not find sequence detail table (no 'Seq #' header found)")
        sys.exit(1)

    _log.info(f"[navigate] Found sequence detail table in {time.time() - t0:.1f}s")

    t0 = time.time()
    _log.info("Checking out page...")
    if not _checkout_page(driver):
        _log.error("Could not checkout page for editing")
        _dump_page_state(driver, "seq_checkout_failed")
        print("ERROR: Could not checkout page for editing")
        sys.exit(1)
    _log.info(f"[checkout] Edit mode in {time.time() - t0:.1f}s")

    _log.info("Sorting rows...")
    sort_count = _sort_sequence_rows(driver)
    _log.info(f"Sorted {sort_count} rows")

    _log.info("Setting G-Code Tool numbers...")
    fix_count = _fix_gcode_tool_numbers(driver)
    _log.info(f"Fixed {fix_count} rows")

    t0 = time.time()
    _save_changes(driver)
    _log.info(f"[save] Completed in {time.time() - t0:.1f}s")

    print(f"OK: Sequence details updated ({sort_count} sorted, {fix_count} G-Code Tool # set)")
    sys.exit(0)


def _run_written_description(driver, args, html_content):
    """Written description mode: navigate, checkout, set CKEditor content, save."""
    customer = args.part_number.split("-")[0] if "-" in args.part_number else args.part_number
    url = (f"{BASE_URL}/procnc/parts/{customer}/{args.part_number}"
           f"$formName=writtenDescription&opId={args.op_number}")

    t0 = time.time()
    _log.info("Navigating to written description page...")
    _log.debug(f"  URL: {url}")
    _safe_navigate(driver, url)

    # Poll for CHECKOUT or SAVE button to confirm page loaded
    def _page_has_action_button(drv):
        from selenium.webdriver.common.by import By
        for btn in drv.find_elements(By.TAG_NAME, "button"):
            try:
                if btn.is_displayed():
                    txt = (btn.text or "").upper()
                    if "CHECKOUT" in txt or "SAVE" in txt:
                        return btn
            except Exception:
                pass
        return None

    action_btn = _wait_for_element(driver, _page_has_action_button, timeout=45)
    if not action_btn:
        _log.error("Page never loaded — no CHECKOUT or SAVE button found")
        _dump_page_state(driver, "wd_page_not_loaded")
        print("ERROR: Written description page never loaded")
        sys.exit(1)
    _log.info(f"[navigate] Page ready in {time.time() - t0:.1f}s")

    # ProShop may use framesets — switch to the content frame if needed
    _switch_to_editor_frame(driver)

    t0 = time.time()
    _log.info("Checking out page...")
    if not _checkout_page(driver):
        _log.error("Could not checkout written description page")
        _dump_page_state(driver, "wd_checkout_failed")
        print("ERROR: Could not checkout written description page")
        sys.exit(1)
    _log.info(f"[checkout] Edit mode in {time.time() - t0:.1f}s")

    t0 = time.time()
    _log.info("Waiting for CKEditor...")
    if not _wait_for_ckeditor(driver, timeout=30):
        _log.error("CKEditor not found or not ready after 30s")
        _dump_page_state(driver, "ckeditor_timeout")
        print("ERROR: CKEditor not found or not ready after 30s")
        sys.exit(1)
    _log.info(f"[ckeditor] Ready after {time.time() - t0:.1f}s")

    # ProShop has a ~256KB (262144 byte) server-side limit on the written
    # description field. Content exceeding this is silently discarded.
    # Warn if we're close; error if we're way over.
    MAX_CONTENT_BYTES = 250_000  # conservative limit (server cuts at ~256KB)
    content_size = len(html_content.encode("utf-8"))
    if content_size > MAX_CONTENT_BYTES:
        _log.error(f"Content too large: {content_size:,} bytes (limit ~{MAX_CONTENT_BYTES:,}). "
                   f"ProShop will silently discard the save.")
        print(f"ERROR: Content too large ({content_size:,} bytes, limit ~{MAX_CONTENT_BYTES:,}). "
              f"Reduce image quality or resolution.")
        sys.exit(1)
    elif content_size > MAX_CONTENT_BYTES * 0.9:
        _log.warning(f"Content is {content_size:,} bytes — close to the ~{MAX_CONTENT_BYTES:,} byte limit")

    t0 = time.time()
    _log.info("Setting written description content...")
    if not _set_ckeditor_content(driver, html_content):
        _log.error("Failed to set CKEditor content")
        _dump_page_state(driver, "ckeditor_content_failed")
        print("ERROR: Failed to set CKEditor content")
        sys.exit(1)
    _log.info(f"[content] Set {len(html_content)} bytes ({content_size:,} byte payload) in {time.time() - t0:.1f}s")

    # Force updateElement to ensure textarea is synced before save
    driver.execute_script("""
        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
            var names = Object.keys(CKEDITOR.instances);
            for (var i = 0; i < names.length; i++) {
                var editor = CKEDITOR.instances[names[i]];
                if (editor.updateElement) editor.updateElement();
            }
        }
    """)

    # Generate a unique marker for this push so we can verify it saved
    push_marker = f"push-{int(time.time())}"
    driver.execute_script("""
        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
            var names = Object.keys(CKEDITOR.instances);
            if (names.length > 0) {
                var editor = CKEDITOR.instances[names[0]];
                var data = editor.getData();
                // Inject hidden marker at the end
                editor.setData(data + '<!-- ' + arguments[0] + ' -->');
                if (editor.updateElement) editor.updateElement();
            }
        }
    """, push_marker)
    _log.info(f"Injected verification marker: {push_marker}")

    t0 = time.time()
    save_ok, save_msg = _save_via_fetch(driver, push_marker=push_marker)
    _log.info(f"[save] {save_msg} in {time.time() - t0:.1f}s")

    if save_ok:
        print(f"OK: Written description updated ({len(html_content)} bytes) — {save_msg}")
        sys.exit(0)
    else:
        _log.error(f"Save FAILED: {save_msg}")
        _dump_page_state(driver, "save_fetch_failed")
        print(f"ERROR: Save failed — {save_msg}")
        sys.exit(1)


def _switch_to_editor_frame(driver):
    """If page uses framesets, switch into the frame containing the editor."""
    from selenium.webdriver.common.by import By
    frames = driver.find_elements(By.TAG_NAME, "frame")
    if not frames:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    if not frames:
        _log.debug("No frames detected — page loaded directly")
        return
    _log.info(f"Frameset detected with {len(frames)} frames, searching for editor frame...")
    for i, frame in enumerate(frames):
        try:
            driver.switch_to.frame(frame)
            # Look for checkout/save buttons or CKEditor as indicators
            has_button = driver.execute_script("""
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var t = (buttons[i].textContent || '').toUpperCase();
                    if (t.indexOf('CHECKOUT') >= 0 || t.indexOf('SAVE') >= 0) return true;
                }
                return typeof CKEDITOR !== 'undefined';
            """)
            if has_button:
                _log.info(f"Switched to content frame {i}")
                return
            _log.debug(f"Frame {i}: no editor indicators, skipping")
            driver.switch_to.default_content()
        except Exception as e:
            _log.debug(f"Frame {i}: error switching — {e}")
            driver.switch_to.default_content()
    _log.warning("No editor frame found — staying on main page")


def _wait_for_ckeditor(driver, timeout=15):
    """Poll until a CKEditor instance is ready. Returns True on success."""
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
            _log.info("CKEditor is ready")
            return True
        time.sleep(0.5)
    return False


def _set_ckeditor_content(driver, html_content):
    """Set CKEditor content and ensure the underlying form element is synced.

    Uses insertHtml after selecting all to mimic user editing, which properly
    updates CKEditor's dirty state and change tracking. Falls back to setData
    if insertHtml fails.
    """
    # Step 1: Set content via CKEditor API
    result = driver.execute_script("""
        var html = arguments[0];
        if (typeof CKEDITOR === 'undefined' || !CKEDITOR.instances) return {error: 'no CKEDITOR'};
        var names = Object.keys(CKEDITOR.instances);
        if (names.length === 0) return {error: 'no instances'};
        var editor = CKEDITOR.instances[names[0]];

        // Replace all existing content with new content
        try {
            editor.focus();
            // Select all existing content
            var range = editor.createRange();
            range.selectNodeContents(editor.editable());
            editor.getSelection().selectRanges([range]);
            // Replace with new content
            editor.insertHtml(html);
        } catch(e) {
            // Fallback to setData if insertHtml fails
            editor.setData(html);
        }

        return {ok: true, editorName: names[0]};
    """, html_content)

    if not result or result.get('error'):
        _log.error(f"CKEditor set failed: {result}")
        return False

    _log.debug(f"CKEditor insertHtml OK, editor: {result.get('editorName')}")

    # Step 2: Wait for editor to process
    time.sleep(2)

    # Step 3: Sync to textarea and verify
    verify = driver.execute_script("""
        var names = Object.keys(CKEDITOR.instances);
        var editor = CKEDITOR.instances[names[0]];

        // Force sync editor content to underlying form element
        if (editor.updateElement) editor.updateElement();

        // Also fire change event for any ProShop listeners
        try { editor.fire('change'); } catch(e) {}

        var data = editor.getData();

        // Double-check: directly set textarea if updateElement didn't work
        var el = editor.element;
        var textarea = el ? el.$ : null;
        if (textarea && textarea.tagName === 'TEXTAREA') {
            if (!textarea.value || textarea.value.length === 0) {
                textarea.value = data;
                textarea.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }

        return {
            editorLen: data.length,
            textareaTag: textarea ? textarea.tagName : 'none',
            textareaLen: textarea ? textarea.value.length : -1,
            isDirty: editor.checkDirty()
        };
    """)

    ed_len = verify.get('editorLen', 0) if verify else 0
    ta_len = verify.get('textareaLen', -1) if verify else -1
    dirty = verify.get('isDirty', False) if verify else False
    _log.info(f"Content set: editor={ed_len} chars, textarea={ta_len} chars, dirty={dirty}")

    return ed_len > 0


def _safe_navigate(driver, url):
    """Navigate to a URL, handling page load timeouts gracefully.

    ProShop pages often hang on file-server resource requests.
    We catch the timeout and call window.stop() to work with
    whatever has already loaded (the HTML/form content we need
    loads early, before the slow resources).
    """
    from selenium.common.exceptions import TimeoutException
    try:
        driver.get(url)
    except TimeoutException:
        _log.warning("Page load timed out — stopping and continuing with partial load")
        try:
            driver.execute_script("window.stop()")
        except Exception:
            pass


def _find_element(driver, selectors):
    """Try multiple selectors, return first match or None."""
    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By
    for selector in selectors:
        try:
            return driver.find_element(*selector)
        except NoSuchElementException:
            continue
    return None


def _wait_for_element(driver, checker_fn, timeout=30, poll_interval=0.5):
    """Poll until checker_fn(driver) returns a truthy value, or timeout.

    Args:
        driver: Selenium WebDriver instance
        checker_fn: callable(driver) -> truthy value or None/False
        timeout: max seconds to wait
        poll_interval: seconds between polls

    Returns:
        The truthy value from checker_fn, or None on timeout.

    If a Selenium command times out during polling (e.g. page still loading),
    we call window.stop() to unblock the renderer and keep polling.
    """
    from selenium.common.exceptions import TimeoutException
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            result = checker_fn(driver)
            if result:
                return result
        except TimeoutException:
            _log.debug("Poll attempt hit TimeoutException — calling window.stop()")
            try:
                driver.execute_script("window.stop()")
            except Exception:
                pass
        except Exception as e:
            # Catches WebDriverException, urllib3 ReadTimeoutError, socket
            # TimeoutError, etc. — anything that can go wrong mid-page-load.
            last_error = e
            _log.debug(f"Poll attempt hit {type(e).__name__}: {e}")
        time.sleep(poll_interval)
    if last_error:
        _log.debug(f"_wait_for_element timed out after {timeout}s, last error: {last_error}")
    return None


def _find_seq_header(driver):
    """Find the 'Seq #' column header in the page."""
    from selenium.webdriver.common.by import By
    headers = driver.find_elements(By.TAG_NAME, "th")
    for th in headers:
        text = (th.text or "").strip()
        if "Seq" in text and "#" in text:
            return th
    return None


def _sort_sequence_rows(driver):
    """Sort table rows by Seq # ascending via JavaScript."""
    return driver.execute_script("""
        // Find the table containing "Seq #" header
        const allTh = document.querySelectorAll('th');
        let seqTh = null;
        for (const th of allTh) {
            const t = (th.textContent || '').trim();
            if (t.includes('Seq') && t.includes('#')) { seqTh = th; break; }
        }
        if (!seqTh) return 0;

        const table = seqTh.closest('table');
        if (!table) return 0;
        const tbody = table.querySelector('tbody');
        if (!tbody) return 0;

        // Find Seq # column index
        const headerRow = seqTh.closest('tr');
        let seqColIdx = 0;
        if (headerRow) {
            const ths = headerRow.querySelectorAll('th');
            for (let i = 0; i < ths.length; i++) {
                if (ths[i] === seqTh) { seqColIdx = i; break; }
            }
        }

        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
            const aCells = a.querySelectorAll('td');
            const bCells = b.querySelectorAll('td');
            const aVal = aCells.length > seqColIdx ?
                parseInt((aCells[seqColIdx].textContent || '').trim(), 10) || 9999 : 9999;
            const bVal = bCells.length > seqColIdx ?
                parseInt((bCells[seqColIdx].textContent || '').trim(), 10) || 9999 : 9999;
            return aVal - bVal;
        });

        for (const row of rows) {
            tbody.appendChild(row);
        }
        return rows.length;
    """) or 0


def _fix_gcode_tool_numbers(driver):
    """Extract T## from Sequence Description, fill G-Code Tool # fields."""
    return driver.execute_script("""
        // Find the table with "Sequence Description" and "G-Code Tool #" columns
        const allTables = document.querySelectorAll('table');
        let seqDescColIdx = -1, gcodeToolColIdx = -1, targetTable = null;

        for (const table of allTables) {
            const headerCells = table.querySelectorAll('thead th, tr:first-child th');
            seqDescColIdx = -1;
            gcodeToolColIdx = -1;
            headerCells.forEach((cell, idx) => {
                const text = (cell.textContent || '').trim().toLowerCase();
                if (text.includes('sequence description')) seqDescColIdx = idx;
                if (text.includes('g-code tool') || text.includes('gcode tool')) gcodeToolColIdx = idx;
            });
            if (seqDescColIdx >= 0 && gcodeToolColIdx >= 0) {
                targetTable = table;
                break;
            }
        }

        if (!targetTable || seqDescColIdx < 0 || gcodeToolColIdx < 0) {
            // Fallback: scan all input fields for T## pattern
            return fixGcodeToolFallback();
        }

        const tbody = targetTable.querySelector('tbody') || targetTable;
        const rows = tbody.querySelectorAll('tr');
        let fixCount = 0;

        for (const row of rows) {
            const cells = row.querySelectorAll('td');
            if (cells.length <= Math.max(seqDescColIdx, gcodeToolColIdx)) continue;

            const descCell = cells[seqDescColIdx];
            const gcodeCell = cells[gcodeToolColIdx];
            const descInput = descCell.querySelector('input, textarea');
            const gcodeInput = gcodeCell.querySelector('input, textarea');
            const descVal = descInput ? (descInput.value || '') : (descCell.textContent || '').trim();
            const match = descVal.match(/^T(\\d+):\\s*/);

            if (match) {
                const toolNum = match[1];
                const cleanDesc = descVal.replace(/^T\\d+:\\s*/, '');

                // Set G-Code Tool # (overwrite — Fusion data is authoritative)
                if (gcodeInput) {
                    gcodeInput.value = toolNum;
                    gcodeInput.dispatchEvent(new Event('input', { bubbles: true }));
                    gcodeInput.dispatchEvent(new Event('change', { bubbles: true }));
                }

                // Clean description
                if (descInput && descInput.value !== cleanDesc) {
                    descInput.value = cleanDesc;
                    descInput.dispatchEvent(new Event('input', { bubbles: true }));
                    descInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
                fixCount++;
            }
        }
        return fixCount;

        function fixGcodeToolFallback() {
            // Scan all visible input fields for T## pattern in descriptions
            const allInputs = document.querySelectorAll('input[type="text"], textarea');
            let count = 0;
            for (let i = 0; i < allInputs.length; i++) {
                const inp = allInputs[i];
                const val = inp.value || '';
                const m = val.match(/^T(\\d+):\\s*/);
                if (m) {
                    const toolNum = m[1];
                    const cleanVal = val.replace(/^T\\d+:\\s*/, '');
                    inp.value = cleanVal;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                    // Try to find the G-Code Tool # input nearby
                    const row = inp.closest('tr');
                    if (row) {
                        const inputs = row.querySelectorAll('input[type="text"]');
                        for (const other of inputs) {
                            if (other !== inp && !(other.value || '').trim()) {
                                other.value = toolNum;
                                other.dispatchEvent(new Event('input', { bubbles: true }));
                                other.dispatchEvent(new Event('change', { bubbles: true }));
                                break;
                            }
                        }
                    }
                    count++;
                }
            }
            return count;
        }
    """) or 0


def _checkout_page(driver):
    """Click the CHECKOUT button to enable editing. Returns True on success.

    After clicking, polls for the SAVE button to appear (edit mode) instead
    of using fixed sleeps. If the click triggers a page reload timeout,
    window.stop() is called to unblock the renderer — the edit-mode form
    loads before the slow file-server resources.
    """
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import TimeoutException

    def _find_save_button(drv):
        """Check if a visible SAVE button exists (indicating edit mode)."""
        for btn in drv.find_elements(By.TAG_NAME, "button"):
            try:
                if btn.is_displayed() and "SAVE" in (btn.text or "").upper():
                    return True
            except Exception:
                pass
        return None

    # Already in edit mode?
    if _find_save_button(driver):
        _log.info("Already in edit mode (SAVE button present)")
        return True

    # Find and click CHECKOUT
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
        _log.warning("No CHECKOUT button found on page")
        return False

    _log.debug(f"Clicking checkout button via JS: '{checkout_btn.text.strip()}'")
    # setTimeout(0) schedules the click on the next event loop tick,
    # so execute_script returns before the click triggers page navigation.
    driver.execute_script("var el = arguments[0]; setTimeout(function(){ el.click(); }, 0)", checkout_btn)

    # Poll for SAVE button to appear (edit mode activated)
    save_found = _wait_for_element(driver, _find_save_button, timeout=45)
    if save_found:
        _log.info("Page checked out — edit mode active (SAVE button found)")
        return True

    _log.warning("Checkout clicked but SAVE button never appeared after 45s")
    return False


def _save_changes(driver):
    """Click the SAVE CHANGES button via JavaScript and return immediately.

    Fire-and-forget save used by sequence-detail mode. For written descriptions,
    use _save_via_fetch() instead which gives a verifiable response.

    JS click fires the event and returns instantly. The caller is responsible
    for polling to verify the save completed (e.g., CHECKOUT button reappears).
    """
    from selenium.webdriver.common.by import By

    _log.info("Looking for Save button...")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    save_btn = None
    for btn in buttons:
        try:
            if btn.is_displayed():
                txt = (btn.text or "").strip().upper()
                if "SAVE" in txt:
                    save_btn = btn
                    break
        except Exception:
            pass

    if not save_btn:
        _log.warning("No visible Save button found — changes may need manual save")
        return

    _log.debug(f"Clicking save button via JS: '{save_btn.text.strip()}'")
    driver.execute_script("var el = arguments[0]; setTimeout(function(){ el.click(); }, 0)", save_btn)
    _log.info("Save button clicked via JS — form submission initiated")


def _save_via_fetch(driver, push_marker=None, timeout=180):
    """Submit the form via fetch() API and wait for a verified server response.

    Instead of clicking SAVE (which triggers a page reload Selenium can't wait
    for), this extracts the form data and sends it via fetch(). This gives us:
      - A real HTTP status code (200 = success)
      - The response body (to verify our content was saved)
      - No page reload (browser stays stable for Selenium)

    Args:
        driver: Selenium WebDriver
        push_marker: Optional marker string to look for in the response body
        timeout: Max seconds to wait for the server response

    Returns:
        (ok: bool, message: str) tuple
    """
    _log.info("Saving via fetch() — submitting form data to server...")

    # Intercept the form submit and send via fetch() instead of navigating.
    #
    # ProShop has JavaScript handlers on both the save button (click) and the
    # form (submit) that do preprocessing. We must let those handlers run,
    # then intercept the final submission and send via fetch() to get a
    # verifiable response without triggering a page navigation.
    #
    # Flow: sync CKEditor → install submit interceptor → requestSubmit(saveBtn)
    #   → ProShop's click/submit handlers run → our interceptor fires →
    #   preventDefault → fetch() with final FormData → poll for result.
    driver.execute_script("""
        window.__fetchResult = null;
        var marker = arguments[0] || null;

        // Sync all CKEditor instances to their textareas
        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
            var names = Object.keys(CKEDITOR.instances);
            for (var i = 0; i < names.length; i++) {
                var ed = CKEDITOR.instances[names[i]];
                if (ed.updateElement) ed.updateElement();
            }
        }

        var form = document.getElementById('mainEditingForm');
        if (!form) {
            var btns = document.querySelectorAll('button');
            for (var j = 0; j < btns.length; j++) {
                if (btns[j].offsetParent !== null &&
                    (btns[j].textContent || '').toUpperCase().indexOf('SAVE') >= 0) {
                    form = btns[j].closest('form');
                    break;
                }
            }
        }

        if (!form) {
            window.__fetchResult = {error: 'no form found'};
            return;
        }

        var saveBtn = form.querySelector('button[name="_submitChanges_"]');
        if (!saveBtn) {
            window.__fetchResult = {error: 'no save button found'};
            return;
        }

        // Install a submit interceptor that fires AFTER ProShop's own handlers.
        // We use addEventListener (not onsubmit) so we don't overwrite ProShop's handler.
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            e.stopImmediatePropagation();

            // Capture the final form state (after ProShop's handlers may have modified it)
            var formData = new FormData(form);
            // Include the submit button's name/value (browsers do this for the clicked button)
            formData.append(saveBtn.name, saveBtn.value);

            var actionUrl = form.action || window.location.href;

            var totalLen = 0;
            for (var pair of formData.entries()) {
                totalLen += (pair[1] + '').length;
            }
            window.__fetchPayloadSize = totalLen;

            var startTime = Date.now();
            fetch(actionUrl, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            }).then(function(resp) {
                var elapsed = Date.now() - startTime;
                resp.text().then(function(body) {
                    window.__fetchResult = {
                        status: resp.status,
                        statusText: resp.statusText,
                        elapsed_ms: elapsed,
                        ok: resp.ok,
                        bodyLen: body.length,
                        bodyTitle: (body.match(/<title>(.*?)<\\/title>/i) || [])[1] || '',
                        hasMarker: marker ? body.indexOf(marker) >= 0 : null
                    };
                });
            }).catch(function(err) {
                window.__fetchResult = {
                    error: err.message,
                    elapsed_ms: Date.now() - startTime
                };
            });
        }, false);  // false = bubble phase, fires after ProShop's capture-phase handlers

        // Trigger the full native form submission flow.
        // requestSubmit(saveBtn) fires the button's click handler, then the form's
        // submit event (including ProShop's handler and our interceptor).
        form.requestSubmit(saveBtn);
    """, push_marker or "")

    payload_size = driver.execute_script("return window.__fetchPayloadSize;") or 0
    _log.info(f"fetch() initiated — payload ~{payload_size} chars")

    # Poll for the result
    poll_start = time.time()
    while time.time() - poll_start < timeout:
        try:
            result = driver.execute_script("return window.__fetchResult;")
            if result is not None:
                break
        except Exception as e:
            _log.debug(f"Poll error: {e}")

        elapsed = int(time.time() - poll_start)
        if elapsed > 0 and elapsed % 30 == 0:
            _log.info(f"Still waiting for server response... ({elapsed}s)")
        time.sleep(2)
    else:
        _log.error(f"fetch() timed out after {timeout}s — no server response")
        return False, f"Save timed out after {timeout}s"

    # Analyze the result
    elapsed_s = result.get('elapsed_ms', 0) / 1000
    if result.get('error'):
        _log.error(f"fetch() failed: {result['error']} ({elapsed_s:.1f}s)")
        return False, f"fetch error: {result['error']}"

    status = result.get('status', 0)
    ok = result.get('ok', False)
    body_len = result.get('bodyLen', 0)
    title = result.get('statusText', '')

    _log.info(f"Server response: {status} {title} in {elapsed_s:.1f}s ({body_len} chars)")

    if not ok:
        _log.error(f"Server returned HTTP {status}")
        return False, f"Server returned HTTP {status}"

    # Verify marker if provided
    if push_marker:
        has_marker = result.get('hasMarker', False)
        if has_marker:
            _log.info(f"Verification marker '{push_marker}' found in response")
        else:
            _log.error(f"Verification marker '{push_marker}' NOT found in response — "
                       f"content was likely discarded (payload may exceed server limit)")
            return False, (f"Save not verified — marker not in response "
                           f"(HTTP {status}, {body_len} chars)")

    return True, f"HTTP {status} in {elapsed_s:.1f}s ({body_len} chars)"


if __name__ == "__main__":
    main()
