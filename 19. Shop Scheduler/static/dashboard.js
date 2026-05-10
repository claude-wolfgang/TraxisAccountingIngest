// ── Dashboard — Stats, Machine Status, Flags ────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Allow ?tab=program|material|tools to deep-link to a needs tab
    const urlTab = new URLSearchParams(window.location.search).get('tab');
    if (urlTab && ['program', 'material', 'tools', 'runtimes'].includes(urlTab)) {
        activeNeedsTab = urlTab;
        document.querySelectorAll('.needs-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === urlTab);
        });
    }
    initNeedsTabs();
    loadDashboard();
    setInterval(loadDashboard, 30000);
});

let needsData = null;
let activeNeedsTab = 'program';

async function loadDashboard() {
    try {
        const [stats, machines, blocks, flags, syncLog, needs] = await Promise.all([
            fetchJSON('/api/stats'),
            fetchJSON('/api/machines'),
            fetchJSON('/api/blocks'),
            fetchJSON('/api/flags?status=open'),
            fetchJSON('/api/sync/log'),
            fetchJSON('/api/needs'),
        ]);

        needsData = needs;

        renderStats(stats);
        renderMachineCards(machines, blocks);
        renderFlags(flags);
        renderPastDue(stats);
        renderSyncLog(syncLog);
        renderNeedsCounts(needs.counts);
        renderNeedsList(activeNeedsTab);

        document.getElementById('sync-dot').classList.remove('syncing');
        document.getElementById('sync-text').textContent = 'Live';
    } catch (e) {
        document.getElementById('sync-text').textContent = 'Error';
        console.error('Dashboard load failed:', e);
    }
}

function renderStats(stats) {
    document.getElementById('stat-active-wos').textContent = stats.active_wos;
    document.getElementById('stat-past-due').textContent = stats.past_due;
    document.getElementById('stat-backlog-hours').textContent = stats.backlog_hours + 'h';
    document.getElementById('stat-unscheduled').textContent = stats.unscheduled_ops;
    document.getElementById('stat-machines-running').textContent = stats.machines_running;
    document.getElementById('stat-open-flags').textContent = stats.open_flags;
    document.getElementById('stat-completed-today').textContent = stats.completed_today;
}

function renderMachineCards(machines, blocks) {
    const container = document.getElementById('machine-cards');

    container.innerHTML = machines.map(m => {
        const machineBlocks = blocks.filter(b => b.resourceId === m.id);
        const running = machineBlocks.find(b => b.extendedProps?.status === 'running');
        const scheduled = machineBlocks.filter(b => b.extendedProps?.status === 'scheduled').length;
        const isRunning = !!running;

        let jobInfo = '';
        if (running) {
            const p = running.extendedProps;
            const progress = p.progress || 0;
            jobInfo = `
                <div style="margin-top:8px">
                    <div style="font-weight:500">WO${p.wo_number} Op${p.op_number}</div>
                    <div style="font-size:12px; color:var(--text-muted)">${p.part_name || p.op_name || ''}</div>
                    <div style="font-size:12px; margin-top:4px">${p.qty_complete || 0} / ${p.qty_required || '?'}</div>
                    <div class="progress-bar" style="margin-top:4px">
                        <div class="progress-fill" style="width:${progress}%"></div>
                    </div>
                </div>
            `;
        }

        return `
            <div class="machine-card ${isRunning ? 'running' : 'idle'}">
                <div class="machine-name">${m.name}</div>
                <div class="machine-status">
                    <span class="badge ${isRunning ? 'badge-green' : 'badge-blue'}">
                        ${isRunning ? 'Running' : 'Idle'}
                    </span>
                    <span style="margin-left:8px; font-size:11px; color:var(--text-subtle)">
                        ${scheduled} queued
                    </span>
                </div>
                ${jobInfo}
            </div>
        `;
    }).join('');
}

function renderFlags(flags) {
    const container = document.getElementById('flags-list');

    if (flags.length === 0) {
        container.innerHTML = '<div style="color:var(--text-subtle); padding:12px">No open flags</div>';
        return;
    }

    container.innerHTML = flags.map(f => `
        <div class="flag-item">
            <div>
                <span class="flag-category flag-category-${f.category}">${f.category}</span>
                <div style="font-size:13px; margin-top:4px">${f.description}</div>
                <div style="font-size:11px; color:var(--text-subtle); margin-top:2px">
                    ${f.machine_name || ''} ${f.wo_number ? '— WO' + f.wo_number : ''}
                    — ${timeAgo(f.created_at)}
                </div>
            </div>
            <button class="btn" style="font-size:11px" onclick="resolveFlag(${f.id})">Resolve</button>
        </div>
    `).join('');
}

async function resolveFlag(flagId) {
    await fetchJSON(`/api/flags/${flagId}/resolve`, { method: 'POST' });
    loadDashboard();
}

async function renderPastDue() {
    try {
        const wos = await fetchJSON('/api/workorders?status=active');
        const now = new Date();
        const pastDue = wos.filter(w => w.due_date && new Date(w.due_date) < now);

        const container = document.getElementById('past-due-list');

        if (pastDue.length === 0) {
            container.innerHTML = '<div style="color:var(--text-subtle); padding:12px">No past-due work orders</div>';
            return;
        }

        container.innerHTML = pastDue.sort((a, b) => new Date(a.due_date) - new Date(b.due_date)).map(w => {
            const days = Math.abs(Math.ceil((new Date(w.due_date) - now) / 86400000));
            return `
                <div class="queue-item">
                    <div>
                        <a href="${psWoUrl(w.wo_number)}" target="_blank" style="font-weight:700; color:var(--accent-red); text-decoration:none">WO${w.wo_number}</a>
                        <div style="font-size:12px; color:var(--text-muted)">${w.part_name || w.part_number || ''}</div>
                        <div style="font-size:11px; color:var(--text-subtle)">${w.customer || ''}</div>
                    </div>
                    <div style="text-align:right">
                        <div style="color:var(--accent-red); font-weight:600; font-size:13px">${days} days late</div>
                        <div style="font-size:11px; color:var(--text-subtle)">Due ${new Date(w.due_date).toLocaleDateString()}</div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load past due:', e);
    }
}

function renderSyncLog(logs) {
    const container = document.getElementById('sync-log');

    if (!logs || logs.length === 0) {
        container.innerHTML = '<div style="color:var(--text-subtle); padding:12px">No sync history</div>';
        return;
    }

    container.innerHTML = logs.slice(0, 10).map(s => `
        <div class="queue-item">
            <div>
                <span class="badge ${s.status === 'completed' ? 'badge-green' : s.status === 'failed' ? 'badge-red' : 'badge-yellow'}">
                    ${s.status}
                </span>
                <span style="margin-left:8px; font-size:12px">${s.sync_type} sync</span>
            </div>
            <div style="text-align:right; font-size:12px; color:var(--text-muted)">
                ${s.wo_count} WOs, ${s.op_count} ops — ${s.duration_ms}ms
                <div style="font-size:11px; color:var(--text-subtle)">${timeAgo(s.created_at)}</div>
            </div>
        </div>
    `).join('');
}

// ── Needs Lists ─────────────────────────────────────────────────────────────

function renderNeedsCounts(counts) {
    document.getElementById('needs-program-count').textContent = counts.program;
    document.getElementById('needs-material-count').textContent = counts.material;
    document.getElementById('needs-tools-count').textContent = counts.tools;
    const rtEl = document.getElementById('needs-runtimes-count');
    if (rtEl) rtEl.textContent = counts.runtimes || 0;
}

function renderNeedsList(tab) {
    if (!needsData) return;
    const container = document.getElementById('needs-list');
    const key = tab === 'runtimes' ? 'check_runtimes' : 'needs_' + tab;
    const items = needsData[key] || [];

    if (items.length === 0) {
        container.innerHTML = '<div style="color:var(--text-subtle); padding:12px">None</div>';
        return;
    }

    // Sort by due date (soonest first, no-date last)
    const sorted = [...items].sort((a, b) => {
        if (!a.due_date && !b.due_date) return 0;
        if (!a.due_date) return 1;
        if (!b.due_date) return -1;
        return new Date(a.due_date) - new Date(b.due_date);
    });

    container.innerHTML = sorted.map(item => {
        const due = item.due_date ? new Date(item.due_date).toLocaleDateString() : 'No date';
        const isPastDue = item.due_date && new Date(item.due_date) < new Date();
        const dueClass = isPastDue ? 'color:var(--accent-red); font-weight:600' : '';

        let detail = '';
        if (tab === 'material') {
            const ms = item.material_status || 'unknown';
            let statusLabel, statusColor;
            if (ms === 'not_ordered') {
                statusLabel = 'NOT ORDERED';
                statusColor = 'var(--accent-red)';
            } else if (ms === 'ordered') {
                const po = item.material_po || '';
                const os = item.material_order_status || '';
                statusLabel = `ORDERED — PO ${po}` + (os ? ` (${os})` : '');
                statusColor = 'var(--accent-orange)';
            } else {
                statusLabel = ms;
                statusColor = 'var(--text-muted)';
            }
            detail = `<div style="font-size:11px; font-weight:600; color:${statusColor}; margin-top:2px">${statusLabel}</div>`;
            if (item.material_type) {
                detail += `<div style="font-size:11px; color:var(--text-subtle); margin-top:1px">Material: ${item.material_type}</div>`;
            }
        }
        if (tab === 'tools' && item.tools && item.tools.length > 0) {
            const toolList = item.tools.map(t => `T${t.tool_number} ${t.tool_description || ''}`).join(', ');
            detail = `<div style="font-size:11px; color:var(--accent-orange); margin-top:2px">Tools: ${toolList}</div>`;
        }
        if (tab === 'runtimes') {
            const hrs = item.est_hours || 0;
            const qty = item.qty_required || 0;
            const estLabel = item.is_estimated ? ' (estimated)' : '';
            detail = `<div style="font-size:12px; font-weight:600; color:var(--accent-red); margin-top:2px">${hrs.toFixed(1)}h total${estLabel} — ${qty} parts</div>`;
        }

        return `
            <div class="needs-item">
                <div>
                    <a href="${psWoUrl(item.wo_number)}" target="_blank" style="font-weight:700; color:var(--accent-blue); text-decoration:none">WO${item.wo_number}</a> Op${item.op_number}
                    <span style="color:var(--text-muted); margin-left:6px">${item.op_name || ''}</span>
                    <div style="font-size:12px; color:var(--text-muted)">${item.part_number || ''} — ${item.part_name || ''}</div>
                    <div style="font-size:11px; color:var(--text-subtle)">${item.customer || ''} · ${item.work_center || ''} · ${item.est_hours || 0}h</div>
                    ${detail}
                </div>
                <div style="text-align:right; white-space:nowrap">
                    <div style="font-size:12px; ${dueClass}">Due ${due}</div>
                </div>
            </div>
        `;
    }).join('');
}

function initNeedsTabs() {
    const tabs = document.querySelectorAll('.needs-tab');
    tabs.forEach(btn => {
        btn.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            btn.classList.add('active');
            activeNeedsTab = btn.dataset.tab;
            renderNeedsList(activeNeedsTab);
        });
    });

    const printBtn = document.getElementById('btn-print-needs');
    if (printBtn) {
        printBtn.addEventListener('click', () => {
            window.print();
        });
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function psWoUrl(woNumber) {
    // WO format: "YY-XXXX" → URL: /procnc/workorders/20YY/YY-XXXX$
    const base = window.PROSHOP_BASE || '';
    const yy = woNumber.split('-')[0];
    return `${base}/procnc/workorders/20${yy}/${woNumber}$`;
}

async function fetchJSON(url, opts = {}) {
    const init = {
        method: opts.method || 'GET',
        headers: { 'Content-Type': 'application/json' },
    };
    if (opts.body) init.body = JSON.stringify(opts.body);
    const resp = await fetch(url, init);
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: resp.statusText }));
        throw new Error(err.error || resp.statusText);
    }
    return resp.json();
}

function timeAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const sec = Math.floor((now - d) / 1000);
    if (sec < 60) return 'just now';
    if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
    if (sec < 86400) return Math.floor(sec / 3600) + 'h ago';
    return Math.floor(sec / 86400) + 'd ago';
}
