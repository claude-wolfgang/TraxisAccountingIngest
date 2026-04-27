(function () {
  'use strict';

  const BUTTON_ATTR = 'data-traxis-box-label';
  let lastUrl = window.location.href;

  function getWOFromUrl() {
    const m = window.location.href.match(/\/procnc\/workorders\/\d+\/(\d+-\d+)/);
    return m ? m[1] : null;
  }

  function scrapeFromDOM() {
    const data = { customerPO: '', partNumber: '' };
    const allCells = document.querySelectorAll('td, th, dt, dd, span, label, div');

    for (let i = 0; i < allCells.length; i++) {
      const el = allCells[i];
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .map(n => n.textContent.trim())
        .join(' ')
        .trim();
      const text = ownText || (el.textContent || '').trim();

      if (/^[^a-z]*(Customer\s+PO|Customer\s+P\.?O\.?\s*#?|PO\s+(Number|#)):?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.customerPO = val;
      }

      if (/^[^a-z]*Part\s*(Number|#|No\.?)\s*:?\s*$/i.test(text)) {
        const val = getNextValue(el);
        if (val) data.partNumber = val;
      }
    }

    if (!data.partNumber) {
      const headerEl = document.querySelector('h1, h2, .page-title, .wo-title');
      if (headerEl) {
        const hText = headerEl.textContent.trim();
        const pMatch = hText.match(/[-–—]\s*(.+)/);
        if (pMatch) data.partNumber = pMatch[1].trim();
      }
    }

    console.log('[Traxis Box Label] DOM scrape result:', data);
    return data;
  }

  function getNextValue(el) {
    let next = el.nextElementSibling;
    if (next) {
      const text = (next.textContent || '').trim();
      if (text && text.length < 200) return text;
    }
    if (el.tagName === 'TD' || el.tagName === 'TH') {
      const row = el.closest('tr');
      if (row) {
        const cells = row.querySelectorAll('td, th');
        for (let i = 0; i < cells.length; i++) {
          if (cells[i] === el && cells[i + 1]) {
            const text = (cells[i + 1].textContent || '').trim();
            if (text && text.length < 200) return text;
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

  async function fetchFromAPI(woNumber) {
    const query = `query {
      workOrders(woNumber: "${woNumber}") {
        results {
          woNumber
          partNumber
          customerPoNumber
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
      const wo = json?.data?.workOrders?.results?.[0];
      if (!wo) throw new Error('WO not found in API response');

      console.log('[Traxis Box Label] API result:', wo);
      return {
        customerPO: wo.customerPoNumber || '',
        partNumber: wo.partNumber || '',
      };
    } catch (err) {
      console.warn('[Traxis Box Label] API fallback failed:', err.message);
      return null;
    }
  }

  async function gatherData(woNumber) {
    const dom = scrapeFromDOM();
    const hasPO = dom.customerPO && dom.customerPO.length > 1;
    const hasPart = dom.partNumber && dom.partNumber.length > 1;

    if (hasPO && hasPart) {
      return { woNumber, ...dom };
    }

    const api = await fetchFromAPI(woNumber);
    if (api) {
      return {
        woNumber,
        customerPO: dom.customerPO || api.customerPO,
        partNumber: dom.partNumber || api.partNumber,
      };
    }

    return { woNumber, ...dom };
  }

  function findShippingRow() {
    const rows = document.querySelectorAll('tr');
    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      for (const cell of cells) {
        if (/^Shipping/i.test((cell.textContent || '').trim())) {
          return row;
        }
      }
    }
    return null;
  }

  function inject() {
    if (document.querySelector(`[${BUTTON_ATTR}]`)) return;

    const woNumber = getWOFromUrl();
    if (!woNumber) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute(BUTTON_ATTR, 'true');
    btn.className = 'traxis-label-btn traxis-label-btn--box';
    btn.textContent = 'Print Box Label';
    btn.title = `Print box label for WO ${woNumber}`;

    const status = document.createElement('span');
    status.className = 'traxis-label-status';

    btn.addEventListener('click', async () => {
      if (btn.classList.contains('traxis-label-btn--printing')) return;

      const boxQty = window.prompt('Enter Qty of Parts in Box');
      if (boxQty === null || boxQty.trim() === '') return;

      btn.classList.remove('traxis-label-btn--success', 'traxis-label-btn--error');
      btn.classList.add('traxis-label-btn--printing');
      btn.textContent = 'Printing...';
      status.textContent = '';
      status.className = 'traxis-label-status';

      try {
        const data = await gatherData(woNumber);
        data.boxQty = boxQty.trim();
        data.url = window.location.href.replace(/\$.*$/, '');
        console.log('[Traxis Box Label] Label data:', data);

        const image_base64 = BoxLabelGenerator.generate(data);

        const result = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage(
            {
              action: 'PRINT_LABEL',
              payload: {
                image_base64,
                copies: 1,
                label_name: `Box WO ${woNumber}`,
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
            btn.textContent = 'Print Box Label';
            btn.classList.remove('traxis-label-btn--success');
            status.textContent = '';
          }, 3000);
        } else {
          throw new Error(result.error || 'Print failed');
        }
      } catch (err) {
        console.error('[Traxis Box Label] Print error:', err);
        btn.classList.remove('traxis-label-btn--printing');
        btn.classList.add('traxis-label-btn--error');
        btn.textContent = 'Print Failed';
        status.textContent = err.message;
        status.className = 'traxis-label-status traxis-label-status--error';
        setTimeout(() => {
          btn.textContent = 'Print Box Label';
          btn.classList.remove('traxis-label-btn--error');
          status.textContent = '';
          status.className = 'traxis-label-status';
        }, 5000);
      }
    });

    let inserted = false;
    const shippingRow = findShippingRow();
    if (shippingRow) {
      const cells = shippingRow.querySelectorAll('td');
      // Find the "Certified To Run" column — typically the 5th cell (index 4)
      // by matching against the header row
      let targetIdx = -1;
      const table = shippingRow.closest('table');
      if (table) {
        const headers = table.querySelectorAll('th');
        for (let i = 0; i < headers.length; i++) {
          if (/Certified\s*(To\s*Run)?/i.test(headers[i].textContent.trim())) {
            targetIdx = i;
            break;
          }
        }
      }
      const targetCell = targetIdx >= 0 && cells[targetIdx] ? cells[targetIdx] : null;
      if (targetCell) {
        targetCell.style.position = 'relative';
        const btnWrap = document.createElement('span');
        btnWrap.style.cssText = 'display: inline-flex; align-items: center; gap: 4px;';
        btnWrap.appendChild(btn);
        btnWrap.appendChild(status);
        targetCell.appendChild(btnWrap);
        inserted = true;
      }
    }

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

    console.log(`[Traxis Box Label] Button injected for WO ${woNumber}`);
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
          const wrap = old.closest('span');
          if (wrap) wrap.remove();
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
  console.log('[Traxis Box Label] Extension loaded');
})();
