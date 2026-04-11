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

Version: 2.0
"""

import sys
import os
import time
import argparse

BASE_URL = "https://traxismfg.adionsystems.com"


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


def status(msg):
    """Print a status message (read by parent process)."""
    print(f"STATUS: {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="ProShop Selenium helper for sequence detail and written description pages")
    parser.add_argument("--mode", default="sequence-detail",
                        choices=["sequence-detail", "written-description"],
                        help="Which page to automate")
    parser.add_argument("--part-number", required=True, help="Part number (e.g., TRA1-10983)")
    parser.add_argument("--op-number", required=True, help="Operation number (e.g., 60)")
    parser.add_argument("--visible", action="store_true", help="Show browser window (for debugging)")
    args = parser.parse_args()

    # For written-description mode, read HTML from stdin
    html_content = None
    if args.mode == "written-description":
        html_content = sys.stdin.read()
        if not html_content.strip():
            print("ERROR: No HTML content provided on stdin")
            sys.exit(1)
        status(f"Read {len(html_content)} bytes of HTML from stdin")

    driver = _setup_and_login(args)
    try:
        if args.mode == "sequence-detail":
            _run_sequence_detail(driver, args)
        elif args.mode == "written-description":
            _run_written_description(driver, args, html_content)
    except Exception as e:
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
        print("ERROR: PROSHOP_USERNAME or PROSHOP_PASSWORD not found in ~/.traxis.env")
        sys.exit(1)

    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
    except ImportError:
        print("ERROR: selenium not installed. Run: pip install selenium")
        sys.exit(1)

    options = webdriver.ChromeOptions()
    if not args.visible:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")

    status("Launching Chrome...")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)

    # Login
    status("Logging in...")
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
        driver.quit()
        print("ERROR: Could not find login button")
        sys.exit(1)

    submit_btn.click()
    time.sleep(3)

    page_source = driver.page_source.lower()
    if "invalid" in page_source or "incorrect" in page_source:
        driver.quit()
        print("ERROR: Login failed — invalid credentials")
        sys.exit(1)

    status("Login successful")
    return driver


def _run_sequence_detail(driver, args):
    """Sequence detail mode: sort rows, fix G-Code Tool #, save."""
    customer = args.part_number.split("-")[0] if "-" in args.part_number else args.part_number
    url = (f"{BASE_URL}/procnc/parts/{customer}/{args.part_number}"
           f"?formName=toolDetail&opId={args.op_number}")
    status("Navigating to sequence details...")
    _safe_navigate(driver, url)
    time.sleep(2)

    seq_header = _find_seq_header(driver)
    if not seq_header:
        url2 = (f"{BASE_URL}/procnc/parts/{args.part_number}/{args.part_number}"
                f"?formName=toolDetail&opId={args.op_number}")
        status("Trying alternate URL...")
        _safe_navigate(driver, url2)
        time.sleep(2)
        seq_header = _find_seq_header(driver)

    if not seq_header:
        print("ERROR: Could not find sequence detail table (no 'Seq #' header found)")
        sys.exit(1)

    status("Found sequence detail table")

    status("Checking out page...")
    if not _checkout_page(driver):
        print("ERROR: Could not checkout page for editing")
        sys.exit(1)
    time.sleep(2)

    status("Sorting rows...")
    sort_count = _sort_sequence_rows(driver)
    status(f"Sorted {sort_count} rows")

    time.sleep(1)
    status("Setting G-Code Tool numbers...")
    fix_count = _fix_gcode_tool_numbers(driver)
    status(f"Fixed {fix_count} rows")

    time.sleep(1)
    _save_changes(driver)

    print(f"OK: Sequence details updated ({sort_count} sorted, {fix_count} G-Code Tool # set)")
    sys.exit(0)


def _run_written_description(driver, args, html_content):
    """Written description mode: navigate, checkout, set CKEditor content, save."""
    customer = args.part_number.split("-")[0] if "-" in args.part_number else args.part_number
    url = (f"{BASE_URL}/procnc/parts/{customer}/{args.part_number}"
           f"?formName=writtenDescription&opId={args.op_number}")
    status("Navigating to written description page...")
    _safe_navigate(driver, url)
    time.sleep(3)

    # ProShop may use framesets — switch to the content frame if needed
    _switch_to_editor_frame(driver)

    status("Checking out page...")
    if not _checkout_page(driver):
        print("ERROR: Could not checkout written description page")
        sys.exit(1)
    time.sleep(3)

    status("Waiting for CKEditor...")
    if not _wait_for_ckeditor(driver, timeout=15):
        print("ERROR: CKEditor not found or not ready after 15s")
        sys.exit(1)

    status("Setting written description content...")
    if not _set_ckeditor_content(driver, html_content):
        print("ERROR: Failed to set CKEditor content")
        sys.exit(1)

    time.sleep(1)
    _save_changes(driver)

    # Verify by checking editor still has content after save
    time.sleep(2)
    verify = driver.execute_script("""
        if (typeof CKEDITOR === 'undefined' || !CKEDITOR.instances) return 0;
        var names = Object.keys(CKEDITOR.instances);
        if (names.length === 0) return 0;
        return CKEDITOR.instances[names[0]].getData().length;
    """) or 0
    status(f"Post-save verification: editor has {verify} chars")

    print(f"OK: Written description updated ({len(html_content)} bytes)")
    sys.exit(0)


def _switch_to_editor_frame(driver):
    """If page uses framesets, switch into the frame containing the editor."""
    from selenium.webdriver.common.by import By
    frames = driver.find_elements(By.TAG_NAME, "frame")
    if not frames:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    if not frames:
        return  # No frames — page loaded directly
    status(f"Frameset detected with {len(frames)} frames, searching for editor frame...")
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
                status(f"Switched to content frame {i}")
                return
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
    status("No editor frame found — staying on main page")


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
            status("CKEditor is ready")
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

        // Get existing content to prepend new content before it
        var existing = editor.getData() || '';
        var combined = html + (existing ? '<hr>' + existing : '');

        // Use insertHtml with select-all to simulate user editing
        try {
            editor.focus();
            // Select all existing content
            var range = editor.createRange();
            range.selectNodeContents(editor.editable());
            editor.getSelection().selectRanges([range]);
            // Replace with new content
            editor.insertHtml(combined);
        } catch(e) {
            // Fallback to setData if insertHtml fails
            editor.setData(combined);
        }

        return {ok: true, editorName: names[0]};
    """, html_content)

    if not result or result.get('error'):
        status(f"CKEditor set failed: {result}")
        return False

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
    status(f"Content set: editor={ed_len} chars, textarea={ta_len} chars, dirty={dirty}")

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
        status("Page load timed out — stopping and continuing with partial load")
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
    """Click the CHECKOUT button to enable editing. Returns True on success."""
    from selenium.webdriver.common.by import By
    buttons = driver.find_elements(By.TAG_NAME, "button")
    for btn in buttons:
        if btn.is_displayed():
            txt = (btn.text or "").strip().upper()
            if "CHECKOUT" in txt and "RECONCILE" not in txt:
                btn.click()
                time.sleep(3)
                # Verify we're now in edit mode (SAVE CHANGES button should appear)
                buttons2 = driver.find_elements(By.TAG_NAME, "button")
                for b2 in buttons2:
                    if b2.is_displayed() and "SAVE" in (b2.text or "").upper():
                        status("Page checked out — edit mode active")
                        return True
                status("Checkout clicked but SAVE button not found")
                return False
    status("No CHECKOUT button found — page may already be checked out")
    # Check if already in edit mode
    buttons2 = driver.find_elements(By.TAG_NAME, "button")
    for b2 in buttons2:
        if b2.is_displayed() and "SAVE" in (b2.text or "").upper():
            return True
    return False


def _save_changes(driver):
    """Click the SAVE CHANGES button (visible after checkout)."""
    from selenium.webdriver.common.by import By
    status("Looking for Save button...")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    for btn in buttons:
        if btn.is_displayed():
            txt = (btn.text or "").strip().upper()
            if "SAVE" in txt:
                btn.click()
                time.sleep(3)
                status("Saved changes")
                return
    status("No visible Save button found — changes may need manual save")


if __name__ == "__main__":
    main()
