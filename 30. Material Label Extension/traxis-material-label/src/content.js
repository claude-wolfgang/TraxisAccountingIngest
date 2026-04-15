/**
 * Content Script — injects "Print Material Label" button on ProShop WO pages.
 *
 * Data flow:
 *   1. WO number from URL (always reliable)
 *   2. Material / part / qty scraped from DOM (fast) or GraphQL API (fallback)
 *   3. Label PNG rendered client-side via LabelGenerator
 *   4. Sent to service worker → Brother PT-P700 print service
 */

(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-material-label';
  let lastUrl = window.location.href;

  // ─── WO Number from URL ───────────────────────────────────────────

  function getWOFromUrl() {
    const m = window.location.href.match(/\/procnc\/workorders\/\d+\/(\d+-\d+)/);
    return m ? m[1] : null;
  }

  // ─── DOM Scraping ─────────────────────────────────────────────────

  /**
   * Try to scrape material info from the WO page DOM.
   * ProShop renders WO details in tables/spans — we search for labels
   * and grab adjacent values.
   */
  function scrapeFromDOM() {
    const data = { material: '', partNumber: '', quantity: '' };

    // Strategy: find all table cells, labels, and dt/dd pairs
    const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');

    for (let i = 0; i < allCells.length; i++) {
      const el = allCells[i];
      const text = (el.textContent || '').trim();

      // Material type / grade — look for labels like "Material", "Material Type"
      if (/^Material(\s+Type)?:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.material = val;
      }

      // Part number
      if (/^Part\s*(Number|#|No\.?)?:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.partNumber = val;
      }

      // Order quantity
      if (/^(Order\s+)?Qty:?\s*$/i.test(text) || /^Quantity:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.quantity = val;
      }
    }

    // Also try: page title or header often has the part number
    if (!data.partNumber) {
      const headerEl = document.querySelector('h1, h2, .page-title, .wo-title');
      if (headerEl) {
        const hText = headerEl.textContent.trim();
        // Often formatted as "WO 26-0120 — PART-1234" or similar
        const pMatch = hText.match(/[-–—]\s*(.+)/);
        if (pMatch) data.partNumber = pMatch[1].trim();
      }
    }

    console.log('[Traxis Material Label] DOM scrape result:', data);
    return data;
  }

  /** Get the text value from the next sibling or adjacent cell */
  function getNextValue(el) {
    // Next sibling element
    let next = el.nextElementSibling;
    if (next) {
      const text = next.textContent.trim();
      if (text && text.length < 200) return text;
    }

    // If it's a <td>, try the next <td> in the same row
    if (el.tagName === 'TD' || el.tagName === 'TH') {
      const row = el.closest('tr');
      if (row) {
        const cells = row.querySelectorAll('td, th');
        for (let i = 0; i < cells.length; i++) {
          if (cells[i] === el && cells[i + 1]) {
            const text = cells[i + 1].textContent.trim();
            if (text && text.length < 200) return text;
          }
        }
      }
    }

    // If it's a <dt>, look for the next <dd>
    if (el.tagName === 'DT') {
      const dd = el.nextElementSibling;
      if (dd && dd.tagName === 'DD') {
        return dd.textContent.trim();
      }
    }

    return null;
  }

  // ─── GraphQL API Fallback ─────────────────────────────────────────

  /**
   * Fetch WO data via ProShop's GraphQL API using the session cookie.
   * This works because the content script runs in ProShop's origin.
   */
  async function fetchFromAPI(woNumber) {
    const query = `query {
      workOrders(woNumber: "${woNumber}") {
        results {
          woNumber
          partNumber
          materialType
          materialGrade
          orderQty
        }
      }
    }`;

    try {
      const res = await fetch('https://traxismfg.adionsystems.com/api/graphql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include', // use session cookie
        body: JSON.stringify({ query }),
      });

      if (!res.ok) throw new Error(`API ${res.status}`);
      const json = await res.json();
      const wo = json?.data?.workOrders?.results?.[0];
      if (!wo) throw new Error('WO not found in API response');

      const material = [wo.materialType, wo.materialGrade]
        .filter(Boolean).join(' ');

      console.log('[Traxis Material Label] API result:', wo);
      return {
        material: material || '',
        partNumber: wo.partNumber || '',
        quantity: wo.orderQty ? String(wo.orderQty) : '',
      };
    } catch (err) {
      console.warn('[Traxis Material Label] API fallback failed:', err.message);
      return null;
    }
  }

  // ─── Gather All Data ──────────────────────────────────────────────

  async function gatherData(woNumber) {
    // Try DOM first
    const dom = scrapeFromDOM();
    const hasMaterial = dom.material && dom.material.length > 1;
    const hasPartNumber = dom.partNumber && dom.partNumber.length > 1;

    // If DOM got the essentials, use it
    if (hasMaterial && hasPartNumber) {
      return { woNumber, ...dom };
    }

    // Otherwise try API and merge
    const api = await fetchFromAPI(woNumber);
    if (api) {
      return {
        woNumber,
        material: dom.material || api.material,
        partNumber: dom.partNumber || api.partNumber,
        quantity: dom.quantity || api.quantity,
      };
    }

    // Use whatever DOM found
    return { woNumber, ...dom };
  }

  // ─── Button Injection ─────────────────────────────────────────────

  function inject() {
    // Don't double-inject
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;

    const woNumber = getWOFromUrl();
    if (!woNumber) return;

    const btn = document.createElement('button');
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn';
    btn.textContent = 'Print Material Label';
    btn.title = `Print material label for WO ${woNumber}`;

    const status = document.createElement('span');
    status.className = 'traxis-label-status';

    btn.addEventListener('click', async () => {
      if (btn.classList.contains('traxis-label-btn--printing')) return;

      btn.classList.remove('traxis-label-btn--success', 'traxis-label-btn--error');
      btn.classList.add('traxis-label-btn--printing');
      btn.textContent = 'Printing...';
      status.textContent = '';
      status.className = 'traxis-label-status';

      try {
        const data = await gatherData(woNumber);
        console.log('[Traxis Material Label] Label data:', data);

        const image_base64 = LabelGenerator.generate(data);

        const result = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage(
            {
              action: 'PRINT_LABEL',
              payload: {
                image_base64,
                copies: 1,
                label_name: `Material WO ${woNumber}`,
              },
            },
            (response) => {
              if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
              } else {
                resolve(response);
              }
            }
          );
        });

        if (result.ok) {
          btn.classList.remove('traxis-label-btn--printing');
          btn.classList.add('traxis-label-btn--success');
          btn.textContent = 'Printed!';
          status.textContent = `Sent to ${result.printer || 'printer'}`;
          setTimeout(() => {
            btn.textContent = 'Print Material Label';
            btn.classList.remove('traxis-label-btn--success');
            status.textContent = '';
          }, 3000);
        } else {
          throw new Error(result.error || 'Print failed');
        }
      } catch (err) {
        console.error('[Traxis Material Label] Print error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Print Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = 'Print Material Label';
          btn.classList.remove('traxis-label-btn--error');
          status.textContent = '';
          status.className = 'traxis-label-status';
        }, 5000);
      }
    });

    // Place button inline in the Part Stock row, in the white space
    // to the right of the green material text. Never overlap anything.
    let inserted = false;

    // Find the Part Stock value cell (the green one with material text)
    // and place button at its far right edge.
    const tds = document.querySelectorAll('td');
    for (let i = 0; i < tds.length; i++) {
      const txt = tds[i].textContent.trim();
      if (/^Part\s+Stock:?\s*$/i.test(txt)) {
        // Label cell found — the value cell is the next td sibling
        let valueCell = tds[i].nextElementSibling;
        // If no direct sibling, try next td in the row
        if (!valueCell || valueCell.tagName !== 'TD') {
          const row = tds[i].closest('tr');
          if (row) {
            const cells = row.querySelectorAll('td');
            valueCell = cells.length > 1 ? cells[1] : cells[0];
          }
        }
        if (valueCell) {
          // Anchor to the row or table so button reaches the far right edge
          const row = valueCell.closest('tr');
          const anchor = row || valueCell;
          const existing = anchor.style.position;
          if (!existing || existing === 'static') {
            anchor.style.position = 'relative';
          }
          const btnWrap = document.createElement('span');
          btnWrap.style.cssText = 'position: absolute; right: 0; top: 50%; transform: translateY(-50%); z-index: 10;';
          btnWrap.appendChild(btn);
          btnWrap.appendChild(status);
          anchor.appendChild(btnWrap);
          inserted = true;
        }
        break;
      }
    }

    // Fallback: before the operations table
    if (!inserted) {
      const opsTables = document.querySelectorAll('table');
      for (const tbl of opsTables) {
        const th = tbl.querySelector('th, td');
        if (th && /Op\s*#/i.test(th.textContent)) {
          const wrapper = document.createElement('div');
          wrapper.style.cssText = 'margin: 6px 0; clear: both;';
          wrapper.appendChild(btn);
          wrapper.appendChild(status);
          tbl.parentNode.insertBefore(wrapper, tbl);
          inserted = true;
          break;
        }
      }
    }

    if (!inserted) {
      const wrapper = document.createElement('div');
      wrapper.style.cssText = 'margin: 6px 0; clear: both;';
      wrapper.appendChild(btn);
      wrapper.appendChild(status);
      document.body.prepend(wrapper);
    }

    console.log(`[Traxis Material Label] Button injected for WO ${woNumber}`);
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
          const statusEl = old.nextElementSibling;
          if (statusEl && statusEl.classList.contains('traxis-label-status')) {
            statusEl.remove();
          }
          old.remove();
        }
        inject();
      } else if (!document.querySelector(`[${BUTTON_ATTR}]`)) {
        inject();
      }
    }, 500);
  });

  // ─── Init ─────────────────────────────────────────────────────────

  inject();
  observer.observe(document.body, { childList: true, subtree: true });
  console.log('[Traxis Material Label] Extension loaded');
})();
