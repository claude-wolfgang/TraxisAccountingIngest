/**
 * ProShop Mobile — Main Application
 * Single-page app with client-side routing.
 */

const App = {
  currentView: 'dashboard',
  statusEl: null,

  init() {
    this.statusEl = document.getElementById('header-status');
    this.checkHealth();
    this.navigate('dashboard');

    // Check health every 30 seconds
    setInterval(() => this.checkHealth(), 30000);
  },

  async checkHealth() {
    try {
      const result = await API.health();
      if (this.statusEl) {
        this.statusEl.className = result.data?.proshop_connected
          ? 'header-status'
          : 'header-status disconnected';
      }
    } catch {
      if (this.statusEl) {
        this.statusEl.className = 'header-status disconnected';
      }
    }
  },

  navigate(view, data) {
    // Clean up camera on view change
    if (this.currentView === 'scanner') Scanner.stop();
    if (this.currentView === 'count') Counter.stop();

    this.currentView = view;
    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.view === view);
    });

    const content = document.getElementById('content');
    switch (view) {
      case 'dashboard': this.renderDashboard(content); break;
      case 'search': this.renderSearch(content); break;
      case 'scanner': this.renderScanner(content); break;
      case 'count': this.renderCount(content); break;
      case 'chat': this.renderChat(content); break;
      default: this.renderDashboard(content);
    }
  },

  // =========================================================================
  // Dashboard
  // =========================================================================

  async renderDashboard(container) {
    container.innerHTML = `
      <div class="dashboard-stats">
        <div class="stat-card" id="stat-open" onclick="App._showOpenWOs()" style="cursor:pointer">
          <div class="spinner"></div>
          <div class="stat-label">Open WOs</div>
        </div>
        <div class="stat-card" id="stat-due" onclick="document.getElementById('due-this-week-list')?.scrollIntoView({behavior:'smooth'})" style="cursor:pointer">
          <div class="spinner"></div>
          <div class="stat-label">Due This Week</div>
        </div>
        <div class="stat-card danger" id="stat-late" onclick="document.getElementById('late-wo-list')?.scrollIntoView({behavior:'smooth'})" style="cursor:pointer">
          <div class="spinner"></div>
          <div class="stat-label">Late</div>
        </div>
        <div class="stat-card" id="stat-total" onclick="App.navigate('search')" style="cursor:pointer">
          <div class="spinner"></div>
          <div class="stat-label">Total Recent</div>
        </div>
      </div>

      <div class="quick-actions">
        <button class="action-btn" onclick="App.navigate('scanner')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
          </svg>
          Scan QR
        </button>
        <button class="action-btn" onclick="App.navigate('search')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          Search
        </button>
        <button class="action-btn" onclick="App.navigate('chat')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          Ask
        </button>
      </div>

      <div class="section-title">Late Work Orders</div>
      <div id="late-wo-list"><div class="loading"><div class="spinner"></div>Loading...</div></div>

      <div class="section-title mt-8">Due This Week</div>
      <div id="due-this-week-list"></div>
    `;

    this._loadDashboard();
  },

  async _loadDashboard() {
    try {
      const result = await API.getDashboard();
      const d = result.data || {};

      // Stats
      const openEl = document.getElementById('stat-open');
      if (openEl) openEl.innerHTML = `<div class="stat-value">${d.open_count ?? '?'}</div><div class="stat-label">Open WOs</div>`;

      const dueEl = document.getElementById('stat-due');
      if (dueEl) dueEl.innerHTML = `<div class="stat-value">${d.due_this_week_count ?? '?'}</div><div class="stat-label">Due This Week</div>`;

      const lateEl = document.getElementById('stat-late');
      if (lateEl) {
        lateEl.className = (d.late_count > 0) ? 'stat-card danger' : 'stat-card';
        lateEl.innerHTML = `<div class="stat-value">${d.late_count ?? '?'}</div><div class="stat-label">Late</div>`;
      }

      const totalEl = document.getElementById('stat-total');
      if (totalEl) totalEl.innerHTML = `<div class="stat-value">${d.total_recent ?? '?'}</div><div class="stat-label">Total Recent</div>`;

      // Late WOs list
      const lateList = document.getElementById('late-wo-list');
      if (lateList) {
        const lateWos = d.late_work_orders || [];
        if (lateWos.length === 0) {
          lateList.innerHTML = '<div class="empty-state">No late work orders</div>';
        } else {
          lateList.innerHTML = lateWos.map(wo => this._renderWoCard(wo)).join('');
        }
      }

      // Due this week list
      const dueList = document.getElementById('due-this-week-list');
      if (dueList) {
        const dueWos = d.due_this_week || [];
        if (dueWos.length === 0) {
          dueList.innerHTML = '<div class="empty-state">No work orders due this week</div>';
        } else {
          dueList.innerHTML = dueWos.map(wo => this._renderWoCard(wo)).join('');
        }
      }

    } catch (err) {
      console.error('Dashboard load error:', err);
      const lateList = document.getElementById('late-wo-list');
      if (lateList) lateList.innerHTML = '<div class="empty-state">Could not load data</div>';
    }
  },

  _openWOsCache: null,

  async _showOpenWOs() {
    const content = document.getElementById('content');
    content.innerHTML = `
      <button class="back-btn" onclick="App.navigate('dashboard')">&#8592; Back</button>
      <div class="section-title">Open Work Orders</div>
      <div class="sort-bar" id="sort-bar">
        <span style="font-size:13px;opacity:0.7">Sort:</span>
        <button class="sort-btn active" data-sort="dueDate">Due Date</button>
        <button class="sort-btn" data-sort="woNumber">WO #</button>
        <button class="sort-btn" data-sort="partNumber">Part #</button>
        <button class="sort-btn" data-sort="status">Status</button>
        <button class="sort-btn" data-sort="qty">Quantity</button>
      </div>
      <div id="open-wo-list"><div class="loading"><div class="spinner"></div>Loading...</div></div>
    `;

    // Wire up sort buttons
    document.getElementById('sort-bar').addEventListener('click', e => {
      const btn = e.target.closest('.sort-btn');
      if (!btn) return;
      document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      this._renderSortedWOs(btn.dataset.sort);
    });

    try {
      const result = await API.getWorkOrders('open');
      this._openWOsCache = result.data?.records || result.data || [];
      this._renderSortedWOs('dueDate');
    } catch (err) {
      const list = document.getElementById('open-wo-list');
      if (list) list.innerHTML = '<div class="empty-state">Could not load data</div>';
    }
  },

  _renderSortedWOs(sortBy) {
    const list = document.getElementById('open-wo-list');
    if (!list || !this._openWOsCache) return;

    const wos = [...this._openWOsCache];

    wos.sort((a, b) => {
      switch (sortBy) {
        case 'dueDate': {
          const da = a.dueDate ? new Date(a.dueDate).getTime() : Infinity;
          const db = b.dueDate ? new Date(b.dueDate).getTime() : Infinity;
          return da - db;
        }
        case 'woNumber':
          return (a.workOrderNumber || '').localeCompare(b.workOrderNumber || '');
        case 'partNumber':
          return (a.part?.partNumber || 'zzz').localeCompare(b.part?.partNumber || 'zzz');
        case 'status':
          return (a.status || '').localeCompare(b.status || '');
        case 'qty':
          return (b.quantityOrdered || 0) - (a.quantityOrdered || 0);
        default:
          return 0;
      }
    });

    if (wos.length === 0) {
      list.innerHTML = '<div class="empty-state">No open work orders</div>';
    } else {
      list.innerHTML = wos.map(wo => this._renderWoCard(wo)).join('');
    }
  },

  _renderWoCard(wo) {
    const status = wo.status || 'Unknown';
    const badgeClass = status === 'Active' ? 'badge-active'
      : status.includes('Complete') ? 'badge-complete'
      : status === 'Shipped' ? 'badge-shipped' : 'badge-active';

    const dueDate = wo.dueDate ? new Date(wo.dueDate).toLocaleDateString() : 'N/A';
    const isLate = wo.dueDate && new Date(wo.dueDate) < new Date() && !['Complete', 'Invoiced', 'Shipped'].includes(status);
    const partNum = wo.part?.partNumber || '';
    const partDesc = wo.part?.partDescription || '';
    const partLine = partNum ? `<div class="card-subtitle">${partNum}${wo.partRev ? ' Rev ' + wo.partRev : ''}${partDesc ? ' — ' + partDesc : ''}</div>` : '';

    return `
      <div class="card" onclick="App.showWorkOrderDetail('${wo.workOrderNumber}')">
        <div class="card-header">
          <span class="card-title">${wo.workOrderNumber}</span>
          <span class="badge ${badgeClass}">${status}</span>
        </div>
        ${partLine}
        <div class="card-footer">
          <span>${isLate ? '<span class="text-danger">LATE</span> - ' : ''}Due: ${dueDate}</span>
          <span>Qty: ${wo.qtyComplete || 0}/${wo.quantityOrdered || 0}</span>
        </div>
      </div>
    `;
  },

  // =========================================================================
  // Work Order Detail
  // =========================================================================

  async showWorkOrderDetail(woNumber) {
    const content = document.getElementById('content');
    content.innerHTML = `
      <button class="back-btn" onclick="App.navigate('${this.currentView}')">&#8592; Back</button>
      <div class="loading"><div class="spinner"></div>Loading ${woNumber}...</div>
    `;

    try {
      const [woRes, opsRes] = await Promise.all([
        API.getWorkOrder(woNumber),
        API.getWorkOrderOps(woNumber),
      ]);

      const wo = woRes.data;
      if (!wo) {
        content.innerHTML = `
          <button class="back-btn" onclick="App.navigate('dashboard')">&#8592; Back</button>
          <div class="empty-state">Work order ${woNumber} not found</div>
        `;
        return;
      }

      const status = wo.status || 'Unknown';
      const badgeClass = status === 'Active' ? 'badge-active'
        : status.includes('Complete') ? 'badge-complete'
        : status === 'Shipped' ? 'badge-shipped' : 'badge-active';
      const dueDate = wo.dueDate ? new Date(wo.dueDate).toLocaleDateString() : 'N/A';
      const isLate = wo.dueDate && new Date(wo.dueDate) < new Date() && !['Complete', 'Invoiced', 'Shipped'].includes(status);

      const ops = opsRes.data?.ops?.records || [];

      const partInfo = wo.part
        ? `<div class="detail-item" style="grid-column: span 2">
             <div class="detail-label">Part</div>
             <div class="detail-value">${wo.part.partNumber}${wo.partRev ? ' Rev ' + wo.partRev : ''}</div>
             <div class="card-subtitle">${wo.part.partDescription || ''}</div>
           </div>`
        : '';

      content.innerHTML = `
        <button class="back-btn" onclick="App.navigate('${this.currentView}')">&#8592; Back</button>

        <div class="detail-header">
          <h2>WO ${wo.workOrderNumber} <span class="badge ${badgeClass}">${status}</span></h2>
          ${isLate ? '<div class="text-danger" style="font-weight:700; margin-top:4px">OVERDUE</div>' : ''}
        </div>

        <div class="detail-grid">
          <div class="detail-item">
            <div class="detail-label">Due Date</div>
            <div class="detail-value ${isLate ? 'text-danger' : ''}">${dueDate}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">Quantity</div>
            <div class="detail-value">${wo.qtyComplete || 0} / ${wo.quantityOrdered || 0}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">Hours Spent</div>
            <div class="detail-value">${wo.hoursTotalSpent != null ? Number(wo.hoursTotalSpent).toFixed(1) : 'N/A'}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">Operations</div>
            <div class="detail-value">${ops.filter(o => o.isOpComplete).length}/${ops.length} done</div>
          </div>
          ${partInfo}
        </div>

        <div class="section-title">Operations</div>
        <div class="ops-list">
          ${ops.length === 0 ? '<div class="empty-state">No operations</div>' :
            ops.map(op => `
              <div class="op-item" onclick="App._showOpDetail('${woNumber}', ${JSON.stringify(op).replace(/'/g, "&#39;").replace(/"/g, '&quot;')})">
                <div class="op-number">${op.operationNumber}</div>
                <div class="op-info">
                  <div class="op-desc">${op.operationDescription || 'No description'}</div>
                  <div class="op-times">
                    Setup: ${op.setupTime ? (op.setupTime / 3600).toFixed(1) + 'h' : '0'}
                    | Run: ${op.runTime ? (op.runTime / 3600).toFixed(1) + 'h' : '0'}
                  </div>
                </div>
                <div class="op-status ${op.isOpComplete ? 'complete' : ''}">
                  ${op.isOpComplete ? '&#10003;' : ''}
                </div>
              </div>
            `).join('')
          }
        </div>
      `;
    } catch (err) {
      content.innerHTML = `
        <button class="back-btn" onclick="App.navigate('dashboard')">&#8592; Back</button>
        <div class="empty-state">Error loading work order: ${err.message}</div>
      `;
    }
  },

  _showOpDetail(woNumber, opJson) {
    const op = typeof opJson === 'string' ? JSON.parse(opJson) : opJson;
    const content = document.getElementById('content');
    content.innerHTML = `
      <button class="back-btn" onclick="App.showWorkOrderDetail('${woNumber}')">&#8592; Back to WO ${woNumber}</button>
      <div class="detail-header">
        <h2>Op ${op.operationNumber}</h2>
        <div class="card-subtitle">${op.operationDescription || ''}</div>
      </div>
      <div class="detail-grid">
        <div class="detail-item">
          <div class="detail-label">Status</div>
          <div class="detail-value">${op.isOpComplete ? '<span class="text-success">Complete</span>' : '<span class="text-accent">In Progress</span>'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Setup Time</div>
          <div class="detail-value">${op.setupTime ? (op.setupTime / 3600).toFixed(1) + ' hrs' : 'N/A'}</div>
        </div>
        <div class="detail-item">
          <div class="detail-label">Run Time</div>
          <div class="detail-value">${op.runTime ? (op.runTime / 3600).toFixed(1) + ' hrs' : 'N/A'}</div>
        </div>
      </div>
    `;
  },

  // =========================================================================
  // Part Detail
  // =========================================================================

  async showPartDetail(partNumber) {
    const content = document.getElementById('content');
    content.innerHTML = `
      <button class="back-btn" onclick="App.navigate('search')">&#8592; Back</button>
      <div class="loading"><div class="spinner"></div>Loading ${partNumber}...</div>
    `;

    try {
      const result = await API.getPartOps(partNumber);
      const parts = result.data || [];

      if (parts.length === 0) {
        content.innerHTML = `
          <button class="back-btn" onclick="App.navigate('search')">&#8592; Back</button>
          <div class="empty-state">Part ${partNumber} not found</div>
        `;
        return;
      }

      const part = parts[0];
      const ops = part.operations?.records || [];

      content.innerHTML = `
        <button class="back-btn" onclick="App.navigate('search')">&#8592; Back</button>
        <div class="detail-header">
          <h2>${part.partNumber}</h2>
          <div class="card-subtitle">${part.partDescription || ''}</div>
        </div>

        <div class="section-title">Operations (${ops.length})</div>
        <div class="ops-list">
          ${ops.length === 0 ? '<div class="empty-state">No operations</div>' :
            ops.map(op => `
              <div class="op-item">
                <div class="op-number">${op.opNumber}</div>
                <div class="op-info">
                  <div class="op-desc">${op.operationDescription || 'No description'}</div>
                </div>
              </div>
            `).join('')
          }
        </div>
      `;
    } catch (err) {
      content.innerHTML = `
        <button class="back-btn" onclick="App.navigate('search')">&#8592; Back</button>
        <div class="empty-state">Error loading part: ${err.message}</div>
      `;
    }
  },

  // =========================================================================
  // Search
  // =========================================================================

  renderSearch(container) {
    container.innerHTML = `
      <div class="search-container">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input class="search-input" id="search-input" type="text"
          placeholder="WO number, part number, or keyword..."
          autocomplete="off" autofocus>
      </div>
      <div id="search-results"></div>
    `;

    const input = document.getElementById('search-input');
    let timeout;
    input.addEventListener('input', () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => this._doSearch(input.value), 400);
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        clearTimeout(timeout);
        this._doSearch(input.value);
      }
    });
  },

  async _doSearch(query) {
    if (!query.trim()) {
      document.getElementById('search-results').innerHTML = '';
      return;
    }

    const resultsEl = document.getElementById('search-results');
    resultsEl.innerHTML = '<div class="loading"><div class="spinner"></div>Searching...</div>';

    try {
      const result = await API.search(query);
      const data = result.data || {};
      const wos = data.work_orders || [];
      const parts = data.parts || [];

      if (wos.length === 0 && parts.length === 0) {
        resultsEl.innerHTML = '<div class="empty-state">No results found</div>';
        return;
      }

      let html = '';
      if (wos.length > 0) {
        html += '<div class="section-title">Work Orders</div>';
        html += wos.map(wo => this._renderWoCard(wo)).join('');
      }
      if (parts.length > 0) {
        html += '<div class="section-title mt-8">Parts</div>';
        html += parts.map(p => `
          <div class="card" onclick="App.showPartDetail('${p.partNumber}')">
            <div class="card-title">${p.partNumber}</div>
            <div class="card-body">${p.partDescription || ''}</div>
          </div>
        `).join('');
      }
      resultsEl.innerHTML = html;
    } catch (err) {
      resultsEl.innerHTML = `<div class="empty-state">Search failed: ${err.message}</div>`;
    }
  },

  // =========================================================================
  // Scanner
  // =========================================================================

  renderScanner(container) {
    container.innerHTML = `
      <div class="section-title">Scan QR Code</div>
      <div class="scanner-container">
        <video id="scanner-video" playsinline></video>
        <div class="scanner-overlay">
          <div class="scanner-frame"></div>
        </div>
      </div>
      <div id="scanner-result" class="scanner-result">
        Point your camera at a ProShop QR code
      </div>
      <div style="text-align:center; margin-top:12px">
        <input class="search-input" id="manual-wo-input" type="text"
          placeholder="Or type WO number manually..."
          style="text-align:center;">
      </div>
    `;

    const video = document.getElementById('scanner-video');
    Scanner.start(video);

    const manualInput = document.getElementById('manual-wo-input');
    manualInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && manualInput.value.trim()) {
        Scanner.stop();
        App.showWorkOrderDetail(manualInput.value.trim());
      }
    });
  },

  showScanResult(text) {
    const el = document.getElementById('scanner-result');
    if (!el) return;

    const isUrl = /^https?:\/\//i.test(text);

    el.innerHTML = `
      <div class="card">
        <div class="card-title">Scanned</div>
        <div class="card-body" style="word-break:break-all">${text}</div>
        ${isUrl ? `<button class="action-btn" style="margin-top:12px;width:100%" onclick="window.open('${text.replace(/'/g, "\\'")}', '_blank', 'noopener')">Open Link</button>` : ''}
        <button class="action-btn" style="margin-top:8px;width:100%" onclick="App.navigate('scanner')">Scan Again</button>
      </div>`;
  },

  // =========================================================================
  // Count (Vision)
  // =========================================================================

  renderCount(container) {
    container.innerHTML = `
      <div class="section-title">Count Parts</div>
      <div class="counter-container">
        <video id="counter-video" playsinline></video>
        <div id="count-overlay" class="count-overlay"></div>
      </div>
      <div class="counter-controls">
        <button class="count-btn" id="count-btn" onclick="Counter.count()">Count</button>
        <button class="auto-btn" id="auto-btn" onclick="App._toggleAutoCount()">Auto</button>
      </div>
      <div class="counter-context">
        <input class="search-input" id="count-context" type="text"
          placeholder="Optional: what to count (e.g. aluminum spacers)"
          style="text-align:center; padding-left:16px;">
      </div>
    `;

    const video = document.getElementById('counter-video');
    Counter.start(video);
  },

  _toggleAutoCount() {
    const btn = document.getElementById('auto-btn');
    if (Counter.isAutoRunning()) {
      Counter.stopAuto();
      if (btn) btn.classList.remove('active');
    } else {
      Counter.startAuto();
      if (btn) btn.classList.add('active');
    }
  },

  // =========================================================================
  // Chat
  // =========================================================================

  renderChat(container) {
    container.innerHTML = `
      <div class="chat-messages" id="chat-messages" style="height: calc(100vh - 220px); overflow-y: auto;"></div>
      <div class="chat-input-area">
        <input class="chat-input" id="chat-input" type="text"
          placeholder="Ask about work orders, parts..." autocomplete="off">
        <button class="chat-send" id="chat-send" onclick="App._sendChat()">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M2 21l21-9L2 3v7l15 2-15 2z"/>
          </svg>
        </button>
      </div>
    `;

    const messagesEl = document.getElementById('chat-messages');
    const inputEl = document.getElementById('chat-input');
    Chat.init(messagesEl, inputEl);

    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter') App._sendChat();
    });

    inputEl.focus();
  },

  async _sendChat() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    await Chat.send(message);
  },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
