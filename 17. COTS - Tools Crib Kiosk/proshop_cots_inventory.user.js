// ==UserScript==
// @name         ProShop COTS Inventory Helper
// @namespace    https://traxismfg.adionsystems.com
// @version      0.1.0
// @description  Quick ADD/REMOVE overlay for COTS inventory via QR scan
// @author       Traxis Manufacturing
// @match        https://traxismfg.adionsystems.com/procnc/ots/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function() {
  'use strict';

  // Only run on COTS detail pages (URL ends with COTS_ID$)
  const url = window.location.href;
  const cotsMatch = url.match(/\/procnc\/ots\/([A-Z\-]+)\/([A-Z]+-\d+)\$?$/i);
  if (!cotsMatch) return;

  const cotsType = cotsMatch[1];
  const cotsId = cotsMatch[2];

  // --- Status badge (matches ProShop Bridge style) ---
  const _badge = document.createElement('div');
  _badge.id = 'cots-inv-badge';
  _badge.style.cssText = 'position:fixed;bottom:8px;left:8px;z-index:99999;' +
    'background:#0c1938;color:#ff6600;padding:4px 10px;border-radius:4px;' +
    'font-family:Segoe UI,sans-serif;font-size:11px;font-weight:bold;' +
    'box-shadow:0 1px 4px rgba(0,0,0,0.3);opacity:0.9;pointer-events:none;' +
    'transition:background 0.3s,color 0.3s;';
  _badge.textContent = 'COTS Inv: Active';
  document.body.appendChild(_badge);

  function setStatus(text, color) {
    _badge.textContent = 'COTS Inv: ' + text;
    if (color === 'ok')    { _badge.style.background = '#107c10'; _badge.style.color = '#fff'; }
    else if (color === 'warn') { _badge.style.background = '#d48000'; _badge.style.color = '#fff'; }
    else if (color === 'err')  { _badge.style.background = '#c00';    _badge.style.color = '#fff'; }
    else { _badge.style.background = '#0c1938'; _badge.style.color = '#ff6600'; }
  }

  // --- Read item description from page ---
  function getItemDescription() {
    // Try to find the A.K.A. or Description field on the COTS detail page
    const labels = document.querySelectorAll('td, th, label, span');
    for (const el of labels) {
      const text = (el.textContent || '').trim();
      if (text === 'A.K.A.:' || text === 'Description') {
        const next = el.nextElementSibling || el.parentElement.nextElementSibling;
        if (next) {
          const val = (next.textContent || next.value || '').trim();
          if (val && val.length > 1) return val;
        }
      }
    }
    // Fallback: try textarea or input near "Description"
    const textareas = document.querySelectorAll('textarea');
    for (const ta of textareas) {
      if (ta.value && ta.value.trim().length > 2) return ta.value.trim();
    }
    return '';
  }

  // --- Transaction queue (localStorage) ---
  const QUEUE_KEY = 'cots_inv_queue';

  function getQueue() {
    try {
      return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]');
    } catch(e) { return []; }
  }

  function addToQueue(transaction) {
    const queue = getQueue();
    queue.push(transaction);
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
    return queue.length;
  }

  // --- Overlay UI ---
  function createOverlay() {
    const desc = getItemDescription();

    // Backdrop
    const overlay = document.createElement('div');
    overlay.id = 'cots-inv-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
      'background:rgba(0,0,0,0.5);z-index:100000;display:flex;align-items:center;' +
      'justify-content:center;font-family:Segoe UI,sans-serif;';

    // Card
    const card = document.createElement('div');
    card.style.cssText = 'background:#fff;border-radius:12px;padding:30px 40px;' +
      'box-shadow:0 8px 32px rgba(0,0,0,0.3);text-align:center;min-width:360px;max-width:500px;';

    // Item header
    const header = document.createElement('div');
    header.style.cssText = 'margin-bottom:8px;';
    header.innerHTML = '<div style="font-size:28px;font-weight:bold;color:#0c1938;">' + cotsId + '</div>' +
      (desc ? '<div style="font-size:16px;color:#555;margin-top:4px;">' + escHtml(desc) + '</div>' : '');
    card.appendChild(header);

    // Queue count indicator
    const queueCount = getQueue().length;
    if (queueCount > 0) {
      const queueBadge = document.createElement('div');
      queueBadge.style.cssText = 'font-size:12px;color:#888;margin-bottom:16px;';
      queueBadge.textContent = queueCount + ' pending transaction' + (queueCount !== 1 ? 's' : '') + ' in queue';
      card.appendChild(queueBadge);
    }

    const hr = document.createElement('hr');
    hr.style.cssText = 'border:none;border-top:1px solid #e0e0e0;margin:16px 0;';
    card.appendChild(hr);

    // Action buttons row
    const btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex;gap:20px;justify-content:center;margin:20px 0;';

    const removeBtn = createActionButton('REMOVE', '#c00', '#fff', function() {
      showTransactionForm('remove');
    });
    const addBtn = createActionButton('ADD', '#107c10', '#fff', function() {
      showTransactionForm('add');
    });

    btnRow.appendChild(removeBtn);
    btnRow.appendChild(addBtn);
    card.appendChild(btnRow);

    // Close / skip link
    const closeLink = document.createElement('div');
    closeLink.style.cssText = 'margin-top:12px;';
    closeLink.innerHTML = '<a href="#" style="color:#888;font-size:13px;text-decoration:none;">' +
      'Close (just viewing)</a>';
    closeLink.querySelector('a').onclick = function(e) {
      e.preventDefault();
      overlay.remove();
    };
    card.appendChild(closeLink);

    // --- Transaction form (hidden initially) ---
    const formDiv = document.createElement('div');
    formDiv.id = 'cots-inv-form';
    formDiv.style.cssText = 'display:none;margin-top:16px;text-align:left;';
    card.appendChild(formDiv);

    overlay.appendChild(card);
    document.body.appendChild(overlay);

    // Close on backdrop click
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) overlay.remove();
    });

    // ESC to close
    document.addEventListener('keydown', function escHandler(e) {
      if (e.key === 'Escape') {
        overlay.remove();
        document.removeEventListener('keydown', escHandler);
      }
    });
  }

  function createActionButton(label, bg, fg, onClick) {
    const btn = document.createElement('button');
    btn.textContent = label;
    btn.style.cssText = 'background:' + bg + ';color:' + fg + ';border:none;' +
      'padding:36px 80px;font-size:44px;font-weight:bold;border-radius:12px;' +
      'cursor:pointer;min-width:280px;box-shadow:0 4px 16px rgba(0,0,0,0.2);' +
      'transition:transform 0.1s,box-shadow 0.1s;';
    btn.onmouseenter = function() { btn.style.transform = 'scale(1.03)'; };
    btn.onmouseleave = function() { btn.style.transform = 'scale(1)'; };
    btn.onclick = onClick;
    return btn;
  }

  function showTransactionForm(action) {
    const formDiv = document.getElementById('cots-inv-form');
    if (!formDiv) return;

    const isRemove = (action === 'remove');
    const refLabel = isRemove ? 'WO #' : 'Vendor PO #';
    const refPlaceholder = isRemove ? 'e.g. 24-0135' : 'e.g. 243157';
    const actionColor = isRemove ? '#c00' : '#107c10';

    formDiv.style.display = 'block';
    formDiv.innerHTML = '';

    // Reference field
    const refGroup = createFormGroup(refLabel, 'cots-inv-ref', refPlaceholder);
    formDiv.appendChild(refGroup);

    // Quantity field
    const qtyGroup = createFormGroup('Quantity', 'cots-inv-qty', 'e.g. 10');
    formDiv.appendChild(qtyGroup);

    // Submit button
    const submitBtn = document.createElement('button');
    submitBtn.textContent = isRemove ? 'LOG REMOVAL' : 'LOG ADDITION';
    submitBtn.style.cssText = 'background:' + actionColor + ';color:#fff;border:none;' +
      'padding:12px 24px;font-size:16px;font-weight:bold;border-radius:6px;' +
      'cursor:pointer;width:100%;margin-top:12px;';
    submitBtn.onclick = function() {
      const ref = document.getElementById('cots-inv-ref').value.trim();
      const qty = document.getElementById('cots-inv-qty').value.trim();

      if (!ref) {
        highlightField('cots-inv-ref');
        return;
      }

      // Validate reference format
      if (isRemove) {
        // WO format: YY-XXXX (e.g., 24-0135)
        if (!/^\d{2}-\d{4}$/.test(ref)) {
          highlightField('cots-inv-ref', 'WO must be format YY-XXXX (e.g., 24-0135)');
          return;
        }
      } else {
        // Vendor PO format: 6 digits (e.g., 243157)
        if (!/^\d{6}$/.test(ref)) {
          highlightField('cots-inv-ref', 'VPO must be 6 digits (e.g., 243157)');
          return;
        }
      }

      if (!qty || isNaN(parseInt(qty)) || parseInt(qty) <= 0) {
        highlightField('cots-inv-qty');
        return;
      }

      const transaction = {
        cotsId: cotsId,
        cotsType: cotsType,
        action: action,
        reference: ref,
        quantity: parseInt(qty),
        timestamp: new Date().toISOString(),
        url: url
      };

      const count = addToQueue(transaction);
      console.log('[COTS Inv] Logged: ' + JSON.stringify(transaction));
      console.log('[COTS Inv] Queue length: ' + count);

      // Success feedback
      formDiv.innerHTML = '<div style="text-align:center;padding:20px;">' +
        '<div style="font-size:48px;margin-bottom:8px;">' + (isRemove ? '📤' : '📥') + '</div>' +
        '<div style="font-size:18px;font-weight:bold;color:' + actionColor + ';">' +
        (isRemove ? 'Removed' : 'Added') + ' ' + qty + ' × ' + cotsId + '</div>' +
        '<div style="font-size:14px;color:#666;margin-top:4px;">' +
        (isRemove ? 'WO: ' : 'VPO: ') + ref + '</div>' +
        '<div style="font-size:12px;color:#888;margin-top:12px;">' +
        count + ' transaction' + (count !== 1 ? 's' : '') + ' queued for sync</div>' +
        '</div>';

      setStatus('Logged ' + action + ' ×' + qty, 'ok');

      // Auto-close after 2 seconds
      setTimeout(function() {
        const overlay = document.getElementById('cots-inv-overlay');
        if (overlay) overlay.remove();
      }, 2000);
    };
    formDiv.appendChild(submitBtn);

    // Focus the reference field
    setTimeout(function() {
      const refInput = document.getElementById('cots-inv-ref');
      if (refInput) refInput.focus();
    }, 100);
  }

  function createFormGroup(label, id, placeholder) {
    const group = document.createElement('div');
    group.style.cssText = 'margin-bottom:12px;';
    group.innerHTML = '<label style="display:block;font-size:13px;font-weight:bold;' +
      'color:#333;margin-bottom:4px;">' + label + '</label>' +
      '<input type="text" id="' + id + '" placeholder="' + placeholder + '" ' +
      'style="width:100%;padding:10px 12px;font-size:16px;border:2px solid #ccc;' +
      'border-radius:6px;box-sizing:border-box;outline:none;transition:border-color 0.2s;" />';

    // Focus styling
    const input = group.querySelector('input');
    input.onfocus = function() { input.style.borderColor = '#0078d4'; };
    input.onblur = function() { input.style.borderColor = '#ccc'; };

    // Enter key advances to next field or submits
    input.onkeydown = function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        const next = group.nextElementSibling;
        if (next) {
          const nextInput = next.querySelector('input');
          if (nextInput) { nextInput.focus(); return; }
        }
        // No next input — click submit
        const submitBtn = document.querySelector('#cots-inv-form button');
        if (submitBtn) submitBtn.click();
      }
    };

    return group;
  }

  function highlightField(id, message) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.borderColor = '#c00';
    el.focus();
    if (message) {
      let errDiv = el.parentElement.querySelector('.cots-inv-error');
      if (!errDiv) {
        errDiv = document.createElement('div');
        errDiv.className = 'cots-inv-error';
        errDiv.style.cssText = 'color:#c00;font-size:12px;margin-top:4px;';
        el.parentElement.appendChild(errDiv);
      }
      errDiv.textContent = message;
      setTimeout(function() { errDiv.remove(); }, 4000);
    }
    setTimeout(function() { el.style.borderColor = '#ccc'; }, 4000);
  }

  function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // --- Queue viewer (accessible from badge click) ---
  _badge.style.pointerEvents = 'auto';
  _badge.style.cursor = 'pointer';
  _badge.onclick = function() {
    const queue = getQueue();
    if (queue.length === 0) {
      showNotification('No transactions queued', '#666');
      return;
    }
    let summary = 'Pending transactions (' + queue.length + '):\n\n';
    queue.forEach(function(t, i) {
      const time = new Date(t.timestamp).toLocaleTimeString();
      summary += (i+1) + '. ' + t.action.toUpperCase() + ' ' + t.quantity + '× ' +
        t.cotsId + ' — ' + (t.action === 'remove' ? 'WO:' : 'VPO:') + t.reference +
        ' @ ' + time + '\n';
    });
    summary += '\n(Queue will be processed during nightly sync)';
    alert(summary);
  };

  function showNotification(text, bg) {
    const div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:10px;right:10px;z-index:100001;' +
      'background:' + (bg || '#107c10') + ';color:#fff;padding:10px 16px;border-radius:6px;' +
      'font-family:Segoe UI,sans-serif;font-size:13px;' +
      'box-shadow:0 2px 8px rgba(0,0,0,0.3);pointer-events:none;';
    div.textContent = text;
    document.body.appendChild(div);
    setTimeout(function() { div.remove(); }, 4000);
  }

  // --- Launch overlay on page load ---
  // Small delay to let ProShop page finish rendering
  setTimeout(function() {
    setStatus(cotsId + ' loaded');
    createOverlay();
  }, 1500);

})();
