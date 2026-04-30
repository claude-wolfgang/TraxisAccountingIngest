(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-tool-label';
  let lastUrl = window.location.href;

  // ─── Tool ID from URL ──────────────────────────────────────────

  function getToolIdFromUrl() {
    // /procnc/tools/GROUP/TB507 or /procnc/tools/TB507
    let m = window.location.href.match(/\/procnc\/tools\/[^/]+\/([A-Z0-9-]+?)(?:\$|$)/i);
    if (m) return m[1];
    m = window.location.href.match(/\/procnc\/tools\/([A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : null;
  }

  function getToolUrl() {
    let m = window.location.href.match(/(https:\/\/[^/]+\/procnc\/tools\/[^/]+\/[A-Z0-9-]+?)(?:\$|$)/i);
    if (m) return m[1];
    m = window.location.href.match(/(https:\/\/[^/]+\/procnc\/tools\/[A-Z0-9-]+?)(?:\$|$)/i);
    return m ? m[1] : window.location.href;
  }

  // ─── DOM Scraping (iframes) ────────────────────────────────────

  function getIframeDocs() {
    const docs = [];
    try {
      for (const iframe of document.querySelectorAll('iframe')) {
        try {
          if (iframe.contentDocument) docs.push(iframe.contentDocument);
        } catch (e) {
          console.warn('[Traxis Tool Label] iframe access blocked (cross-origin?):', e.message);
        }
      }
    } catch (e) {}
    return docs;
  }

  function scrapeFromIframes() {
    const data = { description: '', location: '' };
    const iframeDocs = getIframeDocs();
    console.log(`[Traxis Tool Label] Found ${iframeDocs.length} accessible iframe(s), ${document.querySelectorAll('iframe').length} total`);

    for (const doc of iframeDocs) {
      const fields = doc.querySelectorAll('[data-display-name]');
      for (const el of fields) {
        const name = el.getAttribute('data-display-name');
        const val = (el.value || el.textContent || '').trim();
        if (!val) continue;
        if (!data.description && /^(Header|Description|Tool Name|Tool Description)$/i.test(name)) {
          data.description = val;
          console.log(`[Traxis Tool Label] iframe field "${name}" → "${val}"`);
        }
        if (!data.location && /^(Location|Tool Location)$/i.test(name)) {
          data.location = val;
          console.log(`[Traxis Tool Label] iframe field "${name}" → "${val}"`);
        }
      }
      if (fields.length > 0) {
        console.log('[Traxis Tool Label] All iframe fields:',
          Array.from(fields).map(f => `${f.getAttribute('data-display-name')}=${(f.value||'').substring(0,60)}`));
      }

      if (!data.description || !data.location) {
        const inputs = doc.querySelectorAll('input, textarea, select');
        for (const input of inputs) {
          const val = (input.value || '').trim();
          if (!val) continue;
          const nameAttr = (input.name || input.id || '').toLowerCase();
          if (!data.description && /descr|header|toolname/i.test(nameAttr)) {
            data.description = val;
            console.log(`[Traxis Tool Label] iframe input "${nameAttr}" → "${val}"`);
          }
          if (!data.location && /location/i.test(nameAttr)) {
            data.location = val;
            console.log(`[Traxis Tool Label] iframe input "${nameAttr}" → "${val}"`);
          }
        }
      }
    }
    return data;
  }

  // ─── DOM Scraping (top-level) ──────────────────────────────────

  function scrapeFromDOM() {
    const data = { description: '', location: '' };
    const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');

    for (let i = 0; i < allCells.length; i++) {
      const el = allCells[i];
      const text = (el.textContent || '').trim();

      if (!data.description && /^[^a-z]*Description:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) {
          data.description = val;
          console.log(`[Traxis Tool Label] DOM field "${text}" → "${val}"`);
        }
      }
      if (!data.location && /^[^a-z]*Location:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) {
          data.location = val;
          console.log(`[Traxis Tool Label] DOM field "${text}" → "${val}"`);
        }
      }
    }

    if (!data.description) {
      const headerEl = document.querySelector('h1, h2, .page-title');
      if (headerEl) {
        const hText = headerEl.textContent.trim();
        const pMatch = hText.match(/[–—]\s*(.+)/);
        if (pMatch) {
          data.description = pMatch[1].trim();
          console.log(`[Traxis Tool Label] DOM header → "${data.description}"`);
        }
      }
    }

    return data;
  }

  function getNextValue(el) {
    let next = el.nextElementSibling;
    if (next) {
      const input = next.querySelector('input, textarea, select');
      if (input) {
        const val = (input.value || '').trim();
        if (val && val.length < 300) return val;
      }
      const text = (next.textContent || '').trim();
      if (text && text.length < 300) return text;
    }
    if (el.tagName === 'TD' || el.tagName === 'TH') {
      const row = el.closest('tr');
      if (row) {
        const cells = row.querySelectorAll('td, th');
        for (let i = 0; i < cells.length; i++) {
          if (cells[i] === el && cells[i + 1]) {
            const input = cells[i + 1].querySelector('input, textarea, select');
            if (input) {
              const val = (input.value || '').trim();
              if (val && val.length < 300) return val;
            }
            const text = (cells[i + 1].textContent || '').trim();
            if (text && text.length < 300) return text;
          }
        }
      }
    }
    if (el.tagName === 'DT') {
      const dd = el.nextElementSibling;
      if (dd && dd.tagName === 'DD') return (dd.textContent || '').trim();
    }
    return null;
  }

  // ─── GraphQL API Fallback ──────────────────────────────────────

  async function fetchFromAPI(toolNumber) {
    const query = `query {
      tools(filter: { toolNumber: ["${toolNumber}"] }) {
        records {
          toolNumber
          description
          location
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
      const tool = json?.data?.tools?.records?.[0];
      if (!tool) throw new Error('Tool not found in API response');

      console.log('[Traxis Tool Label] API result:', tool);
      return {
        description: tool.description || '',
        location: tool.location || '',
      };
    } catch (err) {
      console.warn('[Traxis Tool Label] API fallback failed:', err.message);
      return null;
    }
  }

  // ─── Gather All Data ───────────────────────────────────────────

  async function gatherData(toolId) {
    const iframe = scrapeFromIframes();
    const hasDesc = iframe.description && iframe.description.length > 1;
    const hasLoc = iframe.location && iframe.location.length > 1;

    if (hasDesc) {
      console.log('[Traxis Tool Label] Using iframe data');
      return { toolNumber: toolId, ...iframe, url: getToolUrl() };
    }

    const dom = scrapeFromDOM();
    const merged = {
      description: iframe.description || dom.description,
      location: iframe.location || dom.location,
    };

    if (merged.description && merged.description.length > 1) {
      console.log('[Traxis Tool Label] Using DOM data');
      return { toolNumber: toolId, ...merged, url: getToolUrl() };
    }

    const api = await fetchFromAPI(toolId);
    if (api) {
      console.log('[Traxis Tool Label] Using API data');
      return {
        toolNumber: toolId,
        description: merged.description || api.description,
        location: merged.location || api.location,
        url: getToolUrl(),
      };
    }

    console.warn('[Traxis Tool Label] No data source returned description');
    return { toolNumber: toolId, ...merged, url: getToolUrl() };
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
        const data = await gatherData(toolId);
        console.log('[Traxis Tool Label] Label data:', data);

        const image_base64 = ToolLabelGenerator.generate(data);

        const result = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage(
            {
              action: 'PRINT_LABEL',
              payload: { image_base64, copies: 1, label_name: `Tool ${toolId}` },
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
