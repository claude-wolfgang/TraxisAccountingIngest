/**
 * Buy-button injector for COTS / Tools / Parts pages.
 *
 * Mirrors the label-button placement: appears next to the existing
 * "Print … Label" button. On click: prompts for qty, best-effort scrapes
 * unit cost from the page, posts to P31's /api/queue-order. Background
 * service-worker proxies the call (HTTPS->HTTP mixed-content block).
 */

(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-buy-button';
  const TYPE_BY_URL_RE = [
    { re: /\/procnc\/ots\/[^/]+\/([A-Z0-9-]+)/i, type: 'cots' },
    { re: /\/procnc\/tools\/[^/]+\/([A-Z0-9-]+)/i, type: 'tool' },
    { re: /\/procnc\/tools\/([A-Z0-9-]+)/i, type: 'tool' },
    { re: /\/procnc\/parts\/[^/]+\/([A-Z0-9-]+)/i, type: 'part' },
  ];

  let lastUrl = window.location.href;

  // ─── Identify page type + entity id ───────────────────────────────

  function identifyEntity() {
    const url = window.location.href.replace(/\$.*$/, '');
    for (const p of TYPE_BY_URL_RE) {
      const m = url.match(p.re);
      if (m) return { type: p.type, id: m[1] };
    }
    return null;
  }

  // ─── Scrape best-effort unit cost ─────────────────────────────────
  // COTS Equivalents table has columns: Vendor / Approved Brand / Cost / Lead Time / EDP / Multiplier / Markup
  // Take the cost from the row matching the approved brand (per memory: top approved brand wins)
  function scrapeUnitCost() {
    // Try table headers labeled "Cost"
    const headers = document.querySelectorAll('th, td');
    let costColIdx = -1;
    let costTable = null;
    for (const h of headers) {
      if (/^cost$/i.test((h.textContent || '').trim())) {
        const row = h.closest('tr');
        const cells = row ? Array.from(row.querySelectorAll('th, td')) : [];
        const idx = cells.indexOf(h);
        if (idx >= 0) {
          costColIdx = idx;
          costTable = h.closest('table');
          break;
        }
      }
    }
    if (!costTable || costColIdx < 0) return null;

    const dataRows = costTable.querySelectorAll('tbody tr');
    for (const tr of dataRows) {
      const cells = tr.querySelectorAll('td');
      if (cells.length <= costColIdx) continue;
      const raw = (cells[costColIdx].textContent || '').trim();
      const num = parseFloat(raw.replace(/[^\d.]/g, ''));
      if (!isNaN(num) && num > 0) return num;
    }
    return null;
  }

  function scrapeBrand() {
    const headers = document.querySelectorAll('th, td');
    let brandColIdx = -1;
    let brandTable = null;
    for (const h of headers) {
      if (/approved\s*brand/i.test((h.textContent || '').trim())) {
        const row = h.closest('tr');
        const cells = row ? Array.from(row.querySelectorAll('th, td')) : [];
        const idx = cells.indexOf(h);
        if (idx >= 0) {
          brandColIdx = idx;
          brandTable = h.closest('table');
          break;
        }
      }
    }
    if (!brandTable || brandColIdx < 0) return null;
    const dataRows = brandTable.querySelectorAll('tbody tr');
    for (const tr of dataRows) {
      const cells = tr.querySelectorAll('td');
      if (cells.length > brandColIdx) {
        const raw = (cells[brandColIdx].textContent || '').trim();
        if (raw) return raw;
      }
    }
    return null;
  }

  function scrapeVendor() {
    const headers = document.querySelectorAll('th, td');
    for (const h of headers) {
      if (/^vendor$/i.test((h.textContent || '').trim())) {
        const row = h.closest('tr');
        const cells = row ? Array.from(row.querySelectorAll('th, td')) : [];
        const idx = cells.indexOf(h);
        if (idx < 0) continue;
        const table = h.closest('table');
        const dataRow = table ? table.querySelector('tbody tr') : null;
        if (!dataRow) continue;
        const dataCell = dataRow.querySelectorAll('td')[idx];
        if (dataCell) {
          const v = (dataCell.textContent || '').trim();
          if (v) return v;
        }
      }
    }
    return null;
  }

  // ─── Submit ───────────────────────────────────────────────────────

  async function submit(entity, qty, unit_cost, brand, vendor) {
    const payload = {
      entity_type: entity.type,
      entity_id: entity.id,
      qty: qty,
      unit_cost: unit_cost,
      brand: brand,
      vendor: vendor,
    };
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { action: 'QUEUE_ORDER', payload },
        (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else if (response && response.ok) {
            resolve(response);
          } else {
            reject(new Error((response && response.error) || 'unknown error'));
          }
        }
      );
    });
  }

  // ─── Button injection ─────────────────────────────────────────────

  function inject() {
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;
    const entity = identifyEntity();
    if (!entity) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn traxis-label-btn--buy';
    btn.textContent = 'Buy';
    btn.title = `Queue purchase order for ${entity.type} ${entity.id}`;

    const status = document.createElement('span');
    status.className = 'traxis-label-status';

    btn.addEventListener('click', async () => {
      if (btn.classList.contains('traxis-label-btn--printing')) return;

      const qtyRaw = window.prompt(`Quantity to order for ${entity.id}?`, '1');
      if (qtyRaw === null || qtyRaw.trim() === '') return;
      const qty = parseFloat(qtyRaw);
      if (isNaN(qty) || qty <= 0) {
        window.alert('Quantity must be a positive number.');
        return;
      }

      const unit_cost = scrapeUnitCost();
      const brand = scrapeBrand();
      const vendor = scrapeVendor();
      console.log('[Traxis Buy]', entity, { qty, unit_cost, brand, vendor });

      btn.classList.add('traxis-label-btn--printing');
      const original = btn.textContent;
      btn.textContent = 'Queueing…';
      status.textContent = '';
      status.className = 'traxis-label-status';

      try {
        const result = await submit(entity, qty, unit_cost, brand, vendor);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--success');
        if (result.auto_approved) {
          btn.textContent = 'Auto-Approved';
          status.textContent = `Order #${result.order_id}`;
        } else {
          btn.textContent = 'Queued';
          status.textContent = `Order #${result.order_id} pending approval`;
        }
        setTimeout(() => {
          btn.textContent = original;
          btn.classList.remove('traxis-label-btn--success');
          status.textContent = '';
        }, 4000);
      } catch (err) {
        console.error('[Traxis Buy] error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = original;
          btn.classList.remove('traxis-label-btn--error');
          status.textContent = '';
          status.className = 'traxis-label-status';
        }, 5000);
      }
    });

    // Try to place near an existing label button so it sits in the same row
    const labelBtn = document.querySelector(
      '[data-traxis-cots-label], [data-traxis-tool-label], [data-traxis-material-label]'
    );
    if (labelBtn && labelBtn.parentNode) {
      const wrapper = document.createElement('span');
      wrapper.style.cssText = 'display:inline-flex; gap:6px; align-items:center; margin-left:6px;';
      wrapper.appendChild(btn);
      wrapper.appendChild(status);
      labelBtn.parentNode.appendChild(wrapper);
    } else {
      const wrapper = document.createElement('div');
      wrapper.style.cssText = 'margin: 6px 0;';
      wrapper.appendChild(btn);
      wrapper.appendChild(status);
      document.body.prepend(wrapper);
    }

    console.log(`[Traxis Buy] Button injected for ${entity.type} ${entity.id}`);
  }

  // ─── MutationObserver (AJAX navigation) ───────────────────────────

  let debounceTimer = null;
  const observer = new MutationObserver(() => {
    if (debounceTimer) return;
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      const currentUrl = window.location.href;
      if (currentUrl !== lastUrl) {
        lastUrl = currentUrl;
        const old = document.querySelector(`[${BUTTON_ATTR}]`);
        if (old) {
          const wrap = old.closest('span, div');
          if (wrap && wrap.children.length <= 2) wrap.remove();
          else old.remove();
        }
        inject();
      } else if (!document.querySelector(`[${BUTTON_ATTR}]`)) {
        inject();
      }
    }, 500);
  });

  inject();
  observer.observe(document.body, { childList: true, subtree: true });
  console.log('[Traxis Buy] Extension loaded');
})();
