"""Regression test harness for the COTS popup upload path.

Drives _upload_cots_via_popup end-to-end against a single photo in VISIBLE
Chrome so the popup-window → file send_keys → save-and-close flow can be
watched. Bypasses the queue (calls _upload_photo directly), so the
production worker on .71 doesn't race the test.

Run this whenever upload_worker.py or proshop_client.py changes touch
the COTS upload path — or when ProShop's "Handle New Picture" popup
UI changes (button text, URL pattern, popup behavior).

Usage:
    python test_cots_upload.py                  # tests photo #18 (PAC-223)
    python test_cots_upload.py --photo 18
    python test_cots_upload.py --photo 18 --keep-open
    python test_cots_upload.py --photo 18 --reset   # only if .71's worker is stopped

Requires PROSHOP_USERNAME / PROSHOP_PASSWORD in .traxis.env.

Discovery context that built this: inspect_cots_upload.py (sibling script),
session 2026-05-14 — see P31 CLAUDE.md.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import config
import database
from upload_worker import UploadWorker, _safe_navigate, _save_screenshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOGS_DIR / "test_cots_upload.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("test-cots")


def _patch_worker_for_visible_chrome(worker):
    """Replace _ensure_browser so Chrome launches visible (not headless)
    and writes verbose Selenium output we can watch live."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    def _ensure_visible():
        if worker._driver:
            try:
                _ = worker._driver.title
                return True
            except Exception:
                worker._close_browser_unlocked()

        username = config.PROSHOP_USERNAME
        password = config.PROSHOP_PASSWORD
        if not username or not password:
            log.error("PROSHOP_USERNAME / PROSHOP_PASSWORD not set")
            return False

        options = webdriver.ChromeOptions()
        # NO --headless so we can watch the popup
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1600,1000")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-popup-blocking")

        log.info("Launching VISIBLE Chrome...")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(25)

        log.info("Logging into ProShop...")
        _safe_navigate(driver, "https://traxismfg.adionsystems.com/procnc/")
        time.sleep(2)

        def find(selectors):
            from selenium.common.exceptions import NoSuchElementException
            for s in selectors:
                try:
                    return driver.find_element(*s)
                except NoSuchElementException:
                    continue
            return None

        u = find([(By.NAME, "mailAddress"), (By.ID, "mailAddress"),
                  (By.NAME, "username"), (By.CSS_SELECTOR, "input[type='text']")])
        p = find([(By.NAME, "password"), (By.ID, "password"),
                  (By.CSS_SELECTOR, "input[type='password']")])
        if not u or not p:
            log.error("Login form not found")
            return False

        u.clear(); u.send_keys(username)
        p.clear(); p.send_keys(password)

        sub = find([(By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//button[contains(translate(text(),'login','LOGIN'),'LOGIN')]")])
        if not sub:
            log.error("Submit button not found")
            return False
        sub.click()
        time.sleep(3)

        if "invalid" in driver.page_source.lower():
            log.error("Login failed")
            return False

        log.info("Login successful")
        worker._driver = driver
        worker._last_activity = time.time()
        return True

    worker._ensure_browser = _ensure_visible


def _reset_photo_to_pending(photo_id):
    import sqlite3
    con = sqlite3.connect(config.DB_PATH)
    con.execute(
        "UPDATE photos SET status='pending', error_message=NULL, "
        "retry_count=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (photo_id,)
    )
    con.commit()
    con.close()
    log.info(f"Photo #{photo_id}: reset to pending (retry_count=0, error cleared)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", type=int, default=18,
                        help="Photo ID to test (default 18 — PAC-223)")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--reset", action="store_true",
                        help="Reset photo to 'pending' before running. WARNING: "
                             "the production worker on .71 polls 'pending' every "
                             "30s and will race us — only use if .71's worker is stopped.")
    args = parser.parse_args()

    if args.reset:
        _reset_photo_to_pending(args.photo)
    else:
        log.info("Skipping reset (default). _upload_photo will set status='uploading' "
                 "immediately so production worker won't race.")

    photo = database.get_photo(args.photo)
    if not photo:
        log.error(f"Photo #{args.photo} not in DB")
        return 1

    log.info(f"=== Testing COTS upload for photo #{photo['id']} ===")
    log.info(f"  entity:    {photo['entity_type']}/{photo['entity_id']}")
    log.info(f"  proshop:   {photo.get('proshop_url')}")
    log.info(f"  file_path: {photo['file_path']}")
    if photo['entity_type'] != 'cots':
        log.warning(f"Photo is not a COTS photo — entity_type={photo['entity_type']!r}")

    file_full = Path(config.DATA_DIR) / photo["file_path"]
    if not file_full.exists():
        log.error(f"Photo file missing: {file_full}")
        return 1
    log.info(f"  file size: {file_full.stat().st_size} bytes")

    worker = UploadWorker()
    _patch_worker_for_visible_chrome(worker)

    if not worker._ensure_browser():
        log.error("Browser launch failed")
        return 1

    t0 = time.time()
    try:
        worker._upload_photo(photo)
    except Exception as e:
        log.error(f"Upload raised: {e}", exc_info=True)

    elapsed = time.time() - t0
    log.info(f"=== Upload finished in {elapsed:.1f}s ===")

    final = database.get_photo(args.photo)
    log.info(f"Final DB state: status={final['status']!r}  "
             f"retry_count={final['retry_count']}  "
             f"error={final.get('error_message')!r}")

    if args.keep_open:
        log.info("Browser kept open. Press Enter to close.")
        try:
            input(">>> ")
        except (KeyboardInterrupt, EOFError):
            pass

    try:
        worker._driver.quit()
    except Exception:
        pass

    return 0 if final["status"] == "uploaded" else 2


if __name__ == "__main__":
    sys.exit(main())
