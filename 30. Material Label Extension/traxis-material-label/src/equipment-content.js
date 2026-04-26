(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-equipment-label';
  let lastUrl = window.location.href;

  // ─── Equipment ID from URL ──────────────────────────────────────

  function getToolIdFromUrl() {
    const m = window.location.href.match(/\/procnc\/equipment\/[A-Z0-9-]+\/([A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : null;
  }

  function getEquipmentUrl() {
    const m = window.location.href.match(/(https:\/\/[^/]+\/procnc\/equipment\/[A-Z0-9-]+\/[A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : window.location.href;
  }

  // ─── DOM Scraping ───────────────────────────────────────────────

  function scrapeFromDOM() {
    const data = { equipmentNumber: '', toolName: '', serialNumber: '' };

    const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');

    for (let i = 0; i < allCells.length; i++) {
      const el = allCells[i];
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .map(n => n.textContent.trim())
        .join(' ')
        .trim();
      const text = ownText || (el.textContent || '').trim();

      if (/^[^a-z]*Internal\s+Tool\s*#:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.equipmentNumber = val;
      }

      if (/^[^a-z]*Tool\s+Name:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.toolName = val;
      }

      if (/^[^a-z]*Serial\s+Number:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.serialNumber = val;
      }
    }

    console.log('[Traxis Equipment Label] DOM scrape result:', data);
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

  // ─── GraphQL API Fallback ───────────────────────────────────────

  async function fetchFromAPI(toolId) {
    const query = `query {
      equipments(tool: "${toolId}") {
        results {
          tool
          toolName
          serialNumber
        }
      }
    }`;

    try {
      const res = await fetch('https://traxismfg.adionsystems.com/api/graphql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ query }),
      });

      if (!res.ok) throw new Error(`API ${res.status}`);
      const json = await res.json();
      const eq = json?.data?.equipments?.results?.[0];
      if (!eq) throw new Error('Equipment not found in API response');

      console.log('[Traxis Equipment Label] API result:', eq);
      return {
        equipmentNumber: eq.tool || '',
        toolName: eq.toolName || '',
        serialNumber: eq.serialNumber || '',
      };
    } catch (err) {
      console.warn('[Traxis Equipment Label] API fallback failed:', err.message);
      return null;
    }
  }

  // ─── Gather All Data ────────────────────────────────────────────

  async function gatherData(toolId) {
    const dom = scrapeFromDOM();
    const hasEquip = dom.equipmentNumber && dom.equipmentNumber.length > 0;
    const hasName = dom.toolName && dom.toolName.length > 0;

    if (hasEquip && hasName) {
      return dom;
    }

    const api = await fetchFromAPI(toolId);
    if (api) {
      return {
        equipmentNumber: dom.equipmentNumber || api.equipmentNumber,
        toolName: dom.toolName || api.toolName,
        serialNumber: dom.serialNumber || api.serialNumber,
      };
    }

    return dom;
  }

  // ─── Button Injection ──────────────────────────────────────────

  function inject() {
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;

    const toolId = getToolIdFromUrl();
    if (!toolId) return;

    const btn = document.createElement('button');
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn traxis-label-btn--equipment';
    btn.textContent = 'Print Equipment Label';
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
        const data = await gatherData(toolId);
        const url = getEquipmentUrl();
        console.log('[Traxis Equipment Label] Label data:', { ...data, url });

        const image_base64 = EquipmentLabelGenerator.generate({
          ...data,
          url,
        });

        const labelName = data.equipmentNumber
          ? `Equipment ${data.equipmentNumber}`
          : 'Equipment Label';

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
            btn.textContent = 'Print Equipment Label';
            btn.classList.remove('traxis-label-btn--success');
            status.textContent = '';
          }, 3000);
        } else {
          throw new Error(result.error || 'Print failed');
        }
      } catch (err) {
        console.error('[Traxis Equipment Label] Print error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Print Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = 'Print Equipment Label';
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

    console.log(`[Traxis Equipment Label] Button injected for ${toolId}`);
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
  console.log('[Traxis Equipment Label] Extension loaded');
})();
