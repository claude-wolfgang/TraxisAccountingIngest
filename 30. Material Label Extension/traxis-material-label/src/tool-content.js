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

  // ─── DOM Scraping ──────────────────────────────────────────────

  function getIframeDocs() {
    const docs = [];
    try {
      for (const iframe of document.querySelectorAll('iframe')) {
        try {
          if (iframe.contentDocument) docs.push(iframe.contentDocument);
        } catch (e) {}
      }
    } catch (e) {}
    return docs;
  }

  function scrapeFromIframes() {
    const data = { description: '', location: '' };
    for (const doc of getIframeDocs()) {
      const fields = doc.querySelectorAll('[data-display-name]');
      for (const el of fields) {
        const name = el.getAttribute('data-display-name');
        const val = (el.value || el.textContent || '').trim();
        if (!val) continue;
        if (!data.description && /^(Header|Description|Tool Name)$/i.test(name)) {
          data.description = val;
          console.log(`[Traxis Tool Label] iframe field "${name}" → "${val}"`);
        }
        if (!data.location && /^Location$/i.test(name)) {
          data.location = val;
          console.log(`[Traxis Tool Label] iframe field "${name}" → "${val}"`);
        }
      }
      if (fields.length > 0) {
        console.log('[Traxis Tool Label] All iframe fields:',
          Array.from(fields).map(f => `${f.getAttribute('data-display-name')}=${(f.value||'').substring(0,60)}`));
      }
    }
    return data;
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
        const scraped = scrapeFromIframes();
        const description = scraped.description;
        const location = scraped.location;
        const url = getToolUrl();
        const data = { toolNumber: toolId, description, location, url };
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
