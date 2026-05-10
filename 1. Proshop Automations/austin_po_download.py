"""Download Austin Pump PO files using Chrome's own download mechanism."""
import os, re, pickle, time, shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".traxis.env")
USER = os.environ["PROSHOP_USERNAME"]
PWD  = os.environ["PROSHOP_PASSWORD"]
BASE = "https://traxismfg.adionsystems.com"

with open("austin_po_results.pkl","rb") as fh:
    results = pickle.load(fh)

DLDIR = Path("austin_po_files").resolve()
DLDIR.mkdir(exist_ok=True)
TMPDIR = (DLDIR / "_tmp").resolve()
TMPDIR.mkdir(exist_ok=True)

from selenium import webdriver
from selenium.webdriver.common.by import By

opts = webdriver.ChromeOptions()
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--window-size=1600,1000")
opts.add_argument("--disable-gpu")
opts.add_experimental_option("prefs", {
    "download.default_directory": str(TMPDIR),
    "download.prompt_for_download": False,
    "plugins.always_open_pdf_externally": True,
    "profile.default_content_settings.popups": 0,
})
print("Launching Chrome...")
driver = webdriver.Chrome(options=opts)
driver.set_page_load_timeout(30)

# Enable downloads in headless mode (Chrome quirk)
driver.execute_cdp_cmd("Page.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": str(TMPDIR),
})

def find_first(selectors):
    for by, sel in selectors:
        try:
            el = driver.find_element(by, sel)
            if el: return el
        except Exception: pass
    return None

try:
    driver.get(f"{BASE}/procnc/")
    time.sleep(3)
    u = find_first([(By.NAME,"mailAddress"),(By.NAME,"username"),(By.CSS_SELECTOR,"input[type='text']")])
    p = find_first([(By.NAME,"password"),(By.CSS_SELECTOR,"input[type='password']")])
    u.clear(); u.send_keys(USER); p.clear(); p.send_keys(PWD)
    btn = find_first([(By.CSS_SELECTOR,"button[type='submit']"),
                      (By.XPATH,"//button[contains(text(),'LOGIN')]"),
                      (By.XPATH,"//button[contains(text(),'Login')]")])
    btn.click()
    time.sleep(4)
    print("Logged in OK")

    for wo, info in results.items():
        po_url = info["po"].get("proshopUrl")
        print(f"\n=== WO {wo} (PO {info['po'].get('clientPONumber')}) ===")
        try:
            driver.get(po_url)
            time.sleep(7)  # wait for SPA
        except Exception as e:
            print(f"  nav error: {e}")

        for f in info["files"]:
            file_url = f["fileUrl"]
            title = f["title"]
            safe = re.sub(r'[<>:"/\\|?*]', "_", title)
            out = DLDIR / f"{wo}__{safe}"
            if out.exists() and out.stat().st_size > 1024:
                print(f"  [cached] {out.name}")
                continue

            for old in TMPDIR.iterdir():
                try: old.unlink()
                except: pass

            # Use fetch() inside the page context — uses the page's auth cookies/credentials
            print(f"  fetching {title}")
            js = """
              const url = arguments[0];
              const cb = arguments[1];
              fetch(url, { credentials: 'include' })
                .then(async r => {
                  const buf = await r.arrayBuffer();
                  const arr = Array.from(new Uint8Array(buf));
                  cb({ ok: r.ok, status: r.status, ct: r.headers.get('content-type'), len: arr.length, body: arr.slice(0, 100) });
                })
                .catch(e => cb({ error: String(e) }));
            """
            # Use async script for fetch
            driver.set_script_timeout(60)
            res = driver.execute_async_script(js, file_url)
            print(f"    -> status={res.get('status')} ct={res.get('ct')} len={res.get('len')}  err={res.get('error')}")
            # If ok and binary, fetch again to write to disk via JS download trick
            if res.get("ok") and res.get("len", 0) > 1024:
                # Re-fetch and stream to base64 then to Python
                js2 = """
                  const url = arguments[0]; const cb = arguments[1];
                  fetch(url, {credentials:'include'}).then(r=>r.arrayBuffer()).then(buf=>{
                    let s=''; const a=new Uint8Array(buf);
                    for (let i=0;i<a.length;i++) s+=String.fromCharCode(a[i]);
                    cb(btoa(s));
                  }).catch(e=>cb('ERROR:'+e));
                """
                b64 = driver.execute_async_script(js2, file_url)
                if b64.startswith("ERROR:"):
                    print(f"    XX second fetch failed: {b64}")
                else:
                    import base64
                    out.write_bytes(base64.b64decode(b64))
                    print(f"    OK {out.stat().st_size} B -> {out.name}")
            else:
                print(f"    XX skipped (status not ok or len too small)")
finally:
    driver.quit()

print("\nDone. Files in:", DLDIR)
for p in sorted(DLDIR.iterdir()):
    if p.is_file():
        print(f"  {p.name}  ({p.stat().st_size} B)")
