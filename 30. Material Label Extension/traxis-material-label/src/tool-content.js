(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-tool-label';
  let lastUrl = window.location.href;

  function getToolIdFromUrl() {
    // Try two-segment: /procnc/tools/GROUP/TB507
    let m = window.location.href.match(/\/procnc\/tools\/[^/]+\/([A-Z0-9-]+?)(?:\$|$)/i);
    if (m) return m[1];
    // Try one-segment: /procnc/tools/TB507
    m = window.location.href.match(/\/procnc\/tools\/([A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : null;
  }

  function getToolUrl() {
    let m = window.location.href.match(/(https:\/\/[^/]+\/procnc\/tools\/[^/]+\/[A-Z0-9-]+?)(?:\$|$)/i);
    if (m) return m[1];
    m = window.location.href.match(/(https:\/\/[^/]+\/procnc\/tools\/[A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : window.location.href;
  }

  // ─── DOM Scraping ───────────────────────────────────────────────

  function scrapeFromDOM() {
    const data = { toolNumber: '', description: '', location: '' };

    // Direct selector: input with data-display-name="Tool #"
    const toolInput = document.querySelector('input[data-display-name="Tool #"]');
    if (toolInput) data.toolNumber = toolInput.value.trim();

    // Direct selector: tools-toolNumber row
    if (!data.toolNumber) {
      const toolRow = document.querySelector('tr.tools-toolNumber .plainvalue input');
      if (toolRow) data.toolNumber = toolRow.value.trim();
    }

    // Try Header field first (the prominent tool description in ProShop)
    const headerArea = document.querySelector('textarea[data-display-name="Header"], input[data-display-name="Header"]');
    if (headerArea) data.description = headerArea.value.trim();

    // Fallback: try Tool Name
    if (!data.description) {
      const nameInput = document.querySelector('input[data-display-name="Tool Name"], textarea[data-display-name="Tool Name"]');
      if (nameInput) data.description = nameInput.value.trim();
    }

    // Location — textarea in ProShop
    const locArea = document.querySelector('tr.tools-location .plainvalue textarea');
    if (locArea) data.location = locArea.value.trim();
    if (!data.location) {
      const locInput = document.querySelector('textarea[data-display-name="Location"], input[data-display-name="Location"]');
      if (locInput) data.location = locInput.value.trim();
    }

    // Fallback: scan all cells for label text
    if (!data.toolNumber || !data.description) {
      const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');
      for (let i = 0; i < allCells.length; i++) {
        const el = allCells[i];
        const ownText = Array.from(el.childNodes)
          .filter(n => n.nodeType === Node.TEXT_NODE)
          .map(n => n.textContent.trim())
          .join(' ')
          .trim();
        const text = ownText || (el.textContent || '').trim();

        if (!data.toolNumber && /^[^a-z]*Tool\s*#:?\s*$/i.test(text)) {
          const val = getNextValue(el);
          if (val) data.toolNumber = val;
        }

        if (!data.description && /^[^a-z]*Header:?\s*$/i.test(text)) {
          const val = getNextValue(el);
          if (val) data.description = val;
        }

      }
    }

    // Fallback: parse tool number from page title "TB507 (O.D. Threaders)"
    if (!data.toolNumber) {
      const titleEl = document.querySelector('h1, h2, .page-title');
      if (titleEl) {
        const m = titleEl.textContent.match(/^([A-Z0-9-]+)/i);
        if (m) data.toolNumber = m[1].trim();
      }
    }

    console.log('[Traxis Tool Label] DOM scrape result:', data);
    return data;
  }

  function getNextValue(el) {
    let next = el.nextElementSibling;
    if (next) {
      const text = extractText(next);
      if (text && text.length < 200) return text;
    }

    if (el.tagName === 'TD' || el.tagName === 'TH') {
      const row = el.closest('tr');
      if (row) {
        const cells = row.querySelectorAll('td, th');
        for (let i = 0; i < cells.length; i++) {
          if (cells[i] === el && cells[i + 1]) {
            const text = extractText(cells[i + 1]);
            if (text && text.length < 200) return text;
          }
        }
      }
    }

    if (el.tagName === 'DT') {
      const dd = el.nextElementSibling;
      if (dd && dd.tagName === 'DD') return extractText(dd);
    }

    return null;
  }

  function extractText(el) {
    if (el.matches && el.matches('input, textarea, select')) {
      return (el.value || el.textContent || '').trim();
    }
    const input = el.querySelector('input, textarea, select');
    if (input) {
      const val = (input.value || input.textContent || '').trim();
      if (val) return val;
    }
    return (el.textContent || '').trim();
  }

  // ─── Gather All Data ────────────────────────────────────────────

  async function gatherData() {
    return scrapeFromDOM();
  }

  // ─── Button Injection ──────────────────────────────────────────

  function inject() {
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;

    const toolId = getToolIdFromUrl();
    if (!toolId) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn traxis-label-btn--tool';
    btn.textContent = 'Print Tool Label';
    btn.title = `Print label for ${toolId}`;

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
        const data = await gatherData();
        const url = getToolUrl();
        console.log('[Traxis Tool Label] Label data:', { ...data, url });

        const image_base64 = ToolLabelGenerator.generate({ ...data, url });

        const labelName = data.toolNumber
          ? `Tool ${data.toolNumber}`
          : 'Tool Label';

        const result = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage(
            {
              action: 'PRINT_LABEL',
              payload: { image_base64, copies: 1, label_name: labelName },
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
            btn.textContent = 'Print Tool Label';
            btn.classList.remove('traxis-label-btn--success');
            status.textContent = '';
          }, 3000);
        } else {
          throw new Error(result.error || 'Print failed');
        }
      } catch (err) {
        console.error('[Traxis Tool Label] Print error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Print Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = 'Print Tool Label';
          btn.classList.remove('traxis-label-btn--error');
          status.textContent = '';
          status.className = 'traxis-label-status';
        }, 5000);
      }
    });

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: fixed; top: 8px; left: 50%; transform: translateX(-50%); z-index: 9999; display: flex; align-items: center; gap: 6px;';
    wrapper.appendChild(btn);
    wrapper.appendChild(status);
    document.body.appendChild(wrapper);

    console.log(`[Traxis Tool Label] Button injected for ${toolId}`);
  }

  // ─── MutationObserver (AJAX navigation) ─────────────────────────

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
          const wrapper = old.closest('div');
          if (wrapper) wrapper.remove();
        }
        inject();
      } else if (!document.querySelector(`[${BUTTON_ATTR}]`)) {
        inject();
      }
    }, 500);
  });

  // ─── Init ───────────────────────────────────────────────────────

  inject();
  observer.observe(document.body, { childList: true, subtree: true });
  console.log('[Traxis Tool Label] Extension loaded');
})();
