"""Inspect a ProShop User page to discover where HR write-ups should land.

Mirrors inspect_upload.py: launches Chrome in VISIBLE mode, logs in, and walks
the User profile's sub-form navigation. For each $formName=... it visits, it
reports:
  - whether the form has a CKEditor instance (→ candidate for the P31
    base64-image insertion path)
  - whether the form has a real file <input type="file"> (→ candidate for a
    different upload path, not currently in P31's worker)
  - what CHECKOUT/SAVE controls are visible

Outputs:
  - data/logs/inspect_user_<id>_<form>_<ts>.png   one screenshot per form
  - data/logs/inspect_user_<id>_<ts>.json         machine-readable summary
  - inspect_user_page.log                         human-readable trace

Usage:
    python inspect_user_page.py --user 026
    python inspect_user_page.py --user 026 --keep-open

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
        logging.FileHandler(config.LOGS_DIR / "inspect_user_page.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("inspect-user")


# Forms to probe. Empty string = the user page's default landing form.
# Educated guesses from the schema (UserFileStorage, writtenDescription,
# messageinbox confirmed in session log). The script will also extract the
# real list of available forms from the side nav once the page loads, so
# unknown forms get covered too.
CANDIDATE_FORMS = [
    "",  # default landing
    "writtenDescription",
    "fileStorage",
    "userFileStorage",
    "files",
    "messageinbox",
    "hrnotes",
    "personalInfo",
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


def _probe_form(driver, user_id, form_name, screenshot_dir):
    """Visit a sub-form and report what's on it."""
    from selenium.webdriver.common.by import By

    if form_name:
        url = f"{BASE_URL}/procnc/users/{user_id}$formName={quote(form_name)}"
    else:
        url = f"{BASE_URL}/procnc/users/{user_id}"

    log.info(f"Probing form='{form_name or '(default)'}' → {url}")
    _safe_navigate(driver, url)
    time.sleep(2)

    # Try frame switching like the worker does
    try:
        from selenium.common.exceptions import NoSuchElementException
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
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
    except Exception as e:
        log.debug(f"Frame probe error: {e}")

    summary = driver.execute_script("""
        function visible(el) {
            if (!el) return false;
            var s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            return el.offsetParent !== null || el.tagName === 'INPUT';
        }

        var ck_count = 0;
        var ck_names = [];
        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
            ck_names = Object.keys(CKEDITOR.instances);
            ck_count = ck_names.length;
        }

        var file_inputs = [];
        document.querySelectorAll('input[type=file]').forEach(function(el) {
            file_inputs.push({
                name: el.name || '',
                id: el.id || '',
                accept: el.accept || '',
                visible: visible(el)
            });
        });

        var buttons = [];
        document.querySelectorAll('button, input[type=submit]').forEach(function(el) {
            if (visible(el)) {
                var t = (el.textContent || el.value || '').trim();
                if (t) buttons.push(t.substring(0, 40));
            }
        });

        // Side-nav links — these reveal the real $formName= options
        var nav_forms = [];
        document.querySelectorAll('a[href*=\"$formName=\"]').forEach(function(el) {
            var href = el.getAttribute('href') || '';
            var match = href.match(/\\$formName=([^&]+)/);
            if (match) nav_forms.push({form: match[1], text: (el.textContent||'').trim().substring(0, 40)});
        });

        return {
            url: window.location.href,
            title: document.title,
            ckeditor_count: ck_count,
            ckeditor_names: ck_names,
            file_input_count: file_inputs.length,
            file_inputs: file_inputs,
            visible_buttons: buttons.slice(0, 30),
            sidebar_forms: nav_forms.slice(0, 50)
        };
    """)

    safe_form = (form_name or "default").replace("/", "_")
    ts = time.strftime("%Y%m%d_%H%M%S")
    shot = screenshot_dir / f"inspect_user_{user_id}_{safe_form}_{ts}.png"
    try:
        driver.save_screenshot(str(shot))
        summary["screenshot"] = str(shot.name)
    except Exception as e:
        log.debug(f"Screenshot error: {e}")

    log.info(
        f"  → CKEditors: {summary['ckeditor_count']}  "
        f"file inputs: {summary['file_input_count']}  "
        f"buttons: {len(summary['visible_buttons'])}"
    )
    if summary["ckeditor_names"]:
        log.info(f"  → CKEditor instances: {summary['ckeditor_names']}")
    if summary["file_inputs"]:
        log.info(f"  → File inputs: {summary['file_inputs']}")

    driver.switch_to.default_content()
    return summary


def main():
    parser = argparse.ArgumentParser(description="Inspect ProShop User profile sub-forms")
    parser.add_argument("--user", required=True, help="ProShop user ID, e.g. 026")
    parser.add_argument("--keep-open", action="store_true",
                        help="Don't close the browser after inspection")
    args = parser.parse_args()

    user_id = args.user.strip()

    username = config.PROSHOP_USERNAME
    password = config.PROSHOP_PASSWORD
    if not username or not password:
        log.error("PROSHOP_USERNAME / PROSHOP_PASSWORD not set in .traxis.env")
        sys.exit(1)

    try:
        from selenium import webdriver
    except ImportError:
        log.error("selenium not installed: pip install selenium webdriver-manager")
        sys.exit(1)

    options = webdriver.ChromeOptions()
    # Visible mode — we want to see what the page looks like
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--disable-gpu")

    log.info("Launching Chrome (visible)...")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(20)

    try:
        if not _login(driver, username, password):
            log.error("Login failed — aborting")
            return 1

        # First visit the default user page to discover the real sidebar forms
        log.info("=" * 60)
        log.info("Phase 1 — discover side-nav forms from default user page")
        log.info("=" * 60)
        default_summary = _probe_form(driver, user_id, "", config.LOGS_DIR)

        discovered_forms = sorted({
            entry["form"] for entry in default_summary.get("sidebar_forms", [])
        })
        log.info(f"Sidebar surfaced {len(discovered_forms)} distinct form names: "
                 f"{discovered_forms}")

        # Probe candidates + anything new the sidebar revealed
        forms_to_probe = []
        seen = set()
        for f in CANDIDATE_FORMS + discovered_forms:
            key = f.lower()
            if key in seen:
                continue
            seen.add(key)
            if f == "":
                continue  # already done as Phase 1
            forms_to_probe.append(f)

        log.info("=" * 60)
        log.info(f"Phase 2 — probing {len(forms_to_probe)} sub-forms")
        log.info("=" * 60)

        all_summaries = {"(default)": default_summary}
        for form_name in forms_to_probe:
            try:
                summary = _probe_form(driver, user_id, form_name, config.LOGS_DIR)
                all_summaries[form_name] = summary
            except Exception as e:
                log.error(f"Form {form_name} probe failed: {e}")
                all_summaries[form_name] = {"error": str(e)}

        # Verdict
        log.info("=" * 60)
        log.info("Verdict")
        log.info("=" * 60)
        ckeditor_forms = [k for k, v in all_summaries.items()
                          if isinstance(v, dict) and v.get("ckeditor_count", 0) > 0]
        file_input_forms = [k for k, v in all_summaries.items()
                            if isinstance(v, dict) and v.get("file_input_count", 0) > 0]
        log.info(f"Forms with CKEditor (P31 base64-image path works): {ckeditor_forms}")
        log.info(f"Forms with real file inputs (different upload path): {file_input_forms}")

        ts = time.strftime("%Y%m%d_%H%M%S")
        out = config.LOGS_DIR / f"inspect_user_{user_id}_{ts}.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump({
                "user_id": user_id,
                "ckeditor_forms": ckeditor_forms,
                "file_input_forms": file_input_forms,
                "forms": all_summaries,
            }, f, indent=2)
        log.info(f"Full report: {out}")

        if args.keep_open:
            log.info("Browser kept open — close manually when done")
            input("Press Enter to close browser... ")

    finally:
        if not args.keep_open:
            try:
                driver.quit()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
