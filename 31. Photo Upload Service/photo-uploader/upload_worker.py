"""Photo Upload Service — Background Selenium upload worker.

Picks up pending photos from SQLite, launches a Chrome browser, logs into
ProShop, navigates to the WO operation's written description page, and
uploads the photo via CKEditor's image upload dialog.

Browser lifecycle:
  - Lazy-launched on first pending photo
  - Kept alive between uploads (avoids re-login overhead)
  - Closed after BROWSER_IDLE_TIMEOUT seconds with no pending work

Retry policy:
  - MAX_RETRIES attempts per photo (default 3)
  - Backoff delays: 1 min, 5 min, 15 min

Screenshots on failure saved to data/logs/
"""

import logging
import os
import threading
import time
from pathlib import Path

import config
import database
from proshop_client import ProShopClient

log = logging.getLogger("photo-uploader.worker")

BASE_URL = "https://traxismfg.adionsystems.com"
BROWSER_IDLE_TIMEOUT = 120  # seconds — close browser after 2 min idle


class UploadWorker:
    """Background thread that uploads queued photos to ProShop via Selenium."""

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._driver = None
        self._driver_lock = threading.Lock()
        self._last_activity = 0
        self._proshop = ProShopClient()

    # ── Thread lifecycle ─────────────────────────────────────────────────

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="upload-worker")
        self._thread.start()
        log.info("Upload worker started (Phase 2 — Selenium upload)")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._close_browser()

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._process_queue()
            except Exception as e:
                log.error(f"Worker loop error: {e}", exc_info=True)

            # Close browser if idle too long
            if self._driver and (time.time() - self._last_activity) > BROWSER_IDLE_TIMEOUT:
                log.info("Browser idle timeout — closing")
                self._close_browser()

            self._stop_event.wait(config.UPLOAD_CHECK_INTERVAL)

    # ── Browser lifecycle ────────────────────────────────────────────────

    def _ensure_browser(self):
        """Lazy-launch Chrome and log into ProShop. Reuses existing session."""
        with self._driver_lock:
            if self._driver:
                # Verify browser is still alive
                try:
                    _ = self._driver.title
                    return True
                except Exception:
                    log.warning("Browser session dead — relaunching")
                    self._close_browser_unlocked()

            username = config.PROSHOP_USERNAME
            password = config.PROSHOP_PASSWORD
            if not username or not password:
                log.error("PROSHOP_USERNAME or PROSHOP_PASSWORD not configured")
                return False

            try:
                from selenium import webdriver
                from selenium.webdriver.common.by import By
                from selenium.common.exceptions import NoSuchElementException
            except ImportError:
                log.error("selenium not installed — run: pip install selenium webdriver-manager")
                return False

            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")

            log.info("Launching Chrome (headless)...")
            t0 = time.time()
            try:
                driver = webdriver.Chrome(options=options)
            except Exception as e:
                log.error(f"Chrome launch failed: {e}")
                return False

            driver.set_page_load_timeout(20)
            log.info(f"Chrome launched in {time.time() - t0:.1f}s")

            # Login
            log.info("Logging into ProShop...")
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
                log.error("Could not find login form fields")
                _save_screenshot(driver, "login_form_not_found")
                driver.quit()
                return False

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
                log.error("Could not find login button")
                _save_screenshot(driver, "login_button_not_found")
                driver.quit()
                return False

            submit_btn.click()
            time.sleep(3)

            page_source = driver.page_source.lower()
            if "invalid" in page_source or "incorrect" in page_source:
                log.error("Login failed — invalid credentials")
                _save_screenshot(driver, "login_failed")
                driver.quit()
                return False

            log.info(f"ProShop login successful ({time.time() - t0:.1f}s total)")
            self._driver = driver
            self._last_activity = time.time()
            return True

    def _close_browser(self):
        with self._driver_lock:
            self._close_browser_unlocked()

    def _close_browser_unlocked(self):
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ── Queue processing ─────────────────────────────────────────────────

    def _process_queue(self):
        """Fetch pending photos and upload each one."""
        pending = database.get_pending_photos(limit=5)
        if not pending:
            return

        # Check retry delays — skip photos that aren't ready for retry yet
        ready = []
        for photo in pending:
            retry_count = photo.get("retry_count", 0)
            if retry_count > 0 and retry_count <= len(config.RETRY_DELAYS):
                delay = config.RETRY_DELAYS[retry_count - 1]
                updated = photo.get("updated_at", "")
                if updated:
                    try:
                        from datetime import datetime, timezone
                        updated_dt = datetime.fromisoformat(updated)
                        elapsed = (datetime.now(timezone.utc) - updated_dt).total_seconds()
                        if elapsed < delay:
                            log.debug(
                                f"Photo #{photo['id']}: retry {retry_count} — "
                                f"waiting {delay - elapsed:.0f}s more"
                            )
                            continue
                    except Exception:
                        pass
            ready.append(photo)

        if not ready:
            return

        log.info(f"Processing {len(ready)} photo(s) from queue")

        # Ensure browser is ready
        if not self._ensure_browser():
            log.error("Cannot launch browser — skipping this cycle")
            return

        for photo in ready:
            if self._stop_event.is_set():
                break
            try:
                self._upload_photo(photo)
                self._last_activity = time.time()
            except Exception as e:
                log.error(f"Photo #{photo['id']} upload error: {e}", exc_info=True)
                database.update_photo_status(photo["id"], "failed", str(e))
                database.increment_retry(photo["id"])
                if self._driver:
                    _save_screenshot(self._driver, f"photo_{photo['id']}_error")

    # ── Single photo upload ──────────────────────────────────────────────

    def _upload_photo(self, photo):
        """Upload a single photo to ProShop's written description via CKEditor.

        For work order photos: navigates to the WO operation's written description,
        checks out the page, opens the CKEditor image dialog, uploads the file
        via the Upload tab (file input is inside a dialog iframe), and saves.

        DOM structure (verified via inspect_upload.py):
          - Dialog: name="image", title="Image Properties"
          - Tabs: Image Info | Link | Upload | Advanced
          - Upload tab: file input inside an iframe (name="upload")
          - "Send it to the Server" button: <a> tag with class cke_dialog_ui_button
          - Dialog buttons: OK and Cancel via dialog.getButton('ok'/'cancel')
        """
        photo_id = photo["id"]
        entity_type = photo["entity_type"]
        entity_id = photo["entity_id"]
        op_number = photo.get("operation_number", "")

        log.info(f"Uploading photo #{photo_id}: {entity_type}/{entity_id} op={op_number}")
        database.update_photo_status(photo_id, "uploading")

        # Only work order photos have a clear upload destination
        if entity_type != "workorder":
            msg = f"Upload for entity type '{entity_type}' not yet implemented"
            log.warning(f"Photo #{photo_id}: {msg}")
            database.update_photo_status(photo_id, "failed", msg)
            return

        if not op_number:
            msg = "No operation number — cannot determine upload destination"
            log.warning(f"Photo #{photo_id}: {msg}")
            database.update_photo_status(photo_id, "failed", msg)
            return

        # Look up part number from WO
        detail = self._proshop.get_work_order_detail(entity_id)
        if not detail:
            msg = f"Work order {entity_id} not found via API"
            log.error(f"Photo #{photo_id}: {msg}")
            database.update_photo_status(photo_id, "failed", msg)
            database.increment_retry(photo_id)
            return

        part_number = detail["partNumber"]
        customer = detail["customerName"]

        # Build written description URL
        url = (f"{BASE_URL}/procnc/parts/{customer}/{part_number}"
               f"$formName=writtenDescription&opId={op_number}")

        # Resolve photo file path
        file_path = Path(config.DATA_DIR) / photo["file_path"]
        if not file_path.exists():
            msg = f"Photo file not found: {file_path}"
            log.error(f"Photo #{photo_id}: {msg}")
            database.update_photo_status(photo_id, "failed", msg)
            return

        driver = self._driver
        from selenium.webdriver.common.by import By

        # Navigate to written description page
        log.info(f"Photo #{photo_id}: navigating to {url}")
        _safe_navigate(driver, url)

        # Wait for page (CHECKOUT or SAVE button)
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

        action_btn = _wait_for_element(driver, _page_has_action_button, timeout=45)
        if not action_btn:
            msg = "Written description page did not load (no CHECKOUT/SAVE)"
            log.error(f"Photo #{photo_id}: {msg}")
            _save_screenshot(driver, f"photo_{photo_id}_page_not_loaded")
            database.update_photo_status(photo_id, "failed", msg)
            database.increment_retry(photo_id)
            return

        # Switch to editor frame if page uses framesets
        _switch_to_editor_frame(driver)

        # Checkout page
        if not _checkout_page(driver):
            msg = "Could not checkout written description page"
            log.error(f"Photo #{photo_id}: {msg}")
            _save_screenshot(driver, f"photo_{photo_id}_checkout_failed")
            database.update_photo_status(photo_id, "failed", msg)
            database.increment_retry(photo_id)
            return

        # Wait for CKEditor
        if not _wait_for_ckeditor(driver, timeout=30):
            msg = "CKEditor not ready after 30s"
            log.error(f"Photo #{photo_id}: {msg}")
            _save_screenshot(driver, f"photo_{photo_id}_ckeditor_timeout")
            database.update_photo_status(photo_id, "failed", msg)
            database.increment_retry(photo_id)
            return

        # ── Insert image via base64 inline ──────────────────────────────
        # ProShop's CKEditor has no filebrowserImageUploadUrl configured,
        # so the Upload tab's "Send it to the Server" has no server endpoint.
        # Verified via DOM inspection: the upload form posts to the page URL
        # which doesn't handle file uploads. Instead, we insert the image
        # directly as a base64 data URI into the editor content.
        log.info(f"Photo #{photo_id}: inserting image via base64 inline")
        success = self._insert_image_html_fallback(driver, photo, file_path)

        if not success:
            msg = "Base64 image insert failed"
            log.error(f"Photo #{photo_id}: {msg}")
            _save_screenshot(driver, f"photo_{photo_id}_insert_failed")
            database.update_photo_status(photo_id, "failed", msg)
            database.increment_retry(photo_id)
            return

        database.update_photo_status(photo_id, "uploaded")
        log.info(f"Photo #{photo_id}: successfully uploaded to ProShop")

    def _close_dialog(self, driver):
        """Close any open CKEditor dialog."""
        driver.execute_script("""
            try {
                var dialog = CKEDITOR.dialog.getCurrent();
                if (dialog) dialog.hide();
            } catch(e) {}
        """)
        time.sleep(0.5)

    def _insert_image_html_fallback(self, driver, photo, file_path):
        """Insert image as base64 data URI into CKEditor and save.

        ProShop's CKEditor has no filebrowserImageUploadUrl configured,
        so we embed the image directly as a base64 data URI. ProShop has a
        ~256KB server-side limit on written descriptions, so we resize the
        image to fit within budget.

        Uses insertHtml (not setData) to properly mark editor dirty — same
        approach as ProShop Bridge's _set_ckeditor_content.
        """
        import base64
        from PIL import Image
        import io

        photo_id = photo["id"]
        MAX_CONTENT_BYTES = 240_000  # ProShop's server-side limit is ~256KB

        try:
            # Get existing content size to calculate budget
            existing_size = driver.execute_script("""
                if (typeof CKEDITOR === 'undefined' || !CKEDITOR.instances) return -1;
                var names = Object.keys(CKEDITOR.instances);
                if (names.length === 0) return -1;
                return CKEDITOR.instances[names[0]].getData().length;
            """)
            if existing_size < 0:
                existing_size = 0
            budget = MAX_CONTENT_BYTES - existing_size - 200  # 200 for <p><img> wrapper
            log.info(f"Photo #{photo_id}: existing content {existing_size} chars, "
                     f"image budget {budget} chars")

            if budget < 5000:
                log.error(f"Photo #{photo_id}: not enough space — existing content "
                          f"uses {existing_size} of {MAX_CONTENT_BYTES} chars")
                return False

            # Re-encode image at progressively smaller sizes until it fits
            img = Image.open(file_path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Target: base64 is ~33% larger than binary, so binary budget ≈ budget * 3/4
            binary_budget = int(budget * 3 / 4)

            for max_dim in [1200, 1000, 800, 600]:
                w, h = img.size
                if w > max_dim or h > max_dim:
                    if w > h:
                        new_w, new_h = max_dim, int(h * max_dim / w)
                    else:
                        new_h, new_w = max_dim, int(w * max_dim / h)
                    resized = img.resize((new_w, new_h), Image.LANCZOS)
                else:
                    resized = img

                buf = io.BytesIO()
                resized.save(buf, "JPEG", quality=75)
                img_bytes = buf.getvalue()

                if len(img_bytes) <= binary_budget:
                    log.info(f"Photo #{photo_id}: resized to {resized.size}, "
                             f"{len(img_bytes)} bytes (budget {binary_budget})")
                    break
            else:
                log.error(f"Photo #{photo_id}: cannot shrink image enough to fit")
                return False

            b64 = base64.b64encode(img_bytes).decode("ascii")
            note = photo.get("note", "")
            alt_text = f"Photo: {photo['entity_id']}"
            if photo.get("operation_number"):
                alt_text += f" Op {photo['operation_number']}"
            if note:
                alt_text += f" - {note}"

            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            img_html = (
                f'<p><img src="data:image/jpeg;base64,{b64}" '
                f'alt="{alt_text}" style="max-width:100%;" />'
                f'<br /><small>{alt_text} ({timestamp})</small></p>'
            )

            # Append image HTML to existing content via getData/setData.
            # We avoid insertHtml because cursor-based insertion can land
            # inside a table cell if the content ends with a table (which
            # ProShop written descriptions often do — tool lists).
            result = driver.execute_script("""
                var html = arguments[0];
                try {
                    var names = Object.keys(CKEDITOR.instances);
                    if (names.length === 0) return {error: 'no CKEditor'};
                    var editor = CKEDITOR.instances[names[0]];

                    // Append image after all existing content
                    var existing = editor.getData();
                    editor.setData(existing + html);

                    // Mark editor dirty so ProShop's save handler knows to submit
                    editor.resetDirty();
                    editor.setData(editor.getData());  // triggers dirty flag
                    try { editor.fire('change'); } catch(e) {}

                    // Sync to textarea
                    if (editor.updateElement) editor.updateElement();

                    // Verify sync
                    var data = editor.getData();
                    var el = editor.element;
                    var ta = el ? el.$ : null;
                    if (ta && ta.tagName === 'TEXTAREA') {
                        ta.value = data;
                        ta.dispatchEvent(new Event('change', {bubbles: true}));
                    }

                    return {
                        ok: true,
                        totalLen: data.length,
                        taLen: ta ? ta.value.length : -1,
                        dirty: editor.checkDirty()
                    };
                } catch(e) {
                    return {error: e.toString()};
                }
            """, img_html)

            if not result or result.get("error"):
                log.error(f"Photo #{photo_id}: insertHtml failed: {result}")
                return False

            log.info(f"Photo #{photo_id}: image inserted — editor={result.get('totalLen')} chars, "
                     f"textarea={result.get('taLen')} chars, dirty={result.get('dirty')}")

            # Check total size against ProShop limit
            total = result.get("totalLen", 0)
            if total > MAX_CONTENT_BYTES:
                log.warning(f"Photo #{photo_id}: total content {total} chars exceeds "
                            f"safe limit — ProShop may silently discard the save")

            # Save via fetch (same pattern as ProShop Bridge _save_via_fetch)
            return self._save_page(driver, photo_id)

        except Exception as e:
            log.error(f"Photo #{photo_id}: image insert error: {e}", exc_info=True)
            return False

    def _save_page(self, driver, photo_id):
        """Save the checked-out page via fetch() for a verified response.

        Adapted from ProShop Bridge's _save_via_fetch — intercepts form submit
        and sends via fetch() to get a verifiable HTTP response without page reload.
        """
        # Sync CKEditor, install submit interceptor, trigger requestSubmit
        driver.execute_script("""
            window.__saveResult = null;

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
            if (!form) { window.__saveResult = {error: 'no form found'}; return; }

            var saveBtn = form.querySelector('button[name="_submitChanges_"]');
            if (!saveBtn) {
                window.__saveResult = {error: 'no save button found'};
                return;
            }

            // Install submit interceptor (fires after ProShop's own handlers)
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                e.stopImmediatePropagation();

                var formData = new FormData(form);
                formData.append(saveBtn.name, saveBtn.value);
                var actionUrl = form.action || window.location.href;

                fetch(actionUrl, {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin'
                }).then(function(resp) {
                    return resp.text().then(function(body) {
                        window.__saveResult = {
                            status: resp.status,
                            ok: resp.ok,
                            bodyLen: body.length
                        };
                    });
                }).catch(function(err) {
                    window.__saveResult = {error: err.toString()};
                });
            });

            // Trigger form submission through ProShop's handlers
            try {
                form.requestSubmit(saveBtn);
            } catch(e) {
                saveBtn.click();
            }
        """)

        # Poll for fetch response
        deadline = time.time() + 120  # 2 min timeout for large payloads
        result = None
        while time.time() < deadline:
            time.sleep(2)
            try:
                result = driver.execute_script("return window.__saveResult;")
                if result is not None:
                    break
            except Exception as e:
                # Handle unexpected alerts (e.g., from CKEditor validation)
                from selenium.common.exceptions import UnexpectedAlertPresentException
                if isinstance(e, UnexpectedAlertPresentException):
                    log.warning(f"Photo #{photo_id}: alert during save: {e.alert_text}")
                    try:
                        driver.switch_to.alert.accept()
                    except Exception:
                        pass
                    result = {"error": f"alert: {e.alert_text}"}
                    break
                log.debug(f"Photo #{photo_id}: save poll error: {e}")

        if result is None:
            log.error(f"Photo #{photo_id}: save timed out after 120s")
            _save_screenshot(driver, f"photo_{photo_id}_save_timeout")
            return False

        if result.get("error"):
            log.error(f"Photo #{photo_id}: save failed: {result}")
            _save_screenshot(driver, f"photo_{photo_id}_save_error")
            return False

        if result.get("ok"):
            log.info(f"Photo #{photo_id}: save successful (HTTP {result.get('status')}, "
                     f"{result.get('bodyLen')} bytes)")
            return True
        else:
            log.error(f"Photo #{photo_id}: save returned unexpected: {result}")
            _save_screenshot(driver, f"photo_{photo_id}_save_unexpected")
            return False


# ── Shared Selenium helpers ──────────────────────────────────────────────
# Adapted from proshop_selenium_helper.py


def _safe_navigate(driver, url):
    """Navigate to URL, handling page load timeouts."""
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
    """Try multiple selectors, return first match or None."""
    from selenium.common.exceptions import NoSuchElementException
    for selector in selectors:
        try:
            return driver.find_element(*selector)
        except NoSuchElementException:
            continue
    return None


def _wait_for_element(driver, checker_fn, timeout=30):
    """Poll until checker_fn(driver) returns truthy, or timeout."""
    from selenium.common.exceptions import TimeoutException
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = checker_fn(driver)
            if result:
                return result
        except TimeoutException:
            try:
                driver.execute_script("window.stop()")
            except Exception:
                pass
        except Exception as e:
            log.debug(f"Poll: {type(e).__name__}: {e}")
        time.sleep(0.5)
    return None


def _switch_to_editor_frame(driver):
    """Switch into the frame containing the editor, if page uses framesets."""
    from selenium.webdriver.common.by import By
    frames = driver.find_elements(By.TAG_NAME, "frame")
    if not frames:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    if not frames:
        return
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
                log.debug(f"Switched to content frame {i}")
                return
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()


def _wait_for_ckeditor(driver, timeout=30):
    """Poll until a CKEditor instance is ready."""
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
    """Click CHECKOUT to enable editing, poll for SAVE button."""
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
        log.debug("Already in edit mode")
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
        log.warning("No CHECKOUT button found")
        return False

    driver.execute_script(
        "var el = arguments[0]; setTimeout(function(){ el.click(); }, 0)",
        checkout_btn,
    )

    save_found = _wait_for_element(driver, _find_save_button, timeout=45)
    return save_found is not None


def _save_screenshot(driver, label):
    """Save a failure screenshot to data/logs/."""
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_label = label.replace(" ", "_").replace("/", "_")[:40]
        path = config.LOGS_DIR / f"fail_{safe_label}_{timestamp}.png"
        driver.save_screenshot(str(path))
        log.info(f"Screenshot saved: {path}")
    except Exception as e:
        log.debug(f"Screenshot error: {e}")
