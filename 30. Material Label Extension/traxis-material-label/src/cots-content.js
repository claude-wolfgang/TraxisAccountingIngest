/**
 * Content Script — injects "Print COTS Label" button on ProShop COTS pages.
 *
 * Data flow:
 *   1. COTS ID from URL (e.g. /procnc/ots/THI/THI-219)
 *   2. Description scraped from DOM
 *   3. Label PNG rendered client-side via COTSLabelGenerator
 *   4. Sent to service worker -> Brother PT-P700 print service
 */

(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-cots-label';
  let lastUrl = window.location.href;

  // ---- COTS ID from URL ----

  function getCOTSFromUrl() {
    // URL pattern: /procnc/ots/{TYPE}/{TYPE-NUMBER} or /procnc/ots/{TYPE}/{TYPE-NUMBER}$
    const m = window.location.href.match(/\/procnc\/ots\/([A-Z0-9-]+)\/([A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[2].toUpperCase() : null;
  }

  function getCOTSUrl() {
    // Build the canonical ProShop URL from current location
    const m = window.location.href.match(/(https:\/\/[^/]+\/procnc\/ots\/[A-Z0-9-]+\/[A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : window.location.href;
  }

  // ---- DOM Scraping ----

  function scrapeDescription() {
    const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');

    // Try these field labels in priority order
    const patterns = [
      /^Description:?\s*$/i,
      /^COTS\s+Name:?\s*$/i,
      /^Name:?\s*$/i,
      /^A\.?K\.?A\.?:?\s*$/i,
      /^Also\s+Known\s+As:?\s*$/i,
    ];

    for (const pattern of patterns) {
      for (let i = 0; i < allCells.length; i++) {
        const el = allCells[i];
        const text = (el.textContent || '').trim();
        if (pattern.test(text)) {
          const val = getNextValue(el);
          if (val) {
            console.log(`[Traxis COTS Label] Found description via "${text}":`, val);
            return val;
          }
        }
      }
    }

    // Fallback: page title/header
    const headerEl = document.querySelector('h1, h2, .page-title');
    if (headerEl) {
      const hText = headerEl.textContent.trim();
      const pMatch = hText.match(/[-–—]\s*(.+)/);
      if (pMatch) return pMatch[1].trim();
    }

    // ProShop puts the description in a .card-content div near the top
    const cardContent = document.querySelector('.card-content');
    if (cardContent) {
      const text = cardContent.textContent.trim();
      if (text && text.length < 300) {
        console.log('[Traxis COTS Label] Found description via .card-content:', text);
        return text;
      }
    }

    console.warn('[Traxis COTS Label] Could not find description in DOM');
    return '';
  }

  function getNextValue(el) {
    let next = el.nextElementSibling;
    if (next) {
      const text = next.textContent.trim();
      if (text && text.length < 300) return text;
    }

    if (el.tagName === 'TD' || el.tagName === 'TH') {
      const row = el.closest('tr');
      if (row) {
        const cells = row.querySelectorAll('td, th');
        for (let i = 0; i < cells.length; i++) {
          if (cells[i] === el && cells[i + 1]) {
            const text = cells[i + 1].textContent.trim();
            if (text && text.length < 300) return text;
          }
        }
      }
    }

    if (el.tagName === 'DT') {
      const dd = el.nextElementSibling;
      if (dd && dd.tagName === 'DD') return dd.textContent.trim();
    }

    return null;
  }

  // ---- Button Injection ----

  function inject() {
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;

    const cotsId = getCOTSFromUrl();
    if (!cotsId) return;

    const btn = document.createElement('button');
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn';
    btn.textContent = 'Print COTS Label';
    btn.title = `Print label for ${cotsId}`;

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
        const description = scrapeDescription();
        const url = getCOTSUrl();
        console.log('[Traxis COTS Label] Data:', { cotsId, description, url });

        const image_base64 = COTSLabelGenerator.generate({
          cotsId,
          description,
          url,
        });

        const result = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage(
            {
              action: 'PRINT_LABEL',
              payload: {
                image_base64,
                copies: 1,
                label_name: `COTS ${cotsId}`,
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
            btn.textContent = 'Print COTS Label';
            btn.classList.remove('traxis-label-btn--success');
            status.textContent = '';
          }, 3000);
        } else {
          throw new Error(result.error || 'Print failed');
        }
      } catch (err) {
        console.error('[Traxis COTS Label] Print error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Print Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = 'Print COTS Label';
          btn.classList.remove('traxis-label-btn--error');
          status.textContent = '';
          status.className = 'traxis-label-status';
        }, 5000);
      }
    });

    // Place button as a non-intrusive floating element in the top-right area
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: fixed; top: 8px; left: 50%; transform: translateX(-50%); z-index: 9999; display: flex; align-items: center; gap: 6px;';
    wrapper.appendChild(btn);
    wrapper.appendChild(status);
    document.body.appendChild(wrapper);

    console.log(`[Traxis COTS Label] Button injected for ${cotsId}`);
  }

  // ---- MutationObserver (AJAX navigation) ----

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

  // ---- Init ----

  inject();
  observer.observe(document.body, { childList: true, subtree: true });
  console.log('[Traxis COTS Label] Extension loaded');
})();
