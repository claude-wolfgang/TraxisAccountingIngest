(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-user-label';
  let lastUrl = window.location.href;

  function getUserUrl() {
    return window.location.href.replace(/\$.*$/, '');
  }

  function scrapeFromDOM() {
    const data = { name: '', userId: '' };
    const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');

    for (let i = 0; i < allCells.length; i++) {
      const el = allCells[i];
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .map(n => n.textContent.trim())
        .join(' ')
        .trim();
      const text = ownText || (el.textContent || '').trim();

      if (/^[^a-z]*(Full\s+)?Name:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.name = val;
      }

      if (/^[^a-z]*(First\s+Name):?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.name = val;
      }

      if (/^[^a-z]*(Last\s+Name):?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val && data.name) data.name = data.name + ' ' + val;
        else if (val) data.name = val;
      }

      if (/^[^a-z]*((Original\s+)?User\s*(Id|ID|#|Number)|Employee\s*(Id|ID|#|Number)):?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.userId = val;
      }
    }

    if (!data.name) {
      const headerEl = document.querySelector('h1, h2, .page-title');
      if (headerEl) {
        const hText = headerEl.textContent.trim();
        if (hText && hText.length < 100) data.name = hText;
      }
    }

    if (!data.userId) {
      const m = window.location.href.match(/\/procnc\/users\/(\d+)/);
      if (m) data.userId = m[1];
    }

    console.log('[Traxis User Label] DOM scrape result:', data);
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

  function inject() {
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;

    const btn = document.createElement('button');
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn traxis-label-btn--user';
    btn.textContent = 'Print User Label';
    btn.title = 'Print user ID label';

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
        const data = scrapeFromDOM();
        const url = getUserUrl();
        console.log('[Traxis User Label] Label data:', { ...data, url });

        const image_base64 = UserLabelGenerator.generate({ ...data, url });

        const labelName = data.name
          ? `User ${data.name}`
          : 'User Label';

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
            btn.textContent = 'Print User Label';
            btn.classList.remove('traxis-label-btn--success');
            status.textContent = '';
          }, 3000);
        } else {
          throw new Error(result.error || 'Print failed');
        }
      } catch (err) {
        console.error('[Traxis User Label] Print error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Print Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = 'Print User Label';
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

    console.log('[Traxis User Label] Button injected');
  }

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

  inject();
  observer.observe(document.body, { childList: true, subtree: true });
  console.log('[Traxis User Label] Extension loaded');
})();
