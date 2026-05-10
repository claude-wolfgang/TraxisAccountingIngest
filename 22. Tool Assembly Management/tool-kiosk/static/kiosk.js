// ── State ─────────────────────────────────────────────────────────────────────
var state = {
    employee: null,
    holder: null,        // full holder detail from API
    screen: 'sleep',
    isReplace: false,    // true when replacing cutter (vs fresh install)
    retireReason: 'worn',
    selectedMachine: null,
    // Inventory
    invSessionId: null,      // active inventory session ID
    invCurrentTool: null,    // current tool being counted
    invSessionTotal: 0,      // total items in session
    invSessionCounted: 0,    // items counted so far
    invHistory: [],          // stack of previous tools for Back navigation
};

var countdownTimer = null;
var inactivityTimer = null;
var pendingScan = null;
var INACTIVITY_TIMEOUT = 120; // seconds before returning to sleep screen

// ── Screen Navigation ────────────────────────────────────────────────────────

function showScreen(name) {
    var screens = document.querySelectorAll('.kiosk-screen');
    for (var i = 0; i < screens.length; i++) {
        screens[i].classList.remove('active');
    }
    document.getElementById('screen-' + name).classList.add('active');
    state.screen = name;
    resetInactivity();

    if (name === 'scan') {
        var input = document.getElementById('scan-input');
        input.value = '';
        setTimeout(function() { input.focus(); }, 100);
    }
    if (name === 'inventory-scan') {
        var invInput = document.getElementById('inv-scan-input');
        invInput.value = '';
        setTimeout(function() { invInput.focus(); }, 100);
    }
    if (name === 'inventory-menu') {
        var invEmp = document.getElementById('inv-employee');
        if (invEmp) invEmp.textContent = state.employee || '';
        invCheckOpenSession();
    }
}

function kioskGoHome() {
    state.employee = null;
    state.holder = null;
    state.selectedMachine = null;
    state.invSessionId = null;
    state.invCurrentTool = null;
    state.invHistory = [];
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    showScreen('sleep');
}

function wakeKiosk() {
    if (state.screen !== 'sleep') return;
    loadEmployees();
    showScreen('employee');
}

function kioskGoBack() {
    if (state.screen === 'employee') kioskGoHome();
    else if (state.screen === 'scan') kioskGoHome();
    else if (state.screen === 'detail') showScreen('scan');
    else if (state.screen === 'register') showScreen('scan');
    else if (state.screen === 'install') showScreen('detail');
    else if (state.screen === 'assign') showScreen('detail');
    else if (state.screen === 'inventory-menu') showScreen('scan');
    else if (state.screen === 'inventory-scan') showScreen('inventory-menu');
    else if (state.screen === 'inventory-count') invCountBack();
    else if (state.screen === 'inventory-add') showScreen('inventory-menu');
    else if (state.screen === 'inventory-summary') kioskGoHome();
    else if (state.screen === 'done') kioskGoHome();
}

// ── Inactivity Timeout ───────────────────────────────────────────────────────

function resetInactivity() {
    if (inactivityTimer) clearTimeout(inactivityTimer);
    if (state.screen !== 'sleep') {
        inactivityTimer = setTimeout(function() {
            kioskGoHome();
        }, INACTIVITY_TIMEOUT * 1000);
    }
}

document.addEventListener('touchstart', resetInactivity);
document.addEventListener('keydown', resetInactivity);
document.addEventListener('click', resetInactivity);

// ── Employee Selection ───────────────────────────────────────────────────────

function loadEmployees() {
    var grid = document.getElementById('employee-grid');
    grid.innerHTML = '<div class="loading">Loading employees...</div>';
    var timedOut = false;
    var loadTimer = setTimeout(function() {
        timedOut = true;
        grid.innerHTML =
            '<div class="loading">Loading is taking too long.<br>' +
            '<button class="btn btn-primary" style="margin-top:12px" onclick="loadEmployees()">Retry</button> ' +
            '<button class="btn btn-secondary" style="margin-top:12px" onclick="kioskGoHome()">Back</button></div>';
    }, 10000);

    apiFetch('/api/users').then(function(users) {
        clearTimeout(loadTimer);
        if (timedOut) return;
        grid.innerHTML = '';
        users.forEach(function(u) {
            var fullName = u.firstName + ' ' + u.lastName;
            var displayName = u.firstName + ' ' + u.lastName.charAt(0) + '.';
            var btn = document.createElement('button');
            btn.className = 'employee-btn';
            btn.textContent = displayName;
            btn.onclick = function() { selectEmployee(fullName); };
            grid.appendChild(btn);
        });
    }).catch(function() {
        clearTimeout(loadTimer);
        if (timedOut) return;
        grid.innerHTML =
            '<div class="loading">Failed to load employees.<br>' +
            '<button class="btn btn-primary" style="margin-top:12px" onclick="loadEmployees()">Retry</button> ' +
            '<button class="btn btn-secondary" style="margin-top:12px" onclick="kioskGoHome()">Back</button></div>';
    });
}

function selectEmployee(name) {
    state.employee = name;
    document.getElementById('selected-employee').textContent = name;
    showScreen('scan');
    if (pendingScan) {
        var val = pendingScan;
        pendingScan = null;
        document.getElementById('scan-input').value = val;
        lookupHolder(val);
    }
}

// ── QR / Scan Input ──────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    var scanInput = document.getElementById('scan-input');
    if (scanInput) {
        scanInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                var val = scanInput.value.trim();
                if (val) lookupHolder(val);
            }
        });
    }

    // Inventory scan input
    var invScanInput = document.getElementById('inv-scan-input');
    if (invScanInput) {
        invScanInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                var val = invScanInput.value.trim().toUpperCase();
                if (val) invLookupTool(val);
            }
        });
    }

    // Inventory jump-to input
    var invJumpInput = document.getElementById('inv-jump-input');
    if (invJumpInput) {
        invJumpInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                invJumpToTool();
            }
        });
    }

    // Inventory qty inputs — update available total on change
    ['blue', 'green', 'yellow', 'red'].forEach(function(color) {
        var el = document.getElementById('inv-qty-' + color);
        if (el) {
            el.addEventListener('input', invUpdateAvailable);
        }
    });

    // Auto-lookup for inventory add form
    var invAddToolInput = document.getElementById('inv-add-tool-number');
    if (invAddToolInput) {
        var _invAddLookupTimeout = null;
        invAddToolInput.addEventListener('blur', function() {
            var tn = invAddToolInput.value.trim().toUpperCase();
            if (!tn) return;
            if (_invAddLookupTimeout) clearTimeout(_invAddLookupTimeout);
            _invAddLookupTimeout = setTimeout(function() {
                apiFetch('/api/tools/' + encodeURIComponent(tn)).then(function(tool) {
                    var descField = document.getElementById('inv-add-description');
                    if (descField && tool.description && !descField.value.trim()) {
                        descField.value = tool.description;
                    }
                }).catch(function() {});
            }, 300);
        });
    }

    // Auto-lookup tool description when ProShop tool # is entered
    var toolNumInput = document.getElementById('install-tool-number');
    if (toolNumInput) {
        toolNumInput.addEventListener('blur', onToolNumberChange);
        toolNumInput.addEventListener('input', onToolNumberChange);
    }

    // Auto-lookup for register RTA form
    var regToolNumInput = document.getElementById('reg-tool-number');
    if (regToolNumInput) {
        regToolNumInput.addEventListener('blur', onRegToolNumberChange);
        regToolNumInput.addEventListener('input', onRegToolNumberChange);
    }

    // Pick up ?scan= parameter
    var params = new URLSearchParams(window.location.search);
    var scanParam = params.get('scan');
    if (scanParam) {
        history.replaceState(null, '', '/');
        pendingScan = scanParam;
        wakeKiosk();
        showToast('Holder scanned — select your name to continue', 'info');
    }

    // Global scanner detector for non-scan screens
    var kioskScanBuffer = '';
    var kioskScanTimeout = null;
    document.addEventListener('keydown', function(e) {
        if (e.target === scanInput) return;
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

        if (e.key === 'Enter' && kioskScanBuffer.length >= 3) {
            e.preventDefault();
            var scanned = kioskScanBuffer;
            kioskScanBuffer = '';
            if (kioskScanTimeout) { clearTimeout(kioskScanTimeout); kioskScanTimeout = null; }

            if (state.screen === 'sleep') {
                pendingScan = scanned;
                wakeKiosk();
                showToast('Holder scanned — select your name to continue', 'info');
            } else if (state.screen === 'employee') {
                pendingScan = scanned;
                showToast('Holder scanned — select your name to continue', 'info');
            } else if (state.screen === 'scan') {
                scanInput.value = scanned;
                lookupHolder(scanned);
            }
            return;
        }

        if (e.key.length === 1) {
            kioskScanBuffer += e.key;
            if (kioskScanTimeout) clearTimeout(kioskScanTimeout);
            kioskScanTimeout = setTimeout(function() {
                kioskScanBuffer = '';
            }, 80);
        }
    });

});

function extractHolderId(value) {
    value = value.trim().toUpperCase();
    // Strip scanner suffix chars
    value = value.replace(/[\$%#\r\n]+$/, '');
    // Already in H-XXXX format
    if (/^H-\d+$/.test(value)) return value;
    // H followed by digits but missing hyphen (e.g., H0001 → H-0001)
    var noHyphen = value.match(/^H(\d{1,4})$/);
    if (noHyphen) return 'H-' + noHyphen[1].padStart(4, '0');
    // Just digits — prepend H-
    if (/^\d{1,4}$/.test(value)) return 'H-' + value.padStart(4, '0');
    return value;
}

function lookupHolder(rawValue) {
    var holderId = extractHolderId(rawValue);
    var input = document.getElementById('scan-input');
    input.value = holderId;
    input.disabled = true;
    showToast('Looking up: ' + holderId, 'info');

    apiFetch('/api/holders/' + encodeURIComponent(holderId)).then(function(detail) {
        state.holder = detail;
        renderHolderDetail(detail);
        showScreen('detail');
        input.disabled = false;
    }).catch(function(err) {
        input.disabled = false;
        if (err.message && err.message.indexOf('not found') !== -1) {
            showToast(holderId + ' not registered — opening register form', 'warning');
            showScreen('register');
            return;
        }
        input.focus();
        input.select();
    });
}

// ── Holder Detail Rendering ──────────────────────────────────────────────────

function renderHolderDetail(h) {
    document.getElementById('detail-holder-id').textContent = h.holder_id;
    var typeText = h.holder_type || '';
    if (h.collet_size) typeText += ' ' + h.collet_size;
    if (h.holder_length) typeText += ' (' + h.holder_length + '")';
    if (h.serial_number) typeText += ' — SN: ' + h.serial_number;
    document.getElementById('detail-holder-type').textContent = typeText;

    // RTA badge
    var rtaBadge = document.getElementById('detail-rta-number');
    if (rtaBadge) {
        if (h.rta_number) {
            rtaBadge.textContent = 'RTA ' + h.rta_number;
            rtaBadge.style.display = '';
        } else {
            rtaBadge.style.display = 'none';
        }
    }

    // Assembly
    var asmEl = document.getElementById('detail-assembly');
    var asm = h.active_assembly;
    if (asm) {
        asmEl.innerHTML =
            '<div class="detail-row"><span class="detail-label">Tool #:</span><span class="detail-value">' + (asm.proshop_tool_number || '-') + '</span></div>' +
            '<div class="detail-row"><span class="detail-label">Description:</span><span class="detail-value">' + (asm.tool_description || '-') + '</span></div>' +
            '<div class="detail-row"><span class="detail-label">OOH:</span><span class="detail-value">' + (asm.ooh_inches ? asm.ooh_inches.toFixed(3) + '"' : '-') + '</span></div>' +
            '<div class="detail-row"><span class="detail-label">Installed:</span><span class="detail-value">' + formatTime(asm.installed_at) + '</span></div>' +
            '<div class="detail-row"><span class="detail-label">By:</span><span class="detail-value">' + (asm.installed_by || '-') + '</span></div>';
        document.getElementById('btn-replace-cutter').style.display = '';
        document.getElementById('btn-install-cutter').style.display = 'none';
    } else {
        asmEl.innerHTML = '<p class="no-data">No cutter installed</p>';
        document.getElementById('btn-replace-cutter').style.display = 'none';
        document.getElementById('btn-install-cutter').style.display = '';
    }

    // Assignment
    var assignEl = document.getElementById('detail-assignment');
    var asgn = h.active_assignment;
    if (asgn) {
        var machName = MACHINES[asgn.machine_id] ? MACHINES[asgn.machine_id].name : asgn.machine_id;
        assignEl.innerHTML =
            '<div class="detail-row"><span class="detail-label">Machine:</span><span class="detail-value">' + machName + '</span></div>' +
            '<div class="detail-row"><span class="detail-label">Pocket:</span><span class="detail-value">T' + asgn.pocket_number + '</span></div>' +
            '<div class="detail-row"><span class="detail-label">Since:</span><span class="detail-value">' + formatTime(asgn.assigned_at) + '</span></div>';
        document.getElementById('btn-assign').style.display = 'none';
        document.getElementById('btn-move').style.display = '';
        document.getElementById('btn-remove').style.display = '';
    } else {
        assignEl.innerHTML = '<p class="no-data">Not assigned to any machine</p>';
        document.getElementById('btn-assign').style.display = '';
        document.getElementById('btn-move').style.display = 'none';
        document.getElementById('btn-remove').style.display = 'none';
    }

    // Usage
    var usageEl = document.getElementById('detail-usage');
    var usage = h.assembly_usage || {};
    if (usage.total_cutting_minutes > 0) {
        usageEl.innerHTML =
            '<div class="detail-row"><span class="detail-label">Cutting Time:</span><span class="detail-value">' + usage.total_cutting_minutes.toFixed(1) + ' min</span></div>' +
            '<div class="detail-row"><span class="detail-label">Peak Load:</span><span class="detail-value">' + (usage.overall_peak_spindle_load || '-') + '%</span></div>' +
            '<div class="detail-row"><span class="detail-label">Segments:</span><span class="detail-value">' + (usage.segment_count || 0) + '</span></div>';
    } else {
        usageEl.innerHTML = '<p class="no-data">No usage data yet</p>';
    }
}

// ── Register RTA (combined holder + cutter + ProShop RTA) ────────────────────

function registerRTA() {
    var holderType = document.getElementById('reg-holder-type').value;
    var toolNum = (document.getElementById('reg-tool-number').value || '').trim();

    if (!holderType) {
        showToast('Select a holder type', 'error');
        return;
    }
    if (!toolNum) {
        showToast('ProShop Tool # is required', 'error');
        return;
    }

    var lengthEl = document.getElementById('reg-holder-length');
    var lengthVal = lengthEl ? lengthEl.value : '';
    var snEl = document.getElementById('reg-serial-number');
    var oohVal = parseFloat(document.getElementById('reg-ooh').value);

    apiFetch('/api/register-rta', {
        method: 'POST',
        body: {
            holder_type: holderType,
            collet_size: document.getElementById('reg-collet-size').value,
            holder_length: lengthVal ? parseInt(lengthVal) : null,
            serial_number: snEl ? snEl.value.trim() : '',
            proshop_tool_number: toolNum,
            tool_description: document.getElementById('reg-tool-desc').value.trim(),
            ooh_inches: !isNaN(oohVal) ? oohVal : null,
            notes: document.getElementById('reg-notes').value.trim(),
            employee: state.employee,
        }
    }).then(function(result) {
        // Clear form
        document.getElementById('reg-holder-type').value = '';
        document.getElementById('reg-collet-size').value = '';
        if (lengthEl) lengthEl.value = '';
        if (snEl) snEl.value = '';
        document.getElementById('reg-tool-number').value = '';
        document.getElementById('reg-tool-desc').value = '';
        document.getElementById('reg-ooh').value = '';
        document.getElementById('reg-notes').value = '';

        var hid = result.holder_id;
        var rtaText = result.rta_number ? ' — RTA ' + result.rta_number + ' assigned' : '';
        var headline = hid + ' registered' + rtaText;

        // Store holder in state so "Assign to Machine" works
        if (result.holder) {
            result.holder.active_assembly = result.assembly;
            result.holder.active_assignment = null;
            state.holder = result.holder;
        }

        // Build next actions
        var nextActions = [
            {label: 'Assign to Machine', action: function() {
                if (state.holder) renderHolderDetail(state.holder);
                showAssignScreen();
            }}
        ];

        showDone(headline,
                 (toolNum || '') + ' ' + (result.assembly.tool_description || ''),
                 nextActions, true);

        // Auto-print label
        var printData = {
            holder_id: hid,
            rta_number: result.rta_number || '',
            proshop_tool_number: result.assembly ? result.assembly.proshop_tool_number || '' : '',
            holder_type: result.holder ? result.holder.holder_type || 'CAT40 Holder' : 'CAT40 Holder',
        };
        autoPrintLabel(printData);
    });
}

function autoPrintLabel(labelData) {
    var url = '/api/print-label';

    var body = {
        holder_id: labelData.holder_id,
        rta_number: labelData.rta_number || '',
        proshop_tool_number: labelData.proshop_tool_number || '',
        holder_type: labelData.holder_type || 'CAT40 Holder',
        copies: 2,
    };

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    }).then(function(resp) {
        return resp.json().then(function(data) {
            if (resp.ok && data.printed) {
                showToast('Label printed for ' + labelData.holder_id, 'success');
            } else {
                showToast('Print failed — turn on printer PC and tap Retry', 'warning');
                addRetryPrintButton(labelData);
            }
        });
    }).catch(function() {
        showToast('Printer unreachable — turn on printer PC and tap Retry', 'warning');
        addRetryPrintButton(labelData);
    });
}

function addRetryPrintButton(labelData) {
    var actionsEl = document.getElementById('done-next-actions');
    if (!actionsEl) return;
    // Only add if not already present
    if (actionsEl.querySelector('.btn-retry-print')) return;
    var btn = document.createElement('button');
    btn.className = 'btn btn-warning btn-large btn-retry-print';
    btn.textContent = 'Retry Print';
    btn.onclick = function() {
        btn.disabled = true;
        btn.textContent = 'Printing...';
        autoPrintLabel(labelData);
        // Re-enable after a short delay
        setTimeout(function() {
            btn.disabled = false;
            btn.textContent = 'Retry Print';
        }, 2000);
    };
    actionsEl.appendChild(btn);
    actionsEl.style.display = '';
}

// Legacy: keep registerHolder for old scan→register flow (holder found by QR but not registered)
function registerHolder() {
    var holderId = document.getElementById('reg-holder-id') ?
        document.getElementById('reg-holder-id').value.trim().toUpperCase() : '';
    if (!holderId) {
        // No holder ID field — this is the new combined form, use registerRTA instead
        registerRTA();
        return;
    }
    if (!/^H-\d{1,4}$/.test(holderId)) {
        holderId = extractHolderId(holderId);
    }

    var lengthEl = document.getElementById('reg-holder-length');
    var lengthVal = lengthEl ? lengthEl.value : '';
    var snEl = document.getElementById('reg-serial-number');
    apiFetch('/api/holders', {
        method: 'POST',
        body: {
            holder_id: holderId,
            holder_type: document.getElementById('reg-holder-type').value,
            collet_size: document.getElementById('reg-collet-size').value,
            holder_length: lengthVal ? parseInt(lengthVal) : null,
            serial_number: snEl ? snEl.value.trim() : '',
            notes: document.getElementById('reg-notes').value.trim(),
            employee: state.employee,
        }
    }).then(function(holder) {
        showToast(holder.holder_id + ' registered!', 'success');
        // Load holder detail then go straight to install cutter
        apiFetch('/api/holders/' + encodeURIComponent(holder.holder_id)).then(function(detail) {
            state.holder = detail;
            renderHolderDetail(detail);
            showInstallScreen();
        });
    });
}

// ── Install / Replace Cutter ─────────────────────────────────────────────────

var _toolLookupTimeout = null;

function onToolNumberChange() {
    var input = document.getElementById('install-tool-number');
    var tn = input.value.trim().toUpperCase();
    if (_toolLookupTimeout) clearTimeout(_toolLookupTimeout);
    if (!tn || tn.length < 1) return;
    _toolLookupTimeout = setTimeout(function() {
        apiFetch('/api/tools/' + encodeURIComponent(tn)).then(function(tool) {
            var descField = document.getElementById('install-tool-desc');
            if (descField && tool.description && !descField.value.trim()) {
                descField.value = tool.description;
            }
        }).catch(function() { /* not found — no action */ });
    }, 400);
}

var _regToolLookupTimeout = null;

function onRegToolNumberChange() {
    var input = document.getElementById('reg-tool-number');
    var tn = input.value.trim().toUpperCase();
    if (_regToolLookupTimeout) clearTimeout(_regToolLookupTimeout);
    if (!tn || tn.length < 1) return;
    _regToolLookupTimeout = setTimeout(function() {
        apiFetch('/api/tools/' + encodeURIComponent(tn)).then(function(tool) {
            var descField = document.getElementById('reg-tool-desc');
            if (descField && tool.description && !descField.value.trim()) {
                descField.value = tool.description;
            }
        }).catch(function() { /* not found — no action */ });
    }, 400);
}

function showInstallScreen() {
    state.isReplace = false;
    document.getElementById('install-heading').textContent = 'Install Cutter';
    document.getElementById('install-btn-text').textContent = 'Install Cutter';
    document.getElementById('install-holder-id').textContent = state.holder.holder_id;
    document.getElementById('retire-reason-area').style.display = 'none';
    // Show skip button if no cutter and no assignment (fresh holder)
    var skipBtn = document.getElementById('install-skip-btn');
    if (skipBtn) {
        skipBtn.style.display = (!state.holder.active_assembly && !state.holder.active_assignment) ? '' : 'none';
    }
    // Pre-fill from default_tool if available
    var dt = state.holder.default_tool || '';
    document.getElementById('install-tool-number').value = dt;
    document.getElementById('install-tool-desc').value = '';
    document.getElementById('install-ooh').value = '';
    if (dt) onToolNumberChange();
    showScreen('install');
}

function showReplaceScreen() {
    state.isReplace = true;
    state.retireReason = 'worn';
    document.getElementById('install-heading').textContent = 'Replace Cutter';
    document.getElementById('install-btn-text').textContent = 'Replace Cutter';
    document.getElementById('install-holder-id').textContent = state.holder.holder_id;
    document.getElementById('retire-reason-area').style.display = '';
    var skipBtn = document.getElementById('install-skip-btn');
    if (skipBtn) skipBtn.style.display = 'none';
    // Pre-fill from current assembly
    var asm = state.holder.active_assembly || {};
    document.getElementById('install-tool-number').value = asm.proshop_tool_number || '';
    document.getElementById('install-tool-desc').value = asm.tool_description || '';
    document.getElementById('install-ooh').value = asm.ooh_inches || '';
    // Reset retire reason buttons
    var btns = document.querySelectorAll('#retire-reason-area .toggle-btn');
    for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('active', btns[i].getAttribute('data-reason') === 'worn');
    }
    showScreen('install');
}

function setRetireReason(reason) {
    state.retireReason = reason;
    var btns = document.querySelectorAll('#retire-reason-area .toggle-btn');
    for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('active', btns[i].getAttribute('data-reason') === reason);
    }
}

function skipToAssign() {
    // Skip cutter install, go straight to assign
    showAssignScreen();
}

function submitInstall() {
    var holderId = state.holder.holder_id;
    var endpoint = state.isReplace ? '/api/holders/' + encodeURIComponent(holderId) + '/replace'
                                   : '/api/holders/' + encodeURIComponent(holderId) + '/install';

    var body = {
        proshop_tool_number: document.getElementById('install-tool-number').value.trim(),
        tool_description: document.getElementById('install-tool-desc').value.trim(),
        employee: state.employee,
    };
    var ooh = parseFloat(document.getElementById('install-ooh').value);
    if (!isNaN(ooh)) body.ooh_inches = ooh;
    if (state.isReplace) body.retire_reason = state.retireReason;

    apiFetch(endpoint, { method: 'POST', body: body }).then(function(result) {
        var verb = state.isReplace ? 'Cutter replaced' : 'Cutter installed';
        // Refresh holder state
        apiFetch('/api/holders/' + encodeURIComponent(holderId)).then(function(detail) {
            state.holder = detail;
            // If not assigned to a machine, offer assign as next step
            if (!detail.active_assignment) {
                showDone(verb + ' on ' + holderId,
                         (body.proshop_tool_number || '') + ' ' + (body.tool_description || ''),
                         [{label: 'Assign to Machine', action: function() { renderHolderDetail(detail); showAssignScreen(); }}]);
            } else {
                showDone(verb + ' on ' + holderId,
                         (body.proshop_tool_number || '') + ' ' + (body.tool_description || ''));
            }
        }).catch(function() {
            showDone(verb + ' on ' + holderId,
                     (body.proshop_tool_number || '') + ' ' + (body.tool_description || ''));
        });
    });
}

// ── Assign / Move ────────────────────────────────────────────────────────────

function showAssignScreen() {
    state.selectedMachine = null;
    document.getElementById('assign-heading').textContent = 'Assign to Machine';
    document.getElementById('assign-holder-id').textContent = state.holder.holder_id;
    document.getElementById('assign-pocket').value = '';
    document.getElementById('assign-wo').value = '';
    renderMachineGrid();
    showScreen('assign');
}

function showMoveScreen() {
    state.selectedMachine = null;
    document.getElementById('assign-heading').textContent = 'Move to Machine';
    document.getElementById('assign-holder-id').textContent = state.holder.holder_id;
    document.getElementById('assign-pocket').value = '';
    document.getElementById('assign-wo').value = '';
    renderMachineGrid();
    showScreen('assign');
}

function renderMachineGrid() {
    var grid = document.getElementById('machine-grid');
    grid.innerHTML = '';
    var keys = Object.keys(MACHINES).sort();
    keys.forEach(function(mid) {
        var m = MACHINES[mid];
        if (!m.enabled) return;
        var btn = document.createElement('button');
        btn.className = 'machine-btn';
        btn.textContent = mid + '\n' + m.name;
        btn.setAttribute('data-id', mid);
        btn.onclick = function() { selectMachine(mid); };
        grid.appendChild(btn);
    });
}

function selectMachine(mid) {
    state.selectedMachine = mid;
    var btns = document.querySelectorAll('.machine-btn');
    for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('selected', btns[i].getAttribute('data-id') === mid);
    }
}

function submitAssign() {
    if (!state.selectedMachine) {
        showToast('Select a machine first', 'error');
        return;
    }
    var pocket = parseInt(document.getElementById('assign-pocket').value, 10);
    if (!pocket || pocket < 1) {
        showToast('Enter a valid pocket number', 'error');
        return;
    }

    var holderId = state.holder.holder_id;
    var isMove = state.holder.active_assignment != null;
    var endpoint = isMove ? '/api/holders/' + encodeURIComponent(holderId) + '/move'
                          : '/api/holders/' + encodeURIComponent(holderId) + '/assign';

    var body = {
        machine_id: state.selectedMachine,
        pocket_number: pocket,
        work_order: document.getElementById('assign-wo').value.trim() || null,
        employee: state.employee,
    };

    apiFetch(endpoint, { method: 'POST', body: body }).then(function(result) {
        var verb = isMove ? 'Moved' : 'Assigned';
        var machName = MACHINES[state.selectedMachine] ? MACHINES[state.selectedMachine].name : state.selectedMachine;
        showDone(verb + ' ' + holderId + ' to ' + machName + ' T' + pocket,
                 (result.new_proshop_synced || result.proshop_synced) ? 'ProShop synced' : 'ProShop sync pending');
    });
}

function confirmRemove() {
    if (!confirm('Remove ' + state.holder.holder_id + ' from ' +
                 state.holder.active_assignment.machine_id + ' T' +
                 state.holder.active_assignment.pocket_number + '?')) return;

    var holderId = state.holder.holder_id;
    apiFetch('/api/holders/' + encodeURIComponent(holderId) + '/remove', {
        method: 'POST',
        body: { employee: state.employee }
    }).then(function(result) {
        showDone('Removed ' + holderId + ' from machine',
                 result.proshop_synced ? 'ProShop pocket cleared' : 'ProShop sync pending');
    });
}

function printLabel() {
    var h = state.holder;
    var holderId = h.holder_id;
    var btn = document.getElementById('btn-print-label');
    btn.disabled = true;
    btn.textContent = 'Printing...';

    var asm = h.active_assembly || {};
    var body = {
        holder_id: holderId,
        rta_number: h.rta_number || '',
        proshop_tool_number: asm.proshop_tool_number || '',
        holder_type: h.holder_type || 'CAT40 Holder',
        copies: 2,
    };

    var url = '/api/print-label';

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    }).then(function(resp) {
        return resp.json().then(function(data) {
            btn.disabled = false;
            btn.textContent = 'Print Label';
            if (resp.ok && data.printed) {
                showToast('Printed ' + data.copies + ' labels for ' + holderId, 'success');
            } else {
                showToast('Print failed: ' + (data.error || 'unknown'), 'error');
            }
        });
    }).catch(function(err) {
        btn.disabled = false;
        btn.textContent = 'Print Label';
        showToast('Print service unreachable. Is the printer PC on?', 'error');
    });
}

// ── Done Screen ──────────────────────────────────────────────────────────────

function showDone(headline, details, nextActions, noCountdown) {
    document.getElementById('done-headline').textContent = headline;
    document.getElementById('done-details').textContent = details || '';

    // Next action buttons (e.g., "Assign to Machine" after install)
    var actionsEl = document.getElementById('done-next-actions');
    if (actionsEl) {
        actionsEl.innerHTML = '';
        if (nextActions && nextActions.length) {
            nextActions.forEach(function(na) {
                var btn = document.createElement('button');
                btn.className = 'btn btn-primary btn-large';
                btn.textContent = na.label;
                btn.onclick = function() {
                    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
                    na.action();
                };
                actionsEl.appendChild(btn);
            });
            actionsEl.style.display = '';
        } else {
            actionsEl.style.display = 'none';
        }
    }

    var countdownArea = document.querySelector('.done-countdown');
    showScreen('done');
    if (noCountdown) {
        // Stay on screen — operator must tap Done or an action button
        if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
        if (countdownArea) countdownArea.style.display = 'none';
    } else {
        if (countdownArea) countdownArea.style.display = '';
        startCountdown();
    }
}

function startCountdown() {
    var remaining = AUTO_RETURN;
    var el = document.getElementById('countdown');
    el.textContent = remaining;
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = setInterval(function() {
        remaining--;
        el.textContent = remaining;
        if (remaining <= 0) {
            clearInterval(countdownTimer);
            countdownTimer = null;
            kioskGoHome();
        }
    }, 1000);
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(iso) {
    if (!iso) return '-';
    try {
        return new Date(iso).toLocaleString();
    } catch(e) { return iso; }
}


// ── Inventory ────────────────────────────────────────────────────────────────

function startQuickCount() {
    state.invSessionId = null;
    document.getElementById('inv-scan-employee').textContent = state.employee || '';
    showScreen('inventory-scan');
}

function startFullInventory() {
    // If an open session exists, resume it instead of creating a new one
    if (state._pendingResumeSession) {
        resumeInventory();
        return;
    }
    apiFetch('/api/inventory/session', {
        method: 'POST',
        body: { employee: state.employee }
    }).then(function(result) {
        if (result.total_items === 0) {
            showToast('No tools in inventory. Add some first.', 'warning');
            return;
        }
        state.invSessionId = result.session_id;
        state.invSessionTotal = result.total_items;
        state.invSessionCounted = 0;
        state.invHistory = [];
        invLoadNextSessionItem();
    });
}

function invLookupTool(toolNumber) {
    var input = document.getElementById('inv-scan-input');
    input.disabled = true;
    showToast('Looking up: ' + toolNumber, 'info');

    _invFetchTool(toolNumber, function(item) {
        input.disabled = false;
        state.invCurrentTool = item;
        invShowCountForm(item);
    }, function() {
        input.disabled = false;
        input.focus();
        input.select();
    });
}

function invShowCountForm(item) {
    document.getElementById('inv-count-tool-number').textContent = item.tool_number;
    document.getElementById('inv-count-description').textContent = item.tool_description || '';
    document.getElementById('inv-count-location').textContent =
        item.cabinet_location ? 'Location: ' + item.cabinet_location : '';

    // Clear jump input
    var jumpInput = document.getElementById('inv-jump-input');
    if (jumpInput) jumpInput.value = '';

    // Pre-fill with current counts
    document.getElementById('inv-qty-blue').value = item.qty_blue || 0;
    document.getElementById('inv-qty-green').value = item.qty_green || 0;
    document.getElementById('inv-qty-yellow').value = item.qty_yellow || 0;
    document.getElementById('inv-qty-red').value = item.qty_red || 0;

    // Previous counts reference
    var prevEl = document.getElementById('inv-prev-counts');
    var prevVals = document.getElementById('inv-prev-values');
    if (item.last_counted_at) {
        prevEl.style.display = '';
        prevVals.textContent = 'B:' + (item.qty_blue||0) + ' G:' + (item.qty_green||0) +
            ' Y:' + (item.qty_yellow||0) + ' R:' + (item.qty_red||0) +
            ' — ' + formatTime(item.last_counted_at);
    } else {
        prevEl.style.display = 'none';
    }

    // Session progress bar + stop/skip buttons
    var sessionBar = document.getElementById('inv-session-bar');
    var skipBtn = document.getElementById('inv-skip-btn');
    var stopBtn = document.getElementById('inv-stop-btn');
    if (state.invSessionId) {
        sessionBar.style.display = '';
        skipBtn.style.display = '';
        stopBtn.style.display = '';
        invUpdateProgress();
        document.getElementById('inv-save-btn').textContent = 'Save & Next';
    } else {
        sessionBar.style.display = 'none';
        skipBtn.style.display = 'none';
        stopBtn.style.display = 'none';
        document.getElementById('inv-save-btn').textContent = 'Save Count';
    }

    invUpdateAvailable();
    showScreen('inventory-count');
}

function invStep(color, delta) {
    var input = document.getElementById('inv-qty-' + color);
    var val = parseInt(input.value, 10) || 0;
    val = Math.max(0, val + delta);
    input.value = val;
    invUpdateAvailable();
}

function invUpdateAvailable() {
    var blue = parseInt(document.getElementById('inv-qty-blue').value, 10) || 0;
    var green = parseInt(document.getElementById('inv-qty-green').value, 10) || 0;
    document.getElementById('inv-available-total').textContent = blue + green;
}

function invUpdateProgress() {
    var counted = state.invSessionCounted;
    var total = state.invSessionTotal;
    var pct = total > 0 ? Math.round((counted / total) * 100) : 0;
    document.getElementById('inv-progress-fill').style.width = pct + '%';
    document.getElementById('inv-progress-text').textContent =
        (counted + 1) + ' of ' + total + ' tools';
}

function invSaveCount() {
    var toolNumber = state.invCurrentTool.tool_number;
    var body = {
        tool_number: toolNumber,
        qty_blue: parseInt(document.getElementById('inv-qty-blue').value, 10) || 0,
        qty_green: parseInt(document.getElementById('inv-qty-green').value, 10) || 0,
        qty_yellow: parseInt(document.getElementById('inv-qty-yellow').value, 10) || 0,
        qty_red: parseInt(document.getElementById('inv-qty-red').value, 10) || 0,
        employee: state.employee,
    };
    if (state.invSessionId) {
        body.session_id = state.invSessionId;
    }

    apiFetch('/api/inventory/count', { method: 'POST', body: body }).then(function(result) {
        showToast(toolNumber + ' count saved', 'success');

        if (state.invSessionId) {
            state.invHistory.push(state.invCurrentTool);
            state.invSessionCounted++;
            invLoadNextSessionItem();
        } else {
            // Quick count — show done and go back to scan
            showScreen('inventory-scan');
        }
    });
}

function invSkip() {
    if (state.invSessionId) {
        state.invHistory.push(state.invCurrentTool);
        state.invSessionCounted++;
        invLoadNextSessionItem();
    }
}

function invLoadNextSessionItem() {
    apiFetch('/api/inventory/session/' + state.invSessionId + '/next').then(function(item) {
        if (item.done) {
            // Session complete
            invCompleteSession();
            return;
        }
        state.invCurrentTool = item;
        invShowCountForm(item);
    });
}

function invCompleteSession() {
    apiFetch('/api/inventory/session/' + state.invSessionId + '/complete', {
        method: 'POST', body: {}
    }).then(function(session) {
        document.getElementById('inv-summary-counted').textContent =
            session.counted_items || 0;

        // Calculate total available across all items
        var totalAvail = 0;
        var lowStock = [];
        var allItems = (session.counted_list || []).concat(session.remaining || []);
        allItems.forEach(function(item) {
            var avail = (item.qty_green || 0) + (item.qty_blue || 0);
            totalAvail += avail;
            if (item.min_quantity != null && avail < item.min_quantity) {
                lowStock.push(item);
            }
        });
        document.getElementById('inv-summary-total-items').textContent = totalAvail;

        // Low stock warning
        var lowEl = document.getElementById('inv-summary-low-stock');
        var lowList = document.getElementById('inv-summary-low-list');
        if (lowStock.length > 0) {
            lowEl.style.display = '';
            lowList.innerHTML = '';
            lowStock.forEach(function(item) {
                var avail = (item.qty_green || 0) + (item.qty_blue || 0);
                var div = document.createElement('div');
                div.className = 'inv-low-item';
                div.textContent = item.tool_number + ' — ' +
                    (item.tool_description || '') +
                    ' (Available: ' + avail + ', Min: ' + item.min_quantity + ')';
                lowList.appendChild(div);
            });
        } else {
            lowEl.style.display = 'none';
        }

        state.invSessionId = null;
        showScreen('inventory-summary');
    });
}

function pushInventoryToProShop() {
    if (!confirm('Push cabinet inventory counts to ProShop?\nThis may take several minutes.')) return;
    showToast('Starting ProShop inventory sync...', 'info');
    apiFetch('/api/inventory/push-to-proshop', { method: 'POST' })
        .then(function(result) {
            if (result.status === 'already_running') {
                showToast('Sync already in progress', 'info');
            }
            // Poll for completion
            var pollId = setInterval(function() {
                apiFetch('/api/inventory/sync-status').then(function(s) {
                    if (s.status === 'running') return;
                    clearInterval(pollId);
                    if (s.status === 'ok') {
                        showToast('ProShop updated: ' + s.synced_tools + ' tools synced', 'success');
                    } else if (s.status === 'error') {
                        showToast('Sync error: ' + s.error, 'error');
                    }
                });
            }, 5000);
        })
        .catch(function(err) {
            showToast('Push failed: ' + (err.message || err), 'error');
        });
}

function invCheckOpenSession() {
    var resumeBar = document.getElementById('inv-resume-bar');
    resumeBar.style.display = 'none';

    apiFetch('/api/inventory/session/open').then(function(session) {
        if (session && session.session_id) {
            state._pendingResumeSession = session;
            var progressText = session.counted_items + ' of ' + session.total_items + ' counted';
            document.getElementById('inv-resume-progress').textContent = ' — ' + progressText;
            resumeBar.style.display = '';
        }
    }).catch(function() { /* no open session */ });
}

function resumeInventory() {
    var session = state._pendingResumeSession;
    if (!session) return;
    state.invSessionId = session.session_id;
    state.invSessionTotal = session.total_items;
    state.invSessionCounted = session.counted_items;
    state.invHistory = [];
    state._pendingResumeSession = null;
    invLoadNextSessionItem();
}

function invStopSession() {
    // Stop but don't complete — session stays open for resume
    showToast('Inventory paused — you can resume later', 'info');
    state.invSessionId = null;
    showScreen('inventory-menu');
}

function abandonInventorySession() {
    var session = state._pendingResumeSession;
    if (!session) return;
    apiFetch('/api/inventory/session/' + session.session_id + '/abandon', {
        method: 'POST'
    }).then(function() {
        state._pendingResumeSession = null;
        showToast('Session abandoned', 'info');
        invCheckOpenSession();
    });
}

function invCountBack() {
    if (state.invSessionId) {
        // During full inventory: go to previous tool if history exists
        if (state.invHistory.length > 0) {
            var prev = state.invHistory.pop();
            state.invSessionCounted = Math.max(0, state.invSessionCounted - 1);
            state.invCurrentTool = prev;
            invShowCountForm(prev);
        } else {
            // No history — pause session and go to menu
            invStopSession();
        }
    } else {
        showScreen('inventory-scan');
    }
}

function invJumpToTool() {
    var input = document.getElementById('inv-jump-input');
    var toolNumber = (input.value || '').trim().toUpperCase();
    if (!toolNumber) {
        showToast('Enter a tool number', 'error');
        input.focus();
        return;
    }
    input.disabled = true;

    _invFetchTool(toolNumber, function(item) {
        input.disabled = false;
        input.value = '';
        // Push current tool to history so Back returns here
        if (state.invCurrentTool) {
            state.invHistory.push(state.invCurrentTool);
        }
        state.invCurrentTool = item;
        invShowCountForm(item);
    }, function() {
        input.disabled = false;
        input.focus();
        input.select();
    });
}

// Shared fetch for inventory tool lookup — handles did_you_mean suggestions
function _invFetchTool(toolNumber, onSuccess, onFail) {
    fetch('/api/inventory/' + encodeURIComponent(toolNumber)).then(function(resp) {
        return resp.json().then(function(data) {
            if (resp.ok) {
                onSuccess(data);
            } else if (data.error === 'did_you_mean' && data.suggestion) {
                showToast('Did you mean ' + data.suggestion + '?', 'warning');
                // Auto-fill the suggestion so they can just hit Go/Enter
                var jumpInput = document.getElementById('inv-jump-input');
                var scanInput = document.getElementById('inv-scan-input');
                if (jumpInput && document.getElementById('screen-inventory-count').classList.contains('active')) {
                    jumpInput.value = data.suggestion;
                } else if (scanInput) {
                    scanInput.value = data.suggestion;
                }
                onFail();
            } else {
                showToast(toolNumber + ' not in inventory', 'warning');
                onFail();
            }
        });
    }).catch(function() {
        showToast('Cannot reach server', 'error');
        onFail();
    });
}

function showAddInventoryItem() {
    document.getElementById('inv-add-tool-number').value = '';
    document.getElementById('inv-add-description').value = '';
    document.getElementById('inv-add-location').value = '';
    document.getElementById('inv-add-min-qty').value = '';
    document.getElementById('inv-add-notes').value = '';
    showScreen('inventory-add');
}

function invAddItem() {
    var toolNum = (document.getElementById('inv-add-tool-number').value || '').trim().toUpperCase();
    if (!toolNum) {
        showToast('Tool number is required', 'error');
        return;
    }

    var minQty = document.getElementById('inv-add-min-qty').value;
    apiFetch('/api/inventory/items', {
        method: 'POST',
        body: {
            tool_number: toolNum,
            tool_description: document.getElementById('inv-add-description').value.trim(),
            cabinet_location: document.getElementById('inv-add-location').value.trim(),
            min_quantity: minQty ? parseInt(minQty, 10) : null,
            notes: document.getElementById('inv-add-notes').value.trim(),
        }
    }).then(function(item) {
        showToast(toolNum + ' added to inventory', 'success');
        // Go straight to count form for the new item
        state.invCurrentTool = item;
        invShowCountForm(item);
    });
}

// ── Inventory Video Tutorial ─────────────────────────────────────────────────

function showInventoryVideo() {
    document.getElementById('inv-video-modal').style.display = '';
    var player = document.getElementById('inv-video-player');
    player.currentTime = 0;
    player.play().catch(function() { /* autoplay may be blocked */ });
}

function closeInventoryVideo() {
    var player = document.getElementById('inv-video-player');
    player.pause();
    document.getElementById('inv-video-modal').style.display = 'none';
}
