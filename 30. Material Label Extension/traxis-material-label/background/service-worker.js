/**
 * Service Worker — proxies print requests to Brother PT-P700 print service.
 * Needed because content scripts on HTTPS ProShop pages can't fetch HTTP
 * print service directly (mixed-content block).
 */

const PRINT_SERVICE = 'http://10.1.1.242:5002';
const PHOTO_SERVICE = 'http://10.1.1.71:5003';

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === 'PRINT_LABEL') {
    printLabel(msg.payload).then(sendResponse).catch(err =>
      sendResponse({ ok: false, error: err.message })
    );
    return true; // keep channel open for async response
  }

  if (msg.action === 'CHECK_PRINTER') {
    checkPrinter().then(sendResponse).catch(err =>
      sendResponse({ ok: false, error: err.message })
    );
    return true;
  }

  if (msg.action === 'QUEUE_ORDER') {
    queueOrder(msg.payload).then(sendResponse).catch(err =>
      sendResponse({ ok: false, error: err.message })
    );
    return true;
  }
});

async function queueOrder(payload) {
  const res = await fetch(`${PHOTO_SERVICE}/api/queue-order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, error: data.error || `HTTP ${res.status}` };
  }
  return { ok: true, ...data };
}

async function printLabel({ image_base64, copies = 1, label_name }) {
  const res = await fetch(`${PRINT_SERVICE}/api/print-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_base64, copies, label_name }),
  });
  const data = await res.json();
  if (!res.ok) {
    return { ok: false, error: data.error || `HTTP ${res.status}`, code: data.code };
  }
  return { ok: true, ...data };
}

async function checkPrinter() {
  const res = await fetch(`${PRINT_SERVICE}/api/health`);
  const data = await res.json();
  return { ok: true, ...data };
}
