// ── State ─────────────────────────────────────────────────────────────────────
var state = {
    employee: null,
    item: null,
    action: 'checkout',
    quantity: 0,
    screen: 'employee',
    refNumber: '',
    numpadTarget: 'wo'
};

var countdownTimer = null;
var inactivityTimer = null;
var pendingScan = null;  // holds scanned value when no employee is selected yet

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
        document.getElementById('item-preview').classList.add('hidden');
        document.getElementById('btn-continue').classList.add('hidden');
        setAction('checkout');
        setTimeout(function() { input.focus(); }, 100);
    }
    if (name === 'quantity') {
        state.quantity = 0;
        document.getElementById('numpad-value').textContent = '0';
        var refInput = document.getElementById('ref-input');
        if (refInput) { refInput.value = ''; }
        state.refNumber = '';
        setNumpadTarget('wo');
        updateConfirmButton();
    }
}

function kioskGoHome() {
    state.employee = null;
    state.item = null;
    state.action = 'checkout';
    state.quantity = 0;
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    showScreen('employee');
}

function kioskGoBack() {
    if (state.screen === 'scan') kioskGoHome();
    else if (state.screen === 'quantity') showScreen('scan');
    else if (state.screen === 'done') kioskGoHome();
}

function kioskGoToQuantity() {
    document.getElementById('qty-item-name').textContent = state.item.aka || state.item.otsId;
    document.getElementById('qty-employee').textContent = state.employee;
    document.getElementById('qty-current').textContent = parseQty(state.item.inventoryQuantity);
    // Re-apply current action to update WO/PO toggle for the quantity screen
    setAction(state.action);
    showScreen('quantity');
}

// ── Inactivity Timeout ───────────────────────────────────────────────────────

function resetInactivity() {
    if (inactivityTimer) clearTimeout(inactivityTimer);
    if (state.screen !== 'employee') {
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
    apiFetch('/api/users').then(function(users) {
        var grid = document.getElementById('employee-grid');
        grid.innerHTML = '';
        users.forEach(function(u) {
            var fullName = u.firstName + ' ' + u.lastName;
            var displayName = u.firstName + ' ' + u.lastName.charAt(0) + '.';
            var btn = document.createElement('button');
            btn.className = 'employee-btn';
            btn.textContent = displayName;
            btn.setAttribute('data-name', fullName);
            btn.onclick = function() { selectEmployee(fullName); };
            grid.appendChild(btn);
        });
    }).catch(function() {
        document.getElementById('employee-grid').innerHTML =
            '<div class="loading">Failed to load employees. Check connection.</div>';
    });
}

function selectEmployee(name) {
    state.employee = name;
    document.getElementById('selected-employee').textContent = name;
    showScreen('scan');
    // If a scan arrived before employee was selected, process it now
    if (pendingScan) {
        var val = pendingScan;
        pendingScan = null;
        document.getElementById('scan-input').value = val;
        lookupItem(val);
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
                if (val) lookupItem(val);
            }
        });
    }
    var refInput = document.getElementById('ref-input');
    if (refInput) {
        refInput.addEventListener('input', function() {
            formatWOInput(refInput);
            updateConfirmButton();
        });
        refInput.addEventListener('focus', function() {
            setNumpadTarget('wo');
        });
    }

    // Pick up ?scan= parameter (from redirect off another page)
    var params = new URLSearchParams(window.location.search);
    var scanParam = params.get('scan');
    if (scanParam) {
        // Clean the URL so a refresh doesn't re-trigger
        history.replaceState(null, '', '/');
        pendingScan = scanParam;
        showToast('Item scanned — select your name to continue', 'info');
    }

    // Global scanner detector for when focus isn't on scan-input
    // (e.g. user is on employee screen or quantity screen)
    var kioskScanBuffer = '';
    var kioskScanTimeout = null;
    document.addEventListener('keydown', function(e) {
        // Let the scan-input handle its own input normally
        if (e.target === scanInput) return;
        // Don't intercept typing in the WO ref input
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;

        if (e.key === 'Enter' && kioskScanBuffer.length >= 3) {
            e.preventDefault();
            var scanned = kioskScanBuffer;
            kioskScanBuffer = '';
            if (kioskScanTimeout) { clearTimeout(kioskScanTimeout); kioskScanTimeout = null; }

            if (state.screen === 'employee') {
                // No employee yet — stash for after selection
                pendingScan = scanned;
                showToast('Item scanned — select your name to continue', 'info');
            } else if (state.screen === 'scan') {
                // Already on scan screen, just look it up
                scanInput.value = scanned;
                lookupItem(scanned);
            }
            // On quantity/done screens, ignore stray scans
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

    loadEmployees();
});

function extractOtsId(value) {
    // Strip whitespace, trailing slashes, query strings, fragments
    value = value.trim().replace(/[\/\?#]+$/, '');
    // Strip scanner suffix characters (common: $, %, #, \r, \n)
    value = value.replace(/[\$%#\r\n]+$/, '');
    // Handle full ProShop URLs: https://traxismfg.adionsystems.com/procnc/ots/TYPE/OTS-ID
    if (value.indexOf('/procnc/ots/') !== -1) {
        var parts = value.split('/');
        return parts[parts.length - 1].trim().replace(/[\$%#\r\n]+$/, '');
    }
    // Handle any ProShop URL with the otsId as the last path segment
    if (value.indexOf('adionsystems.com') !== -1) {
        var parts = value.split('/');
        return parts[parts.length - 1].trim().replace(/[\$%#\r\n]+$/, '');
    }
    return value.trim();
}

function lookupItem(rawValue) {
    var otsId = extractOtsId(rawValue);
    var input = document.getElementById('scan-input');
    input.value = otsId;
    input.disabled = true;
    showToast('Looking up: ' + otsId, 'info');
    apiFetch('/api/cots/' + encodeURIComponent(otsId)).then(function(item) {
        state.item = item;
        document.getElementById('preview-name').textContent = item.aka || item.otsId;
        document.getElementById('preview-id').textContent = item.otsId;
        document.getElementById('preview-type').textContent = item.type || '-';
        document.getElementById('preview-location').textContent = item.location || '-';
        document.getElementById('preview-qty').textContent = parseQty(item.inventoryQuantity);
        document.getElementById('item-preview').classList.remove('hidden');
        document.getElementById('btn-continue').classList.remove('hidden');
        input.disabled = false;
    }).catch(function() {
        input.disabled = false;
        input.focus();
        input.select();
    });
}

// ── Action Toggle ────────────────────────────────────────────────────────────

function setAction(action) {
    state.action = action;
    document.getElementById('btn-action-checkout').classList.toggle('active', action === 'checkout');
    document.getElementById('btn-action-checkin').classList.toggle('active', action === 'checkin');
    updateConfirmButton();
}

// ── Numpad Target ─────────────────────────────────────────────────────────────

function setNumpadTarget(target) {
    state.numpadTarget = target;
    var woArea = document.getElementById('ref-input-area');
    var qtyArea = document.getElementById('qty-numpad-area');
    if (woArea) woArea.classList.toggle('numpad-target', target === 'wo');
    if (qtyArea) qtyArea.classList.toggle('numpad-target', target === 'qty');
}

// ── Numpad ────────────────────────────────────────────────────────────────────

function numpadPress(digit) {
    if (state.numpadTarget === 'wo') {
        var refInput = document.getElementById('ref-input');
        var digits = refInput.value.replace(/[^0-9]/g, '');
        if (digits.length >= 6) return;
        digits += digit;
        if (digits.length > 2) {
            refInput.value = digits.slice(0, 2) + '-' + digits.slice(2);
        } else {
            refInput.value = digits;
        }
        if (digits.length >= 6) {
            setNumpadTarget('qty');
        }
        updateConfirmButton();
        return;
    }
    var current = String(state.quantity);
    if (current === '0') current = '';
    current += digit;
    state.quantity = parseInt(current, 10) || 0;
    document.getElementById('numpad-value').textContent = state.quantity;
    updateConfirmButton();
}

function numpadClear() {
    if (state.numpadTarget === 'wo') {
        document.getElementById('ref-input').value = '';
        updateConfirmButton();
        return;
    }
    state.quantity = 0;
    document.getElementById('numpad-value').textContent = '0';
    updateConfirmButton();
}

function numpadBackspace() {
    if (state.numpadTarget === 'wo') {
        var refInput = document.getElementById('ref-input');
        var digits = refInput.value.replace(/[^0-9]/g, '');
        digits = digits.slice(0, -1);
        if (digits.length > 2) {
            refInput.value = digits.slice(0, 2) + '-' + digits.slice(2);
        } else {
            refInput.value = digits;
        }
        updateConfirmButton();
        return;
    }
    var s = String(state.quantity);
    s = s.slice(0, -1);
    state.quantity = parseInt(s, 10) || 0;
    document.getElementById('numpad-value').textContent = state.quantity || '0';
    updateConfirmButton();
}

function updateConfirmButton() {
    var btn = document.getElementById('btn-confirm');
    var refInput = document.getElementById('ref-input');
    state.refNumber = (refInput ? refInput.value.trim() : '');
    btn.disabled = !(state.quantity > 0 && state.refNumber.length > 0);
}

// ── Confirm ──────────────────────────────────────────────────────────────────

function kioskConfirm() {
    var btn = document.getElementById('btn-confirm');
    btn.disabled = true;
    btn.textContent = 'Processing...';

    var url = '/api/cots/' + encodeURIComponent(state.item.otsId) + '/' + state.action;
    apiFetch(url, {
        method: 'POST',
        body: { employee: state.employee, quantity: state.quantity, ref_type: 'wo', ref_number: state.refNumber }
    }).then(function(result) {
        var verb = state.action === 'checkout' ? 'Item Out' : 'Item In';
        document.getElementById('done-headline').textContent =
            verb + ' ' + state.quantity + 'x ' + (state.item.aka || state.item.otsId);
        var refTag = 'WO: ' + state.refNumber;
        document.getElementById('done-details').textContent =
            state.employee + ' | ' + refTag;

        var warning = document.getElementById('low-stock-warning');
        if (result.below_minimum) {
            document.getElementById('low-stock-message').textContent =
                'Stock is at ' + result.new_quantity + ' (minimum: ' + result.minimum_quantity + ')';
            warning.classList.remove('hidden');
        } else {
            warning.classList.add('hidden');
        }

        showScreen('done');
        startCountdown();
        btn.textContent = 'Confirm';
    }).catch(function() {
        btn.disabled = false;
        btn.textContent = 'Confirm';
    });
}

// ── Countdown ────────────────────────────────────────────────────────────────

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

function formatWOInput(input) {
    var digits = input.value.replace(/[^0-9]/g, '');
    if (digits.length > 6) digits = digits.slice(0, 6);
    if (digits.length > 2) {
        input.value = digits.slice(0, 2) + '-' + digits.slice(2);
    } else {
        input.value = digits;
    }
}

function parseQty(val) {
    if (val === null || val === undefined || val === '') return 0;
    var n = parseFloat(val);
    return isNaN(n) ? 0 : Math.floor(n);
}
