// ==UserScript==
// @name         ProShop Bridge — Auto-Fill Helper
// @namespace    https://traxismfg.adionsystems.com
// @version      1.6.0
// @description  Auto-fills written descriptions (via localhost fetch) and fixes G-Code Tool # on Sequence Detail pages
// @author       Traxis Manufacturing
// @match        https://traxismfg.adionsystems.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function() {
  'use strict';

  // With @grant GM_xmlhttpRequest, script runs in Tampermonkey sandbox.
  // Use unsafeWindow to access page globals (CKEditor, tinymce, etc.)
  const _win = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;

  // Skip frameset pages — the script will run inside each child frame instead
  if (document.querySelector('frameset')) {
    console.log('[ProShop Bridge TM] Frameset detected, deferring to child frames');
    return;
  }

  const url = window.location.href;

  // ProShop uses framesets — bridge params (psBridge=, writtenDescription) are
  // only on the top-level URL that Fusion opened, not on child frame URLs.
  // Check window.top.location.href so child frames can still detect bridge mode.
  let topUrl = url;
  try { topUrl = window.top.location.href; } catch (e) { /* cross-origin guard */ }
  const pushedByBridge = url.includes('psBridge=') || topUrl.includes('psBridge=');

  // --- Status badge (only shown when bridge is actively pushing) ---
  let _badge = null;

  function ensureBadge() {
    if (_badge) return;
    _badge = document.createElement('div');
    _badge.id = 'proshop-bridge-badge';
    _badge.style.cssText = 'position:fixed;bottom:8px;left:8px;z-index:99999;' +
      'background:#0c1938;color:#ff6600;padding:4px 10px;border-radius:4px;' +
      'font-family:Segoe UI,sans-serif;font-size:11px;font-weight:bold;' +
      'box-shadow:0 1px 4px rgba(0,0,0,0.3);opacity:0.9;pointer-events:none;' +
      'transition:background 0.3s,color 0.3s;';
    _badge.textContent = 'PS Bridge: Active';
    document.body.appendChild(_badge);
  }

  function setStatus(text, color) {
    ensureBadge();
    _badge.textContent = 'PS Bridge: ' + text;
    if (color === 'ok')    { _badge.style.background = '#107c10'; _badge.style.color = '#fff'; }
    else if (color === 'warn') { _badge.style.background = '#d48000'; _badge.style.color = '#fff'; }
    else if (color === 'err')  { _badge.style.background = '#c00';    _badge.style.color = '#fff'; }
    else { _badge.style.background = '#0c1938'; _badge.style.color = '#ff6600'; }
  }

  const isWrittenDesc = url.includes('writtenDescription') || topUrl.includes('writtenDescription');

  // Extract bridge marker ID for cross-frame mutex
  const bridgeMatch = topUrl.match(/psBridge=([^&]+)/);
  const bridgeId = bridgeMatch ? bridgeMatch[1] : null;

  if (isWrittenDesc && pushedByBridge && bridgeId) {
    // Phase tracking: checkout reloads the page, so the script runs twice.
    // Phase 1 (no key): fetch content, click checkout → page reloads
    // Phase 2 ("checked_out"): skip checkout, fill editor, save
    // Phase 3 ("done"): skip everything
    const phaseKey = 'psBridge_phase_' + bridgeId;
    const phase = localStorage.getItem(phaseKey);
    if (phase === 'done') {
      console.log('[ProShop Bridge TM] Bridge ' + bridgeId + ' already completed, skipping.');
      return;
    }
    // Clean up phase key after 120s (in case of errors)
    setTimeout(() => { try { localStorage.removeItem(phaseKey); } catch(e) {} }, 120000);

    setStatus('Auto-paste ready');
    handleWrittenDescription(phaseKey, phase);
  }

  // Always check for sequence detail table on any ProShop page (content-based detection)
  // ProShop loads sequence detail in frames/tabs without a distinct URL
  // Skip on written description pages to avoid interfering with auto-paste
  if (!isWrittenDesc) {
    setTimeout(() => {
      try {
        const allTh = document.querySelectorAll('th');
        let found = false;
        for (const th of allTh) {
          const text = (th.textContent || '').trim();
          if (text.includes('Seq') && text.includes('#')) {
            found = true;
            break;
          }
        }
        if (found) {
          console.log('[ProShop Bridge TM] Found Seq # table — running sequence detail handler');
          handleSequenceDetail();
        }
      } catch (e) {
        console.log('[ProShop Bridge TM] Sequence detect error:', e.message);
      }
    }, 3000);
  }

  // ================================================================
  //  WRITTEN DESCRIPTION — fetch from local server (clipboard-free)
  // ================================================================
  function handleWrittenDescription(phaseKey, phase) {
    const MARKER_PREFIX = '<!--PROSHOP_BRIDGE:';
    const WAIT_FOR_PAGE_MS = 2500;
    const WAIT_FOR_EDITOR_MS = 20000;

    // Extract bridgePort from URL (set by Python's local server)
    const portMatch = topUrl.match(/bridgePort=(\d+)/);
    const bridgePort = portMatch ? portMatch[1] : null;

    const isPostCheckout = (phase === 'checked_out');
    console.log('[ProShop Bridge TM] Written description page detected' +
                (isPostCheckout ? ' (post-checkout reload)' : ' (initial load)'));
    setStatus(isPostCheckout ? 'Post-checkout...' : 'Waiting for page...', 'warn');

    // Fetch HTML content from local server (via GM_xmlhttpRequest to bypass mixed content)
    function fetchFromServer() {
      return new Promise((resolve) => {
        if (!bridgePort) { resolve(null); return; }
        console.log('[ProShop Bridge TM] Fetching content from localhost:' + bridgePort);
        setStatus('Fetching from bridge...');
        GM_xmlhttpRequest({
          method: 'GET',
          url: 'http://127.0.0.1:' + bridgePort + '/',
          timeout: 10000,
          onload: function(resp) {
            if (resp.status === 200 && resp.responseText && resp.responseText.startsWith(MARKER_PREFIX)) {
              console.log('[ProShop Bridge TM] Got ' + resp.responseText.length + ' bytes from local server');
              resolve(resp.responseText);
            } else {
              console.log('[ProShop Bridge TM] Server response invalid (status=' + resp.status + ')');
              resolve(null);
            }
          },
          onerror: function(err) {
            console.log('[ProShop Bridge TM] Local server fetch failed:', err.statusText || 'network error');
            resolve(null);
          },
          ontimeout: function() {
            console.log('[ProShop Bridge TM] Local server fetch timed out');
            resolve(null);
          }
        });
      });
    }

    // Core logic — fetch content, checkout if needed, set editor, save
    async function doPaste() {
      // Fetch HTML from Python's local server
      const rawContent = await fetchFromServer();
      if (!rawContent) {
        console.log('[ProShop Bridge TM] No ProShop Bridge data available, skipping.');
        setStatus('No data available', 'warn');
        showPasteButton(MARKER_PREFIX);
        return;
      }
      console.log('[ProShop Bridge TM] Found ProShop Bridge data, auto-filling...');
      const markerEnd = rawContent.indexOf('-->');
      const htmlContent = markerEnd >= 0 ? rawContent.substring(markerEnd + 4) : rawContent;

      // Checkout if needed (only on initial load, not post-checkout)
      if (!isPostCheckout) {
        const checkoutBtn = findButtonByText('Checkout', 'CHECKOUT', 'Check Out');
        if (checkoutBtn) {
          // Mark phase so the post-reload script knows to skip checkout
          localStorage.setItem(phaseKey, 'checked_out');
          setStatus('Checking out...');
          console.log('[ProShop Bridge TM] Clicking Checkout (page will reload)...');
          checkoutBtn.click();
          // If checkout causes a page reload, this script dies here.
          // The reloaded page will re-run with phase='checked_out'.
          // If it DOESN'T reload (AJAX checkout), continue after a wait.
          await sleep(5000);
          console.log('[ProShop Bridge TM] Checkout did not reload — continuing in same page');
        } else {
          console.log('[ProShop Bridge TM] No Checkout button found (may already be checked out)');
        }
      } else {
        console.log('[ProShop Bridge TM] Skipping checkout (post-reload)');
      }

      // Wait for CKEditor to initialize
      setStatus('Waiting for editor...', 'warn');
      console.log('[ProShop Bridge TM] Waiting for editor to initialize...');
      const editor = await waitForCKEditor(WAIT_FOR_EDITOR_MS);

      if (editor) {
        setStatus('Setting editor content...');
        const existing = editor.getData() || '';
        const combined = htmlContent + (existing ? '<hr>' + existing : '');
        await new Promise((resolve) => {
          editor.setData(combined, { callback: function() {
            console.log('[ProShop Bridge TM] CKEditor setData callback fired');
            resolve();
          }});
          setTimeout(resolve, 3000);
        });
        editor.fire('change');
        if (editor.updateElement) editor.updateElement();
        console.log('[ProShop Bridge TM] Content set via CKEditor (' + editor.name + ')');
      } else {
        setStatus('Setting editor content...');
        const editorSet = await setEditorContent(htmlContent);
        if (!editorSet) {
          console.log('[ProShop Bridge TM] Could not find editor, showing manual paste button');
          setStatus('Editor not found', 'err');
          showPasteButton(MARKER_PREFIX);
          return;
        }
      }

      console.log('[ProShop Bridge TM] Content set successfully.');
      await sleep(1000);
      const saveBtn = findButtonByText('Save', 'SAVE');
      if (saveBtn) {
        setStatus('Saving...');
        console.log('[ProShop Bridge TM] Clicking Save...');
        saveBtn.click();
        setStatus('Done!', 'ok');
        console.log('[ProShop Bridge TM] Done!');
      } else {
        setStatus('Save manually', 'warn');
        console.log('[ProShop Bridge TM] No Save button found — please save manually.');
      }
      // Mark as done
      localStorage.setItem(phaseKey, 'done');
    }

    setTimeout(async () => {
      setStatus('Fetching content...');
      await doPaste();
    }, isPostCheckout ? 1000 : WAIT_FOR_PAGE_MS);
  }

  // ================================================================
  //  SEQUENCE DETAIL — move T## from description to G-Code Tool #
  // ================================================================
  function handleSequenceDetail() {
    console.log('[ProShop Bridge TM] Sequence Detail page detected, waiting for page load...');

    setTimeout(() => {
      try {
        sortSequenceRows();
        // Delay tool fix to let DataTables redraw after sort click
        setTimeout(() => {
          try { fixGcodeToolNumbers(); }
          catch (err) { console.error('[ProShop Bridge TM] fixGcodeToolNumbers error:', err); }
        }, 1000);
      } catch (err) {
        console.error('[ProShop Bridge TM] Sequence Detail error:', err);
      }
    }, 2500);
  }

  function sortSequenceRows() {
    // Find the Seq # column header and its table
    const allHeaders = document.querySelectorAll('th');
    let seqHeader = null;

    for (const th of allHeaders) {
      const text = (th.textContent || '').trim();
      if (text.includes('Seq') && text.includes('#')) {
        seqHeader = th;
        break;
      }
    }

    if (!seqHeader) {
      console.log('[ProShop Bridge TM] Could not find Seq # column header');
      return;
    }

    const table = seqHeader.closest('table');
    if (!table) {
      console.log('[ProShop Bridge TM] Could not find table from Seq # header');
      return;
    }

    console.log('[ProShop Bridge TM] Seq # header found, classes: ' + seqHeader.className);

    // Sorting is disabled on this column — must sort manually via DOM
    const tbody = table.querySelector('tbody');
    if (!tbody) {
      console.log('[ProShop Bridge TM] No tbody found');
      return;
    }

    const rows = Array.from(tbody.querySelectorAll('tr'));
    if (rows.length < 2) {
      console.log('[ProShop Bridge TM] Only ' + rows.length + ' row(s), skip sort');
      return;
    }

    // Find Seq # column index
    const headerRow = table.querySelector('thead tr') || table.querySelector('tr:first-child');
    let seqColIdx = 0;
    if (headerRow) {
      const ths = headerRow.querySelectorAll('th, td');
      for (let i = 0; i < ths.length; i++) {
        const t = (ths[i].textContent || '').trim();
        if (t.includes('Seq') && t.includes('#')) { seqColIdx = i; break; }
      }
    }
    console.log('[ProShop Bridge TM] Seq # column index: ' + seqColIdx);

    // Sort rows by numeric Seq # value
    rows.sort((a, b) => {
      const aCells = a.querySelectorAll('td');
      const bCells = b.querySelectorAll('td');
      const aVal = aCells.length > seqColIdx ? parseInt(aCells[seqColIdx].textContent.trim(), 10) || 9999 : 9999;
      const bVal = bCells.length > seqColIdx ? parseInt(bCells[seqColIdx].textContent.trim(), 10) || 9999 : 9999;
      return aVal - bVal;
    });

    // Re-append in sorted order
    for (const row of rows) {
      tbody.appendChild(row);
    }

    // Verify
    const first5 = rows.slice(0, 5).map(r => {
      const c = r.querySelectorAll('td')[seqColIdx];
      return c ? c.textContent.trim() : '?';
    });
    console.log('[ProShop Bridge TM] Seq # after DOM sort: ' + first5.join(', '));
  }

  function fixGcodeToolNumbers() {
    // Find the table headers to identify column indices
    const headers = document.querySelectorAll('th, td.header, .headerRow td');
    let seqDescColIdx = -1;
    let gcodeToolColIdx = -1;

    // Try to find columns by header text in the table
    const allTables = document.querySelectorAll('table');
    let targetTable = null;

    for (const table of allTables) {
      const headerCells = table.querySelectorAll('tr:first-child th, tr:first-child td, thead th, thead td');
      headerCells.forEach((cell, idx) => {
        const text = (cell.textContent || '').trim().toLowerCase();
        if (text.includes('sequence description')) seqDescColIdx = idx;
        if (text.includes('g-code tool') || text.includes('gcode tool')) gcodeToolColIdx = idx;
      });
      if (seqDescColIdx >= 0 && gcodeToolColIdx >= 0) {
        targetTable = table;
        break;
      }
    }

    if (!targetTable || seqDescColIdx < 0 || gcodeToolColIdx < 0) {
      console.log('[ProShop Bridge TM] Could not find Sequence Description or G-Code Tool # columns');
      console.log('[ProShop Bridge TM] seqDescCol=' + seqDescColIdx + ', gcodeToolCol=' + gcodeToolColIdx);

      // Fallback: try to find inputs by scanning all rows for T## pattern
      fixGcodeToolFallback();
      return;
    }

    console.log('[ProShop Bridge TM] Found columns: SeqDesc=' + seqDescColIdx + ', GCodeTool=' + gcodeToolColIdx);

    // Process each data row
    const rows = targetTable.querySelectorAll('tbody tr, tr');
    let fixCount = 0;

    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      if (cells.length <= Math.max(seqDescColIdx, gcodeToolColIdx)) continue;

      const descCell = cells[seqDescColIdx];
      const gcodeCell = cells[gcodeToolColIdx];

      // Try input first, fall back to cell text
      const descInput = descCell.querySelector('input, textarea');
      const gcodeInput = gcodeCell.querySelector('input, textarea');
      const descVal = descInput ? (descInput.value || '') : (descCell.textContent || '').trim();
      const match = descVal.match(/^T(\d+):\s*/);

      if (match) {
        const toolNum = match[1];
        const cleanDesc = descVal.replace(/^T\d+:\s*/, '');

        // Set G-Code Tool # (input or text cell)
        // Overwrite G-Code Tool # — Fusion data is authoritative
        if (gcodeInput) {
          gcodeInput.value = toolNum;
          triggerInputEvent(gcodeInput);
        } else {
          gcodeCell.textContent = toolNum;
        }
        console.log('[ProShop Bridge TM] Set G-Code Tool # = ' + toolNum);

        // Clean up description
        if (descInput) {
          descInput.value = cleanDesc;
          triggerInputEvent(descInput);
        } else {
          descCell.textContent = cleanDesc;
        }
        fixCount++;
        console.log('[ProShop Bridge TM] Cleaned description: "' + cleanDesc + '"');
      }
    }

    if (fixCount > 0) {
      console.log('[ProShop Bridge TM] Fixed ' + fixCount + ' row(s)');
      showNotification('ProShop Bridge: Moved T# to G-Code Tool column (' + fixCount + ' rows)');
    } else {
      console.log('[ProShop Bridge TM] No T## prefixes found in descriptions.');
    }
  }

  function fixGcodeToolFallback() {
    // Fallback: scan all input fields on the page for T## pattern
    console.log('[ProShop Bridge TM] Using fallback input scan...');
    const allInputs = document.querySelectorAll('input[type="text"], input:not([type])');
    const descInputs = [];
    const gcodeInputs = [];

    // Group inputs by their row (parent tr)
    const rowMap = new Map();
    for (const input of allInputs) {
      const row = input.closest('tr');
      if (!row) continue;
      if (!rowMap.has(row)) rowMap.set(row, []);
      rowMap.get(row).push(input);
    }

    let fixCount = 0;
    for (const [row, inputs] of rowMap) {
      // Find the input with a T##: pattern
      for (let i = 0; i < inputs.length; i++) {
        const val = inputs[i].value || '';
        const match = val.match(/^T(\d+):\s*/);
        if (match) {
          const toolNum = match[1];
          const cleanDesc = val.replace(/^T\d+:\s*/, '');

          // Look for an empty input nearby (likely the G-Code Tool # field)
          // It should be a few columns to the right
          for (let j = i + 1; j < Math.min(i + 4, inputs.length); j++) {
            if (!inputs[j].value || inputs[j].value.trim() === '') {
              inputs[j].value = toolNum;
              triggerInputEvent(inputs[j]);
              console.log('[ProShop Bridge TM] (fallback) Set G-Code Tool # = ' + toolNum);
              break;
            }
          }

          inputs[i].value = cleanDesc;
          triggerInputEvent(inputs[i]);
          fixCount++;
          break;
        }
      }
    }

    if (fixCount > 0) {
      console.log('[ProShop Bridge TM] (fallback) Fixed ' + fixCount + ' row(s). Remember to save!');
      showNotification('ProShop Bridge: Moved T# to G-Code Tool column (' + fixCount + ' rows). Save to keep changes.');
    }
  }

  function triggerInputEvent(input) {
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function showNotification(text) {
    const div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;' +
      'background:#107c10;color:#fff;padding:10px 16px;border-radius:6px;' +
      'font-family:Segoe UI,sans-serif;font-size:13px;' +
      'box-shadow:0 2px 8px rgba(0,0,0,0.3);pointer-events:none;';
    div.textContent = text;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 6000);
  }

  // ================================================================
  //  Wait for CKEditor to initialize (polls main page + iframes)
  // ================================================================
  function waitForCKEditor(timeoutMs) {
    return new Promise((resolve) => {
      const start = Date.now();
      const interval = setInterval(() => {
        // Check main page
        if (typeof _win.CKEDITOR !== 'undefined' && _win.CKEDITOR.instances) {
          const names = Object.keys(_win.CKEDITOR.instances);
          for (const name of names) {
            const inst = _win.CKEDITOR.instances[name];
            if (inst.status === 'ready' || inst.status === 'loaded') {
              clearInterval(interval);
              console.log('[ProShop Bridge TM] CKEditor ready: ' + name + ' (status: ' + inst.status + ')');
              resolve(inst);
              return;
            }
          }
          // CKEditor exists but not ready yet — also listen for instanceReady
          if (names.length > 0 && !interval._listenerAdded) {
            interval._listenerAdded = true;
            _win.CKEDITOR.on('instanceReady', function(evt) {
              clearInterval(interval);
              console.log('[ProShop Bridge TM] CKEditor instanceReady: ' + evt.editor.name);
              resolve(evt.editor);
            });
          }
        }
        // Check inside iframes
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
          try {
            const win = iframe.contentWindow;
            if (win && typeof win.CKEDITOR !== 'undefined' && win.CKEDITOR.instances) {
              const names = Object.keys(win.CKEDITOR.instances);
              for (const name of names) {
                const inst = win.CKEDITOR.instances[name];
                if (inst.status === 'ready' || inst.status === 'loaded') {
                  clearInterval(interval);
                  console.log('[ProShop Bridge TM] CKEditor ready in iframe: ' + name);
                  resolve(inst);
                  return;
                }
              }
            }
          } catch (e) {}
        }
        if (Date.now() - start > timeoutMs) {
          clearInterval(interval);
          console.log('[ProShop Bridge TM] CKEditor wait timed out after ' + timeoutMs + 'ms');
          resolve(null);
        }
      }, 500);
    });
  }

  // ================================================================
  //  Editor detection — tries CKEditor, TinyMCE, contenteditable, iframe
  // ================================================================
  async function setEditorContent(newHtml) {
    if (typeof _win.CKEDITOR !== 'undefined' && _win.CKEDITOR.instances) {
      const names = Object.keys(_win.CKEDITOR.instances);
      if (names.length > 0) {
        const editor = _win.CKEDITOR.instances[names[0]];
        const existing = editor.getData() || '';
        const combined = newHtml + (existing ? '<hr>' + existing : '');
        editor.setData(combined);
        console.log('[ProShop Bridge TM] Set via CKEditor (' + names[0] + ')');
        return true;
      }
    }

    if (typeof _win.tinymce !== 'undefined' && _win.tinymce.editors && _win.tinymce.editors.length > 0) {
      const editor = _win.tinymce.editors[0];
      const existing = editor.getContent() || '';
      const combined = newHtml + (existing ? '<hr>' + existing : '');
      editor.setContent(combined);
      console.log('[ProShop Bridge TM] Set via TinyMCE');
      return true;
    }

    const editables = document.querySelectorAll('[contenteditable="true"]');
    if (editables.length > 0) {
      const el = editables[0];
      const existing = el.innerHTML || '';
      el.innerHTML = newHtml + (existing ? '<hr>' + existing : '');
      console.log('[ProShop Bridge TM] Set via contenteditable');
      return true;
    }

    const iframes = document.querySelectorAll('iframe');
    for (const iframe of iframes) {
      try {
        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
        const iframeWin = iframe.contentWindow;

        // Check for CKEditor inside iframe
        if (iframeWin && typeof iframeWin.CKEDITOR !== 'undefined' && iframeWin.CKEDITOR.instances) {
          const names = Object.keys(iframeWin.CKEDITOR.instances);
          if (names.length > 0) {
            const editor = iframeWin.CKEDITOR.instances[names[0]];
            const existing = editor.getData() || '';
            const combined = newHtml + (existing ? '<hr>' + existing : '');
            editor.setData(combined);
            console.log('[ProShop Bridge TM] Set via CKEditor inside iframe (' + names[0] + ')');
            return true;
          }
        }

        // Check for TinyMCE inside iframe
        if (iframeWin && typeof iframeWin.tinymce !== 'undefined' && iframeWin.tinymce.editors && iframeWin.tinymce.editors.length > 0) {
          const editor = iframeWin.tinymce.editors[0];
          const existing = editor.getContent() || '';
          const combined = newHtml + (existing ? '<hr>' + existing : '');
          editor.setContent(combined);
          console.log('[ProShop Bridge TM] Set via TinyMCE inside iframe');
          return true;
        }

        // Check for contenteditable divs inside iframe
        const iframeEditables = iframeDoc.querySelectorAll('[contenteditable="true"]');
        if (iframeEditables.length > 0) {
          const el = iframeEditables[0];
          const existing = el.innerHTML || '';
          el.innerHTML = newHtml + (existing ? '<hr>' + existing : '');
          console.log('[ProShop Bridge TM] Set via contenteditable inside iframe');
          return true;
        }

        // Check if iframe body itself is contentEditable
        const body = iframeDoc.body;
        if (body && body.contentEditable === 'true') {
          const existing = body.innerHTML || '';
          body.innerHTML = newHtml + (existing ? '<hr>' + existing : '');
          console.log('[ProShop Bridge TM] Set via iframe body contentEditable');
          return true;
        }
      } catch (e) {}
    }

    return false;
  }

  // ================================================================
  //  Button finder
  // ================================================================
  function findButtonByText(...labels) {
    const lower = labels.map(l => l.toLowerCase());
    const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn, .button');
    for (const btn of buttons) {
      const text = (btn.textContent || btn.value || '').trim().toLowerCase();
      for (const label of lower) {
        if (text === label || text.includes(label)) return btn;
      }
    }
    const links = document.querySelectorAll('a, span');
    for (const el of links) {
      const text = (el.textContent || '').trim().toLowerCase();
      for (const label of lower) {
        if (text === label) return el;
      }
    }
    return null;
  }

  // ================================================================
  //  Fallback paste button
  // ================================================================
  function showPasteButton(MARKER_PREFIX) {
    if (document.getElementById('proshop-bridge-paste-btn')) return;  // already shown
    const div = document.createElement('div');
    div.id = 'proshop-bridge-paste-btn';
    div.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;' +
      'background:#0078d4;color:#fff;padding:10px 16px;border-radius:6px;' +
      'font-family:Segoe UI,sans-serif;font-size:13px;cursor:pointer;' +
      'box-shadow:0 2px 8px rgba(0,0,0,0.3);';
    div.textContent = 'Paste Written Description';
    div.title = 'Click to paste written description from ProShop Bridge';
    div.onclick = async function() {
      try {
        const clipText = await navigator.clipboard.readText();
        if (!clipText || !clipText.startsWith(MARKER_PREFIX)) {
          div.textContent = 'No data on clipboard';
          div.style.background = '#c00';
          setTimeout(() => div.remove(), 3000);
          return;
        }
        const markerEnd = clipText.indexOf('-->');
        const htmlContent = markerEnd >= 0 ? clipText.substring(markerEnd + 4) : clipText;
        const ok = await setEditorContent(htmlContent);
        if (ok) {
          div.textContent = 'Pasted!';
          div.style.background = '#107c10';
          try { await navigator.clipboard.writeText(''); } catch(e) {}
          setTimeout(() => div.remove(), 2000);
        } else {
          div.textContent = 'Editor not found';
          div.style.background = '#c00';
          setTimeout(() => div.remove(), 3000);
        }
      } catch(e) {
        div.textContent = 'Clipboard denied';
        div.style.background = '#c00';
        setTimeout(() => div.remove(), 3000);
      }
    };
    document.body.appendChild(div);
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
})();
