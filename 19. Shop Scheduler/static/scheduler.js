// ── Shop Scheduler — Gantt Board Logic ───────────────────────────────────────

let ec = null;          // EventCalendar instance
let machines = [];
let backlogOps = [];
let suggestionsMap = {}; // opId → suggestion
let skippedMap = {};    // opId → { reason }
let currentZoom = '3day';
let draggedOp = null;   // Currently dragged backlog item
let selectedOp = null;  // Click-to-schedule: selected backlog op
let allEvents = [];     // Full unfiltered events list for board filters

const undoStack = [];   // Undo history (max 20 entries)
const UNDO_MAX = 20;

const ZOOM_LEVELS = ['day', '3day', 'week', 'month'];
const BH_START = 5;   // Business hours start (5 AM) — matches config.py
const BH_END = 18;    // Business hours end (6 PM)

/** Count business hours between two dates (inverse of addBusinessHours). */
function businessHoursBetween(start, end) {
    let hours = 0;
    let cursor = new Date(start);
    const endMs = new Date(end).getTime();

    for (let i = 0; i < 500 && cursor.getTime() < endMs; i++) {
        // Skip weekends
        while (cursor.getDay() === 0 || cursor.getDay() === 6) {
            cursor.setDate(cursor.getDate() + 1);
            cursor.setHours(BH_START, 0, 0, 0);
        }
        if (cursor.getTime() >= endMs) break;

        // Snap to business hours
        if (cursor.getHours() < BH_START) {
            cursor.setHours(BH_START, 0, 0, 0);
        }
        if (cursor.getTime() >= endMs) break;
        if (cursor.getHours() >= BH_END) {
            cursor.setDate(cursor.getDate() + 1);
            cursor.setHours(BH_START, 0, 0, 0);
            continue;
        }

        // Count business hours in this day slice
        const dayEnd = new Date(cursor);
        dayEnd.setHours(BH_END, 0, 0, 0);
        const sliceEnd = Math.min(dayEnd.getTime(), endMs);
        hours += (sliceEnd - cursor.getTime()) / 3600000;

        cursor.setDate(cursor.getDate() + 1);
        cursor.setHours(BH_START, 0, 0, 0);
    }
    return hours;
}

/** Add working hours to a start date, skipping nights and weekends. */
function addBusinessHours(start, hours) {
    let remaining = hours;
    let cursor = new Date(start);

    for (let i = 0; i < 500 && remaining > 0; i++) {
        // Skip weekends (0=Sun, 6=Sat)
        while (cursor.getDay() === 0 || cursor.getDay() === 6) {
            cursor.setDate(cursor.getDate() + 1);
            cursor.setHours(BH_START, 0, 0, 0);
        }
        // Before business hours — snap to start
        if (cursor.getHours() < BH_START) {
            cursor.setHours(BH_START, 0, 0, 0);
        }
        // After business hours — next day
        if (cursor.getHours() >= BH_END) {
            cursor.setDate(cursor.getDate() + 1);
            cursor.setHours(BH_START, 0, 0, 0);
            continue;
        }
        // Hours left in the current business day
        const dayEnd = new Date(cursor);
        dayEnd.setHours(BH_END, 0, 0, 0);
        const available = (dayEnd - cursor) / 3600000;

        if (remaining <= available) {
            cursor = new Date(cursor.getTime() + remaining * 3600000);
            remaining = 0;
        } else {
            remaining -= available;
            cursor.setDate(cursor.getDate() + 1);
            cursor.setHours(BH_START, 0, 0, 0);
        }
    }
    return cursor;
}

/**
 * Convert a cursor X pixel position to a calendar datetime.
 *
 * Uses the calendar's timeline content area bounds and the known
 * date/duration options — purely mathematical, no DOM hit-testing needed.
 * Call this BEFORE removing the overlay (it reads calendar DOM bounds,
 * which are stable regardless of overlay state).
 *
 * Also snaps to the nearest slot boundary so the block aligns to the grid.
 */
function dateFromCursorX(clientX) {
    const calEl = document.getElementById('gantt-calendar');
    if (!ec || !calEl) return null;

    try {
        const dateOpt = ec.getOption('date');
        const durOpt = ec.getOption('duration');
        const slotOpt = ec.getOption('slotDuration');
        const startDate = new Date(dateOpt);
        if (isNaN(startDate)) return null;

        // Convert duration to ms
        let durationMs = 14 * 86400000; // default 14 days
        if (durOpt) {
            if (durOpt.days) durationMs = durOpt.days * 86400000;
            else if (durOpt.weeks) durationMs = durOpt.weeks * 7 * 86400000;
        }

        // Parse slot duration for snapping (e.g. "02:00:00" → 2h, or {days:1})
        let slotMs = 2 * 3600000; // default 2h
        if (slotOpt) {
            if (typeof slotOpt === 'string') {
                const parts = slotOpt.split(':').map(Number);
                slotMs = ((parts[0] || 0) * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0)) * 1000;
            } else if (slotOpt.days) {
                slotMs = slotOpt.days * 86400000;
            } else if (slotOpt.hours) {
                slotMs = slotOpt.hours * 3600000;
            }
        }

        // Find the timeline content area (EXCLUDING the sidebar with machine labels).
        // Strategy: find the sidebar, then the timeline is everything to its right.
        const sidebar = calEl.querySelector('.ec-sidebar, .ec-resource-header');
        const calRect = calEl.getBoundingClientRect();
        let timelineLeft, timelineWidth;

        if (sidebar) {
            const sr = sidebar.getBoundingClientRect();
            timelineLeft = sr.right;
            timelineWidth = calRect.right - sr.right;
        } else {
            // Try specific content selectors (NOT .ec-body which includes sidebar)
            const contentArea = calEl.querySelector('.ec-body .ec-content, .ec-content, .ec-days');
            if (contentArea) {
                const cr = contentArea.getBoundingClientRect();
                timelineLeft = cr.left;
                timelineWidth = cr.width;
            } else {
                // Last resort: assume resource labels take ~120px on the left
                timelineLeft = calRect.left + 120;
                timelineWidth = calRect.width - 120;
            }
        }

        const frac = Math.max(0, Math.min(1, (clientX - timelineLeft) / timelineWidth));
        const rawMs = startDate.getTime() + frac * durationMs;

        // Snap to nearest slot boundary
        const snappedMs = Math.round(rawMs / slotMs) * slotMs;
        const result = new Date(snappedMs);

        console.log('dateFromCursorX:', {
            clientX,
            timelineLeft: Math.round(timelineLeft),
            timelineWidth: Math.round(timelineWidth),
            frac: frac.toFixed(3),
            viewStart: startDate.toISOString(),
            durationDays: (durationMs / 86400000).toFixed(1),
            result: result.toString(),
        });

        return result;
    } catch (e) {
        console.warn('dateFromCursorX failed:', e);
        return null;
    }
}

/** Last-resort fallback: snap to next business-hours start. */
function dateFromFallback() {
    const now = new Date();
    if (now.getHours() >= BH_END) {
        now.setDate(now.getDate() + 1);
    }
    while (now.getDay() === 0 || now.getDay() === 6) {
        now.setDate(now.getDate() + 1);
    }
    now.setHours(Math.max(BH_START, now.getHours()), 0, 0, 0);
    return now;
}

/** Format a Date as local ISO string (no UTC shift). */
function toLocalISO(d) {
    const pad = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate())
        + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}

// ── Undo Stack ───────────────────────────────────────────────────────────────

function pushUndo(entry) {
    undoStack.push(entry);
    if (undoStack.length > UNDO_MAX) undoStack.shift();
    updateUndoButton();
}

function updateUndoButton() {
    const btn = document.getElementById('btn-undo');
    if (!btn) return;
    if (undoStack.length === 0) {
        btn.disabled = true;
        btn.textContent = 'Undo';
    } else {
        btn.disabled = false;
        btn.textContent = `Undo (${undoStack.length})`;
    }
}

async function performUndo() {
    if (undoStack.length === 0) return;
    const entry = undoStack.pop();
    updateUndoButton();

    try {
        switch (entry.type) {
            case 'create':
                // Undo a create → delete the block
                await fetchJSON(`/api/blocks/${entry.blockId}`, { method: 'DELETE' });
                break;
            case 'move':
            case 'resize':
                // Undo a move/resize → PUT old values back
                await fetchJSON(`/api/blocks/${entry.blockId}`, {
                    method: 'PUT',
                    body: entry.oldState,
                });
                break;
            case 'delete':
                // Undo a delete → recreate the block
                await fetchJSON('/api/blocks', {
                    method: 'POST',
                    body: entry.recreate,
                });
                break;
            case 'batch-create':
                // Undo auto-schedule → delete all created blocks
                for (const id of entry.blockIds) {
                    try {
                        await fetchJSON(`/api/blocks/${id}`, { method: 'DELETE' });
                    } catch (_) {}
                }
                break;
            case 'swap':
                // Undo a swap → swap them back
                await fetchJSON('/api/blocks/swap', {
                    method: 'POST',
                    body: { block_a: entry.blockA, block_b: entry.blockB },
                });
                break;
        }
        showToast(`Undone: ${entry.description}`, 3000);
        refreshEvents();
        loadBacklog();
    } catch (e) {
        console.error('Undo failed:', e);
        showToast('Undo failed: ' + (e.message || 'Unknown error'));
    }
}

// ── Initialization ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    try {
        machines = await fetchJSON('/api/machines');
    } catch (e) {
        document.getElementById('gantt-calendar').innerHTML =
            '<div class="empty-state" style="padding:40px"><p>Failed to load machines: ' + e.message + '</p></div>';
        return;
    }

    // Init controls and backlog FIRST (these must work regardless of calendar)
    try {
        initControls();
    } catch (e) {
        console.error('initControls failed:', e);
        document.getElementById('gantt-calendar').innerHTML =
            '<div class="empty-state" style="padding:40px"><p>Controls init failed: ' + e.message + '</p></div>';
    }

    loadBacklog();

    // Then try the calendar (may fail if library has issues)
    try {
        await initCalendar();
    } catch (e) {
        console.error('Calendar init failed:', e);
        document.getElementById('gantt-calendar').innerHTML =
            '<div class="empty-state" style="padding:40px"><p>Calendar failed to load.</p><p style="color:var(--text-subtle);margin-top:8px">' + e.message + '</p></div>';
    }

    // Swap detection during block drags
    initSwapDetection();

    // Wheel zoom on the calendar
    initWheelZoom();

    // Machine ops click handler (after calendar renders)
    initMachineOpsClick();

    // Init board filters (after calendar so allEvents is populated)
    initFilters();

    // Refresh blocks every 30s
    setInterval(refreshEvents, 30000);

    // Drop overlay is created dynamically during drag
});

async function refreshEvents() {
    if (!ec) return;
    try {
        allEvents = (await fetchJSON('/api/blocks')).filter(e =>
            e.start && e.end && !isNaN(new Date(e.start)) && !isNaN(new Date(e.end))
        );
        populateCustomerFilter(allEvents);
        populateMaterialTypeFilter(allEvents);
        applyFilters();
    } catch (e) {
        console.error('Failed to refresh events:', e);
    }
}

async function initCalendar() {
    const resources = machines.map(m => ({
        id: m.id,
        title: m.name,
    }));

    const zoomConfig = getZoomConfig(currentZoom);

    // Load initial events (filter out any with bad dates)
    allEvents = (await fetchJSON('/api/blocks')).filter(e =>
        e.start && e.end && !isNaN(new Date(e.start)) && !isNaN(new Date(e.end))
    );
    const events = allEvents;

    const calEl = document.getElementById('gantt-calendar');

    // Try the EventCalendar CDN build
    if (typeof EventCalendar === 'undefined') {
        throw new Error('EventCalendar library not loaded');
    }

    // The CDN build uses EventCalendar.create() or new EventCalendar()
    const createFn = EventCalendar.create || EventCalendar;
    const calOpts = {
            view: 'resourceTimelineDay',
            resources, events,
            headerToolbar: { start: 'prev,next', center: 'title', end: '' },
            slotDuration: zoomConfig.slotDuration,
            duration: zoomConfig.duration,
            scrollTime: '05:00:00',
            slotMinTime: '05:00:00',
            slotMaxTime: '18:00:00',
            hiddenDays: [0, 6],  // Hide Sunday (0) and Saturday (6)
            editable: true,
            eventStartEditable: true,
            eventDurationEditable: true,
            nowIndicator: true,
            height: '100%',
            eventContent: (info) => renderBlockContent(info),
            eventDrop: (info) => handleBlockMove(info),
            eventResize: (info) => handleBlockResize(info),
            eventClick: (info) => showBlockDetails(info.event),
    };

    ec = typeof createFn === 'function' && createFn !== EventCalendar
        ? createFn(calEl, calOpts)
        : new EventCalendar(calEl, calOpts);
}

// ── Zoom Config ──────────────────────────────────────────────────────────────

function getZoomConfig(zoom) {
    switch (zoom) {
        case 'day':
            return { duration: { days: 2 }, slotDuration: '01:00:00' };
        case '3day':
            return { duration: { days: 4 }, slotDuration: '02:00:00' };
        case 'week':
            return { duration: { days: 8 }, slotDuration: '04:00:00' };
        case 'month':
            return { duration: { days: 35 }, slotDuration: { days: 1 } };
        default:
            return { duration: { days: 4 }, slotDuration: '02:00:00' };
    }
}

function setZoom(level) {
    currentZoom = level;
    if (!ec) return;
    const cfg = getZoomConfig(level);
    ec.setOption('slotDuration', cfg.slotDuration);
    ec.setOption('duration', cfg.duration);
    document.querySelectorAll('.zoom-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.zoom === level);
    });
    // Re-apply events after zoom change so they render in new view
    applyFilters();
}

function initWheelZoom() {
    var calEl = document.getElementById('gantt-calendar');
    if (!calEl) return;
    calEl.addEventListener('wheel', function(e) {
        if (!e.ctrlKey) return;
        e.preventDefault();
        var idx = ZOOM_LEVELS.indexOf(currentZoom);
        if (e.deltaY > 0 && idx < ZOOM_LEVELS.length - 1) {
            setZoom(ZOOM_LEVELS[idx + 1]);
        } else if (e.deltaY < 0 && idx > 0) {
            setZoom(ZOOM_LEVELS[idx - 1]);
        }
    }, { passive: false });
}

// ── Block Content Renderer ───────────────────────────────────────────────────

function renderBlockContent(info) {
    const props = info.event.extendedProps || {};
    const progress = props.progress || 0;
    const isEst = props.is_estimated;
    const isLocked = props.is_locked;
    const r = props.readiness || {};

    let classes = 'block-label';
    if (isLocked) classes += ' block-locked';

    let html = `<div class="${classes}">`;
    html += `<strong>${info.event.title}</strong>`;
    if (isEst) html += `<span class="block-est-badge">EST</span>`;
    if (props.part_name) html += `<br><span style="opacity:0.8">${props.part_name}</span>`;
    if (progress > 0) {
        html += `<div class="block-progress" style="width:${progress}%"></div>`;
    }
    // Readiness dots in bottom-right corner
    html += `<div class="block-readiness">`;
    html += `<span class="light ${r.program_ready ? 'green' : 'red'}" title="Program"></span>`;
    html += `<span class="light ${r.material_ready ? 'green' : 'red'}" title="Material"></span>`;
    html += `<span class="light ${r.tools_ready ? 'green' : 'yellow'}" title="Tools"></span>`;
    html += `<span class="light ${r.machine_ready ? 'green' : 'gray'}" title="Machine"></span>`;
    html += `</div>`;
    html += '</div>';

    return { html };
}

// ── Edge-Scroll During Drag ──────────────────────────────────────────────────
// When dragging near the left/right edge of the calendar, auto-scroll by 1 day.

let _edgeScrollInterval = null;
let _edgeScrollLastDir = 0; // -1 = left, +1 = right, 0 = none
const EDGE_SCROLL_ZONE = 60;      // px from edge to trigger
const EDGE_SCROLL_DELAY = 1200;   // ms between scroll steps

function startEdgeScrollCheck(clientX) {
    const calEl = document.getElementById('gantt-calendar');
    if (!calEl || !ec) return;

    // Find the timeline area (exclude sidebar with machine labels)
    const sidebar = calEl.querySelector('.ec-sidebar, .ec-resource-header');
    const calRect = calEl.getBoundingClientRect();
    let timelineLeft = calRect.left + 120;
    let timelineRight = calRect.right;
    if (sidebar) {
        timelineLeft = sidebar.getBoundingClientRect().right;
    }

    let dir = 0;
    if (clientX < timelineLeft + EDGE_SCROLL_ZONE && clientX > calRect.left) {
        dir = -1; // scroll left (earlier dates)
    } else if (clientX > timelineRight - EDGE_SCROLL_ZONE && clientX < calRect.right) {
        dir = 1;  // scroll right (later dates)
    }

    if (dir === _edgeScrollLastDir) return; // no change
    _edgeScrollLastDir = dir;
    stopEdgeScroll();

    if (dir !== 0) {
        // Wait before first scroll so brief passes near edge don't jump
        _edgeScrollInterval = setInterval(() => edgeScrollStep(dir), EDGE_SCROLL_DELAY);
    }
}

function edgeScrollStep(dir) {
    if (!ec) return;
    const current = new Date(ec.getOption('date'));
    current.setDate(current.getDate() + dir);
    ec.setOption('date', current);
}

function stopEdgeScroll() {
    if (_edgeScrollInterval) {
        clearInterval(_edgeScrollInterval);
        _edgeScrollInterval = null;
    }
    _edgeScrollLastDir = 0;
}

// ── Swap Detection (visual hover indicator during block drags) ───────────────

let swapTarget = null;  // Block ID of the event we'd swap with

function initSwapDetection() {
    const calEl = document.getElementById('gantt-calendar');
    if (!calEl) return;

    let dragging = false;
    let draggedBlockId = null;

    // Detect when a block drag starts (pointerdown on .ec-event)
    calEl.addEventListener('pointerdown', (e) => {
        const eventEl = e.target.closest('.ec-event');
        if (!eventEl) return;
        // Find the block_id from allEvents by matching the DOM element
        draggedBlockId = getBlockIdFromEventEl(eventEl);
        // We don't know if this is a drag or click yet — wait for pointermove
        dragging = false;
    });

    calEl.addEventListener('pointermove', (e) => {
        if (draggedBlockId === null) return;
        dragging = true;

        // Edge-scroll when near calendar edges during block drag
        startEdgeScrollCheck(e.clientX);

        // Check multiple points around cursor to detect overlap in any direction
        const offsets = [0, -30, -60, 30, 60];
        let foundTarget = null;

        for (const ox of offsets) {
            const els = document.elementsFromPoint(e.clientX + ox, e.clientY);
            for (const el of els) {
                const eventEl = el.closest('.ec-event');
                if (!eventEl) continue;
                const bid = getBlockIdFromEventEl(eventEl);
                if (bid && bid !== draggedBlockId) {
                    foundTarget = { el: eventEl, blockId: bid };
                    break;
                }
            }
            if (foundTarget) break;
        }

        // Update swap indicator
        if (foundTarget && foundTarget.blockId !== swapTarget?.blockId) {
            clearSwapIndicator();
            swapTarget = foundTarget;
            showSwapIndicator(foundTarget.el);
        } else if (!foundTarget && swapTarget) {
            clearSwapIndicator();
            swapTarget = null;
        }
    });

    document.addEventListener('pointerup', () => {
        dragging = false;
        draggedBlockId = null;
        stopEdgeScroll();
        // Don't clear swapTarget here — handleBlockMove needs it
        // It gets cleared after the swap or on next drag
        setTimeout(() => {
            clearSwapIndicator();
            swapTarget = null;
        }, 200);
    });
}

function getBlockIdFromEventEl(eventEl) {
    // Match the event DOM element to our allEvents data
    // EventCalendar stores event data; we extract from rendered content
    const label = eventEl.querySelector('.block-label strong');
    if (!label) return null;
    const title = label.textContent.trim();
    const evt = allEvents.find(e => e.title === title);
    return evt?.extendedProps?.block_id || null;
}

function showSwapIndicator(eventEl) {
    // Add a "Swap?" overlay on the target event
    eventEl.classList.add('swap-target');
    let badge = eventEl.querySelector('.swap-badge');
    if (!badge) {
        badge = document.createElement('div');
        badge.className = 'swap-badge';
        badge.textContent = 'Release to swap';
        eventEl.appendChild(badge);
    }
}

function clearSwapIndicator() {
    document.querySelectorAll('.swap-target').forEach(el => {
        el.classList.remove('swap-target');
        const badge = el.querySelector('.swap-badge');
        if (badge) badge.remove();
    });
}

// ── Block Drag/Drop Handlers ─────────────────────────────────────────────────

async function handleBlockMove(info) {
    const blockId = info.event.extendedProps?.block_id;
    if (!blockId) return;

    if (info.event.extendedProps?.is_locked) {
        showToast('Block is locked — unlock it first');
        info.revert();
        return;
    }

    let start = info.event.start;
    let end = info.event.end;

    // Validate we have usable dates
    if (!start || isNaN(start.getTime())) {
        console.warn('Block move: invalid start date', start);
        showToast('Drag failed — could not determine drop time');
        info.revert();
        return;
    }

    // Sanity check: if event landed more than 90 days from now, it's a drag glitch
    const now = new Date();
    if (Math.abs(start - now) > 90 * 86400000) {
        console.warn('Block move landed at unreasonable time:', start);
        showToast('Drag landed off-screen — reverted');
        info.revert();
        return;
    }

    // Preserve original business-hours duration so the block stays the same
    // visual size regardless of where it lands on the timeline.
    if (info.oldEvent && info.oldEvent.start && info.oldEvent.end) {
        const bhHours = businessHoursBetween(info.oldEvent.start, info.oldEvent.end);
        end = addBusinessHours(start, bhHours || 1);
    }

    if (!end || isNaN(end.getTime())) {
        end = addBusinessHours(start, 1); // default 1h if end is missing
    }

    // Determine the target machine.
    // newResource is only set when moving BETWEEN resources; for same-machine
    // slides it's undefined, so fall back to oldResource or extendedProps.
    const machineId = info.newResource?.id          // cross-machine move
        || info.oldResource?.id                     // same-machine slide (vkurko)
        || info.event.resourceId                    // direct property
        || (Array.isArray(info.event.resourceIds) ? info.event.resourceIds[0] : null)
        || info.event.extendedProps?.machine_id     // our custom fallback
        || info.event.getResources?.()[0]?.id;

    if (!machineId) {
        // Log full info for debugging in case this still triggers
        console.warn('Block move: could not determine target machine.',
            'info keys:', Object.keys(info),
            'event keys:', Object.keys(info.event),
            'extendedProps:', info.event.extendedProps);
        showToast('Drag failed — could not determine target machine');
        info.revert();
        return;
    }

    // Capture old state for undo
    const oldMachineId = info.oldResource?.id
        || info.event.extendedProps?.machine_id;
    const oldStart = info.oldEvent?.start;
    const oldEnd = info.oldEvent?.end;

    // Try the move — if overlap, offer swap
    const resp = await fetch(`/api/blocks/${blockId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            machine_id: machineId,
            start_time: toLocalISO(start),
            end_time: toLocalISO(end),
        }),
    });

    if (resp.ok) {
        pushUndo({
            type: 'move',
            description: `${info.event.title} moved`,
            blockId,
            oldState: {
                machine_id: oldMachineId,
                start_time: oldStart ? toLocalISO(oldStart) : null,
                end_time: oldEnd ? toLocalISO(oldEnd) : null,
            },
        });
        refreshEvents();
    } else if (resp.status === 409) {
        const err = await resp.json();
        if (err.conflict && err.conflict.id) {
            // Overlap detected — auto-swap (user saw "Release to swap" indicator)
            const c = err.conflict;
            try {
                await fetchJSON('/api/blocks/swap', {
                    method: 'POST',
                    body: { block_a: blockId, block_b: c.id },
                });
                pushUndo({
                    type: 'swap',
                    description: `${info.event.title} swapped with WO${c.wo_number} Op${c.op_number}`,
                    blockA: blockId,
                    blockB: c.id,
                });
                showToast(`Swapped with WO${c.wo_number} Op${c.op_number}`, 3000);
                refreshEvents();
            } catch (swapErr) {
                showToast('Swap failed: ' + (swapErr.message || 'Unknown error'));
                info.revert();
            }
        } else {
            showToast(err.error || 'Overlap — move rejected', 6000);
            info.revert();
        }
    } else {
        const err = await resp.json().catch(() => ({}));
        showToast(err.error || 'Failed to move block');
        info.revert();
    }
}

async function handleBlockResize(info) {
    const blockId = info.event.extendedProps?.block_id;
    if (!blockId) return;

    const oldEnd = info.oldEvent?.end;

    try {
        await fetchJSON(`/api/blocks/${blockId}`, {
            method: 'PUT',
            body: { end_time: toLocalISO(info.event.end) },
        });
        pushUndo({
            type: 'resize',
            description: `${info.event.title} resized`,
            blockId,
            oldState: {
                end_time: oldEnd ? toLocalISO(oldEnd) : null,
            },
        });
    } catch (e) {
        console.error('Failed to resize block:', e);
        showToast(e.message || 'Failed to resize block');
        info.revert();
    }
}

// ── Backlog ──────────────────────────────────────────────────────────────────

async function loadBacklog() {
    try {
        backlogOps = await fetchJSON('/api/operations?unscheduled=true&schedulable=true');
        await loadSuggestions();
        renderBacklog(backlogOps);
    } catch (e) {
        console.error('Failed to load backlog:', e);
    }
}

async function loadSuggestions() {
    try {
        const result = await fetchJSON('/api/suggestions');
        suggestionsMap = {};
        skippedMap = {};
        (result.suggestions || []).forEach(s => { suggestionsMap[s.op_id] = s; });
        (result.skipped || []).forEach(s => { skippedMap[s.op_id] = s; });
    } catch (e) {
        console.error('Failed to load suggestions:', e);
        suggestionsMap = {};
        skippedMap = {};
    }
}

function renderBacklog(ops) {
    const container = document.getElementById('backlog-items');
    document.getElementById('backlog-count').textContent = ops.length;

    if (ops.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>All operations are scheduled!</p></div>';
        return;
    }

    container.innerHTML = ops.map(op => {
        const dueClass = getDueClass(op.due_date);
        const estClass = op.is_estimated ? 'estimated' : '';
        const hours = op.override_hours || op.est_hours || 1;
        const dueText = formatDueDate(op.due_date);
        const fmtHours = typeof hours === 'number' ? hours.toFixed(1) : hours;

        // Suggestion chip or skip warning
        const sug = suggestionsMap[op.id];
        const skip = skippedMap[op.id];
        let chipHtml = '';
        let skipClass = '';
        if (skip) {
            skipClass = 'backlog-skipped';
            chipHtml = `<span class="skip-warning" title="${skip.reason}">${skip.reason}</span>`;
        } else if (sug) {
            const st = new Date(sug.start_time);
            const timeStr = st.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                + ' ' + st.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
            const chipClass = sug.urgency === 'past-due' ? 'suggest-past-due'
                : sug.urgency === 'urgent' ? 'suggest-urgent'
                : op.machine_id ? 'suggest-assigned' : 'suggest-auto';
            const toolBadge = sug.tool_total > 0 ? ` <span class="tool-badge">(${sug.tool_match}/${sug.tool_total} tools)</span>` : '';
            chipHtml = `<button class="suggest-chip ${chipClass}" data-op-id="${op.id}" title="${sug.reasons.join(', ')}">&#8594; ${sug.machine_name}, ${timeStr}${toolBadge}</button>`;
        }

        // Readiness lights
        const r = op.readiness || {};
        const lightsHtml = renderReadinessLights(r);

        return `
            <div class="backlog-item ${estClass} ${skipClass}" draggable="true"
                 data-op-id="${op.id}" data-hours="${hours}"
                 data-wo="${op.wo_number}" data-op="${op.op_number}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <span class="wo-label">WO${op.wo_number} Op${op.op_number}</span>
                    ${lightsHtml}
                </div>
                <span class="op-label">${op.part_name || op.op_name || ''}</span>
                <span class="op-label" ${op.is_estimated ? 'style="font-style:italic"' : ''}>${op.is_estimated ? 'EST ' : ''}${fmtHours}h</span>
                <span class="due-label ${dueClass}">${dueText}</span>
                ${chipHtml}
            </div>
        `;
    }).join('');

    // Attach suggestion chip click handlers
    container.querySelectorAll('.suggest-chip').forEach(chip => {
        chip.addEventListener('click', async (e) => {
            e.stopPropagation();
            const opId = chip.dataset.opId;
            const sug = suggestionsMap[opId];
            if (!sug) return;
            chip.disabled = true;
            chip.textContent = 'Scheduling...';
            try {
                const sugResult = await fetchJSON('/api/blocks', {
                    method: 'POST',
                    body: {
                        operation_id: sug.op_id,
                        machine_id: sug.machine_id,
                        start_time: sug.start_time,
                        end_time: sug.end_time,
                        created_by: 'auto-suggest',
                    },
                });
                pushUndo({
                    type: 'create',
                    description: `suggestion → ${sug.machine_name}`,
                    blockId: sugResult.id,
                });
                refreshEvents();
                loadBacklog();
            } catch (err) {
                console.error('Failed to schedule suggestion:', err);
                showToast(err.message || 'Failed to schedule');
                chip.textContent = 'Failed';
                chip.disabled = false;
            }
        });
    });

    // Attach right-click context menu for hiding WOs/ops
    container.querySelectorAll('.backlog-item').forEach(el => {
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showBacklogContextMenu(e.pageX, e.pageY, el.dataset.wo, el.dataset.opId);
        });
    });

    // Attach drag handlers
    container.querySelectorAll('.backlog-item').forEach(el => {
        el.addEventListener('dragstart', (e) => {
            const opData = {
                id: el.dataset.opId,
                hours: parseFloat(el.dataset.hours) || 1,
                wo: el.dataset.wo,
                op: el.dataset.op,
            };
            draggedOp = opData;
            // Store full JSON in text/plain so dataTransfer fallback works reliably
            const json = JSON.stringify(opData);
            e.dataTransfer.setData('text/plain', json);
            e.dataTransfer.setData('application/json', json);
            e.dataTransfer.effectAllowed = 'move';
            // Fix: lock the item's size so flex-wrap doesn't reflow all items
            const rect = el.getBoundingClientRect();
            el.style.width = rect.width + 'px';
            el.style.height = rect.height + 'px';
            el.style.opacity = '0.4';
            // Freeze backlog scroll during drag
            container.style.overflowY = 'hidden';
            // Show drop overlay after a tick (so drag image captures first)
            setTimeout(() => showDropOverlay(), 0);
        });
        el.addEventListener('dragend', () => {
            el.style.opacity = '1';
            el.style.width = '';
            el.style.height = '';
            container.style.overflowY = '';
            // Delay clearing draggedOp and overlay so drop handler runs first
            setTimeout(() => {
                draggedOp = null;
                hideDropOverlay();
            }, 100);
        });
    });
}

// ── Drop Overlay — transparent zones over calendar per machine row ───────────

function showDropOverlay() {
    // Remove existing
    hideDropOverlay();

    const calEl = document.getElementById('gantt-calendar');
    const calRect = calEl.getBoundingClientRect();

    const overlay = document.createElement('div');
    overlay.id = 'drop-overlay';
    overlay.style.cssText = `position:fixed;inset:0;z-index:150;pointer-events:all;`;

    // Detect sidebar width for sidebar vs timeline split
    const sidebarEl = calEl.querySelector('.ec-sidebar, .ec-resource-header');
    let sidebarRight = calRect.left + 120; // fallback
    if (sidebarEl) {
        sidebarRight = sidebarEl.getBoundingClientRect().right;
    }

    // Find resource rows — try multiple selectors for vkurko EventCalendar
    const resourceEls = Array.from(
        calEl.querySelectorAll('.ec-resource')
    );
    // Also find the body rows (timeline lanes) which may differ from label elements
    const bodyRows = Array.from(
        calEl.querySelectorAll('.ec-body .ec-resource, .ec-body tr, .ec-timeline .ec-resource')
    );
    // Use whichever set has the right count; prefer bodyRows for position accuracy
    const rowEls = bodyRows.length === machines.length ? bodyRows
        : resourceEls.length === machines.length ? resourceEls
        : resourceEls;

    console.log(`Drop overlay: ${rowEls.length} row elements for ${machines.length} machines (body: ${bodyRows.length}, resource: ${resourceEls.length})`);

    // Helper: extract dragged op from event (try global, then dataTransfer)
    function extractOp(e) {
        let op = draggedOp;
        if (!op) {
            // Try application/json first, then text/plain (which also has JSON)
            for (const mime of ['application/json', 'text/plain']) {
                try {
                    const raw = e.dataTransfer.getData(mime);
                    if (raw) {
                        const parsed = JSON.parse(raw);
                        if (parsed && parsed.id) { op = parsed; break; }
                    }
                } catch (_) {}
            }
        }
        draggedOp = null;
        return op;
    }

    // Helper: schedule op on machine at a specific time (timeline drop)
    async function scheduleAtTime(op, machine, dropDate) {
        // Snap to business hours
        if (dropDate.getHours() < BH_START) {
            dropDate.setHours(BH_START, 0, 0, 0);
        } else if (dropDate.getHours() >= BH_END) {
            dropDate.setDate(dropDate.getDate() + 1);
            dropDate.setHours(BH_START, 0, 0, 0);
        }
        while (dropDate.getDay() === 0 || dropDate.getDay() === 6) {
            dropDate.setDate(dropDate.getDate() + 1);
            dropDate.setHours(BH_START, 0, 0, 0);
        }

        const start = toLocalISO(dropDate);
        const end = toLocalISO(addBusinessHours(dropDate, op.hours));

        const result = await fetchJSON('/api/blocks', {
            method: 'POST',
            body: {
                operation_id: op.id,
                machine_id: machine.id,
                start_time: start,
                end_time: end,
            },
        });
        pushUndo({
            type: 'create',
            description: `WO${op.wo} Op${op.op} → ${machine.name}`,
            blockId: result.id,
        });
        refreshEvents();
        loadBacklog();
    }

    // Helper: append op to end of machine queue (sidebar drop)
    async function scheduleAppend(op, machine) {
        // Get existing blocks on this machine to find the last one
        let startDate;
        try {
            const blocks = await fetchJSON(`/api/blocks?machine=${machine.id}`);
            if (blocks.length > 0) {
                blocks.sort((a, b) => new Date(a.end) - new Date(b.end));
                startDate = new Date(blocks[blocks.length - 1].end);
            }
        } catch (_) {}

        if (!startDate) {
            startDate = dateFromFallback();
        }

        // Snap to business hours
        if (startDate.getHours() < BH_START) {
            startDate.setHours(BH_START, 0, 0, 0);
        } else if (startDate.getHours() >= BH_END) {
            startDate.setDate(startDate.getDate() + 1);
            startDate.setHours(BH_START, 0, 0, 0);
        }
        while (startDate.getDay() === 0 || startDate.getDay() === 6) {
            startDate.setDate(startDate.getDate() + 1);
            startDate.setHours(BH_START, 0, 0, 0);
        }

        const start = toLocalISO(startDate);
        const end = toLocalISO(addBusinessHours(startDate, op.hours));

        const result = await fetchJSON('/api/blocks', {
            method: 'POST',
            body: {
                operation_id: op.id,
                machine_id: machine.id,
                start_time: start,
                end_time: end,
            },
        });
        pushUndo({
            type: 'create',
            description: `WO${op.wo} Op${op.op} → ${machine.name} (appended)`,
            blockId: result.id,
        });
        refreshEvents();
        loadBacklog();
        // Refresh machine panel if it's open for this machine
        if (machineOpsActive === machine.id) {
            setTimeout(() => showMachineOps(machine.id, machine.name), 400);
        }
    }

    // Create TWO drop zones per machine: sidebar + timeline
    machines.forEach((m, i) => {
        const rr = rowEls[i] ? rowEls[i].getBoundingClientRect() : null;
        const rowTop = rr ? rr.top : calRect.top + i * 40;
        const rowHeight = rr ? Math.max(rr.height, 30) : 40;

        // ── Sidebar zone (drop = append to end of queue) ──
        const sideZone = document.createElement('div');
        sideZone.className = 'drop-zone-sidebar';
        sideZone.dataset.machineId = m.id;
        sideZone.style.cssText = `
            position: absolute;
            left: ${calRect.left}px;
            top: ${rowTop}px;
            width: ${sidebarRight - calRect.left}px;
            height: ${rowHeight}px;
        `;

        sideZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            sideZone.classList.add('drag-hover');
            sideZone.textContent = '+ Add to end';
        });
        sideZone.addEventListener('dragleave', () => {
            sideZone.classList.remove('drag-hover');
            sideZone.textContent = '';
        });
        sideZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const op = extractOp(e);
            hideDropOverlay();
            if (!op) { showToast('Drop failed — lost operation data. Try again.'); return; }
            try {
                await scheduleAppend(op, m);
            } catch (err) {
                console.error('Failed to schedule (sidebar):', err);
                const msg = err.message || 'Failed to schedule';
                showToast(msg.includes('verlap') ? 'Overlap: ' + msg : 'Schedule failed: ' + msg, 6000);
            }
        });
        overlay.appendChild(sideZone);

        // ── Timeline zone (drop = at cursor X position, existing behavior) ──
        const timeZone = document.createElement('div');
        timeZone.dataset.machineId = m.id;
        timeZone.dataset.machineName = m.name;
        timeZone.style.cssText = `
            position: absolute;
            left: ${sidebarRight}px;
            top: ${rowTop}px;
            width: ${calRect.right - sidebarRight}px;
            height: ${rowHeight}px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px dashed transparent;
            border-radius: 4px;
            transition: all 0.15s;
            font-size: 13px;
            color: transparent;
            background: transparent;
        `;

        timeZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            timeZone.style.borderColor = 'var(--accent-blue)';
            timeZone.style.background = 'rgba(59,130,246,0.1)';
            timeZone.style.color = 'var(--accent-blue)';
            timeZone.textContent = m.name;
        });
        timeZone.addEventListener('dragleave', () => {
            timeZone.style.borderColor = 'transparent';
            timeZone.style.background = 'transparent';
            timeZone.style.color = 'transparent';
            timeZone.textContent = '';
        });
        timeZone.addEventListener('drop', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const op = extractOp(e);
            let dropDate = dateFromCursorX(e.clientX) || dateFromFallback();
            hideDropOverlay();
            if (!op) { showToast('Drop failed — lost operation data. Try again.'); return; }
            if (!dropDate || !(dropDate instanceof Date) || isNaN(dropDate)) {
                showToast('Could not determine drop time — try a different spot');
                return;
            }
            try {
                await scheduleAtTime(op, m, dropDate);
            } catch (err) {
                console.error('Failed to schedule:', err);
                const msg = err.message || 'Failed to schedule';
                showToast(msg.includes('verlap') ? 'Overlap: ' + msg : 'Schedule failed: ' + msg, 6000);
            }
        });
        overlay.appendChild(timeZone);
    });

    // Catch-all: if the drop misses all machine zones (alignment issue),
    // show feedback instead of silently doing nothing
    overlay.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    });
    overlay.addEventListener('drop', (e) => {
        // Only fires if no zone's drop handler stopped propagation
        e.preventDefault();
        hideDropOverlay();
        showToast('Drop missed the machine row — try again or use the suggestion chip');
    });

    document.body.appendChild(overlay);
}

function hideDropOverlay() {
    const existing = document.getElementById('drop-overlay');
    if (existing) existing.remove();
}

function psWoUrl(woNumber) {
    const base = window.PROSHOP_BASE || '';
    const yy = woNumber.split('-')[0];
    return `${base}/procnc/workorders/20${yy}/${woNumber}$`;
}

// ── Block Details Side Panel ─────────────────────────────────────────────────

function showBlockDetails(event) {
    const props = event.extendedProps || {};
    const r = props.readiness || {};
    const panel = document.getElementById('side-panel');
    const body = document.getElementById('panel-body');

    const woUrl = psWoUrl(props.wo_number);
    document.getElementById('panel-title').innerHTML =
        `<span id="panel-drawing" class="panel-drawing" style="display:inline-block;vertical-align:middle;margin-right:10px"></span><a href="${woUrl}" target="_blank" style="color:var(--accent-blue);text-decoration:none">WO${props.wo_number}</a> Op${props.op_number}`;

    const dueText = formatDueDate(props.due_date);
    const dueClass = getDueClass(props.due_date);
    const progress = props.progress || 0;
    const hours = props.override_hours || props.est_hours || 1;

    const fmtHours = typeof hours === 'number' ? hours.toFixed(1) : hours;
    const statusBadge = props.status === 'running' ? 'green' : props.status === 'complete' ? 'blue' : 'yellow';

    body.innerHTML = `
        <div class="panel-compact">
            <div class="panel-info">
                <span><strong>${props.part_number || ''}</strong> ${props.part_name || ''}</span>
                <span class="text-muted">${props.customer || ''}</span>
                <span class="text-muted">${props.op_name || ''} · ${props.machine_name || ''}</span>
                <span>${fmtHours}h ${props.is_estimated ? '<span class="badge badge-yellow">EST</span>' : ''} · <span class="due-countdown ${dueClass}">${dueText}</span> · ${props.qty_complete || 0}/${props.qty_required || '?'} · <span class="badge badge-${statusBadge}">${props.status}</span></span>
                <div class="readiness-lights-lg" style="margin-top:2px">
                    <span class="light-item"><span class="light ${r.program_ready ? 'green' : 'red'}"></span>Prog</span>
                    <span class="light-item"><span class="light ${r.material_ready ? 'green' : 'red'}"></span>Mat</span>
                    <span class="light-item"><span class="light ${r.tools_ready ? 'green' : 'yellow'}"></span>Tools</span>
                    <span class="light-item"><span class="light ${r.machine_ready ? 'green' : 'gray'}"></span>Machine</span>
                </div>
            </div>
            <div class="panel-actions">
                <a href="${woUrl}" target="_blank" class="btn btn-primary" style="text-decoration:none">ProShop</a>
                <button class="btn-tools-toggle ${r.tools_ready ? 'staged' : ''}"
                        onclick="toggleToolsReady('${props.wo_number}-${props.op_number}')">
                    ${r.tools_ready ? 'Tools Staged' : 'Mark Tools Staged'}
                </button>
                <button class="btn ${props.is_locked ? 'btn-danger' : ''}" onclick="toggleLock(${props.block_id}, ${props.is_locked})">
                    ${props.is_locked ? 'Unlock' : 'Lock'}
                </button>
                <button class="btn btn-danger" onclick="deleteBlock(${props.block_id})">Remove</button>
            </div>
        </div>
    `;

    panel.classList.add('open');

    // Fetch part drawing async — show as thumbnail in header
    fetchJSON('/api/workorders/' + props.wo_number + '/drawing')
        .then(data => {
            const el = document.getElementById('panel-drawing');
            if (!el || !data.url) return;
            if (data.type === 'pdf') {
                el.innerHTML = '<iframe src="' + data.url + '#toolbar=0&navpanes=0" class="drawing-frame-thumb" title="' + (data.title || 'Drawing') + '"></iframe>';
            } else {
                el.innerHTML = '<img src="' + data.url + '" class="drawing-thumb" alt="' + (data.title || 'Part image') + '" onclick="openDrawingLightbox(\'' + data.url + '\', \'' + data.type + '\')">';
            }
        })
        .catch(() => {});
}

function closePanel() {
    document.getElementById('side-panel').classList.remove('open');
}

function closeMachinePanel() {
    document.getElementById('machine-panel').classList.remove('open');
    machineOpsActive = null;
}

function openDrawingLightbox(url, type) {
    const lb = document.createElement('div');
    lb.className = 'drawing-lightbox';
    lb.onclick = () => lb.remove();
    if (type === 'pdf') {
        lb.innerHTML = '<iframe src="' + url + '" style="width:85vw;height:85vh;border:none;border-radius:8px"></iframe>';
    } else {
        lb.innerHTML = '<img src="' + url + '">';
    }
    document.body.appendChild(lb);
}

async function toggleLock(blockId, isLocked) {
    await fetchJSON(`/api/blocks/${blockId}`, {
        method: 'PUT',
        body: { is_locked: isLocked ? 0 : 1, force: true },
    });
    refreshEvents();
    closePanel();
}

async function deleteBlock(blockId) {
    if (!confirm('Remove this block from the schedule?')) return;

    // Find the block in allEvents to capture state for undo
    const evt = allEvents.find(e => e.extendedProps?.block_id === blockId);
    const props = evt?.extendedProps || {};

    await fetchJSON(`/api/blocks/${blockId}`, { method: 'DELETE' });

    if (evt) {
        pushUndo({
            type: 'delete',
            description: `${evt.title} removed`,
            recreate: {
                operation_id: props.operation_id,
                machine_id: props.machine_id,
                start_time: evt.start,
                end_time: evt.end,
            },
        });
    }

    refreshEvents();
    loadBacklog();
    closePanel();
}

// ── Controls ─────────────────────────────────────────────────────────────────

function initControls() {
    // Zoom buttons
    document.querySelectorAll('.zoom-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setZoom(btn.dataset.zoom);
        });
    });

    // Today button
    document.getElementById('btn-today').addEventListener('click', () => {
        if (ec) ec.setOption('date', new Date());
    });

    // Sync button
    document.getElementById('btn-sync').addEventListener('click', async () => {
        const dot = document.getElementById('sync-dot');
        const text = document.getElementById('sync-text');
        dot.classList.add('syncing');
        text.textContent = 'Syncing...';

        try {
            const result = await fetchJSON('/api/sync', { method: 'POST' });
            text.textContent = `Synced ${result.wo_count} WOs, ${result.op_count} ops`;
            refreshEvents();
            loadBacklog();
        } catch (e) {
            text.textContent = 'Sync failed';
        }

        dot.classList.remove('syncing');
        setTimeout(() => { text.textContent = 'Ready'; }, 5000);
    });

    // Backlog toggle
    document.getElementById('backlog-toggle').addEventListener('click', () => {
        const panel = document.getElementById('backlog-panel');
        const arrow = document.getElementById('backlog-arrow');
        panel.classList.toggle('collapsed');
        arrow.textContent = panel.classList.contains('collapsed') ? '\u25B6' : '\u25BC';
    });

    // Backlog search
    document.getElementById('backlog-search').addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase();
        const filtered = backlogOps.filter(op =>
            (op.wo_number || '').toLowerCase().includes(q) ||
            (op.part_name || '').toLowerCase().includes(q) ||
            (op.part_number || '').toLowerCase().includes(q) ||
            (op.customer || '').toLowerCase().includes(q) ||
            (op.op_name || '').toLowerCase().includes(q)
        );
        renderBacklog(filtered);
    });

    // Clear Board button
    const clearBtn2 = document.getElementById('btn-clear-board');
    if (clearBtn2) {
        clearBtn2.addEventListener('click', clearBoard);
    }

    // Auto-Schedule button
    const autoBtn = document.getElementById('btn-auto-schedule');
    if (autoBtn) {
        autoBtn.addEventListener('click', autoScheduleAll);
    }

    // Hidden Items button
    const hiddenBtn = document.getElementById('btn-hidden-wos');
    if (hiddenBtn) {
        hiddenBtn.addEventListener('click', toggleHiddenDropdown);
    }
    loadHiddenCount();

    // Close context menu and hidden dropdown on outside click
    document.addEventListener('click', (e) => {
        const ctx = document.getElementById('backlog-context-menu');
        if (ctx && !ctx.contains(e.target)) ctx.remove();
        const dd = document.getElementById('hidden-wos-dropdown');
        const btn = document.getElementById('btn-hidden-wos');
        if (dd && dd.classList.contains('open') && !dd.contains(e.target) && e.target !== btn) {
            dd.classList.remove('open');
        }
    });

    // Undo button
    const undoBtn = document.getElementById('btn-undo');
    if (undoBtn) {
        undoBtn.addEventListener('click', performUndo);
    }
    updateUndoButton();

    // Side panel close (bottom)
    document.getElementById('panel-close').addEventListener('click', closePanel);
    // Machine panel close (right side)
    document.getElementById('machine-panel-close').addEventListener('click', closeMachinePanel);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            // Close whichever panel is open (machine panel takes priority)
            const mp = document.getElementById('machine-panel');
            if (mp && mp.classList.contains('open')) {
                closeMachinePanel();
            } else {
                closePanel();
            }
        }
        // Ctrl+Z / Cmd+Z for undo
        if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
            e.preventDefault();
            performUndo();
        }
    });

    // Resize handle — drag to resize calendar vs backlog
    initResizeHandle();
}

async function clearBoard() {
    if (!confirm('Remove all unlocked blocks from the board?')) return;
    const btn = document.getElementById('btn-clear-board');
    btn.disabled = true;
    btn.textContent = 'Clearing...';
    try {
        const result = await fetchJSON('/api/blocks/clear', { method: 'POST' });
        btn.textContent = `Cleared ${result.deleted} blocks`;
        refreshEvents();
        loadBacklog();
    } catch (e) {
        btn.textContent = 'Failed';
        showToast(e.message || 'Failed to clear board');
    }
    btn.disabled = false;
    setTimeout(() => { btn.textContent = 'Clear Board'; }, 3000);
}

async function autoScheduleAll() {
    const btn = document.getElementById('btn-auto-schedule');
    const suggestions = Object.values(suggestionsMap);
    if (suggestions.length === 0) {
        btn.textContent = 'Nothing to schedule';
        setTimeout(() => { btn.textContent = 'Auto-Schedule'; }, 2000);
        return;
    }

    btn.disabled = true;
    let scheduled = 0;
    let failed = 0;
    const createdIds = [];

    for (const sug of suggestions) {
        btn.textContent = `Scheduling ${scheduled + 1}/${suggestions.length}...`;
        try {
            const res = await fetchJSON('/api/blocks', {
                method: 'POST',
                body: {
                    operation_id: sug.op_id,
                    machine_id: sug.machine_id,
                    start_time: sug.start_time,
                    end_time: sug.end_time,
                    created_by: 'auto-suggest',
                },
            });
            createdIds.push(res.id);
            scheduled++;
        } catch (err) {
            console.error('Failed to auto-schedule:', sug.op_id, err);
            failed++;
        }
    }

    if (createdIds.length > 0) {
        pushUndo({
            type: 'batch-create',
            description: `auto-scheduled ${createdIds.length} ops`,
            blockIds: createdIds,
        });
    }

    btn.textContent = `Done! ${scheduled} scheduled` + (failed ? `, ${failed} failed` : '');
    btn.disabled = false;
    refreshEvents();
    loadBacklog();
    setTimeout(() => { btn.textContent = 'Auto-Schedule'; }, 3000);
}

// ── Resize Handle ────────────────────────────────────────────────────────────

function initResizeHandle() {
    const handle = document.getElementById('resize-handle');
    const container = document.querySelector('.scheduler-container');
    const backlog = document.getElementById('backlog-panel');
    let dragging = false;
    let startY = 0;
    let startHeight = 0;

    // Restore saved height
    const saved = localStorage.getItem('backlog_height');
    if (saved) {
        backlog.style.height = saved + 'px';
    } else {
        backlog.style.height = '250px';
    }

    handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        dragging = true;
        startY = e.clientY;
        startHeight = backlog.offsetHeight;
        handle.classList.add('dragging');
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const delta = startY - e.clientY;
        const newHeight = Math.max(36, Math.min(window.innerHeight - 200, startHeight + delta));
        backlog.style.height = newHeight + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        handle.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        localStorage.setItem('backlog_height', backlog.offsetHeight);
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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

function getDueClass(dueDateStr) {
    if (!dueDateStr) return 'normal';
    const due = new Date(dueDateStr);
    const now = new Date();
    const days = (due - now) / 86400000;
    if (days < 0) return 'past-due';
    if (days < 3) return 'urgent';
    if (days < 7) return 'soon';
    return 'normal';
}

function formatDueDate(dueDateStr) {
    if (!dueDateStr) return 'No due date';
    const due = new Date(dueDateStr);
    const now = new Date();
    const days = Math.ceil((due - now) / 86400000);
    if (days < -1) return `${Math.abs(days)} days past due`;
    if (days === -1) return 'Due yesterday';
    if (days === 0) return 'Due today';
    if (days === 1) return 'Due tomorrow';
    if (days < 7) return `Due in ${days} days`;
    return `Due ${due.toLocaleDateString()}`;
}

// ── Readiness Lights ─────────────────────────────────────────────────────────

function renderReadinessLights(r) {
    const progColor = r.program_ready ? 'green' : 'red';
    const matColor = r.material_ready ? 'green' : 'red';
    const toolColor = r.tools_ready ? 'green' : 'yellow';
    const machColor = r.machine_ready ? 'green' : 'gray';
    return `<span class="readiness-lights" title="Prog | Mat | Tools | Machine">` +
        `<span class="light ${progColor}" title="Program: ${r.program_ready ? 'Ready' : 'Not ready'}"></span>` +
        `<span class="light ${matColor}" title="Material: ${r.material_ready ? 'Ready' : 'Not ready'}"></span>` +
        `<span class="light ${toolColor}" title="Tools: ${r.tools_ready ? 'Staged' : 'Not staged'}"></span>` +
        `<span class="light ${machColor}" title="Machine: ${r.machine_ready ? 'Slot found' : 'No slot'}"></span>` +
        `</span>`;
}

async function toggleToolsReady(opId) {
    try {
        const result = await fetchJSON(`/api/operations/${opId}/tools-ready`, { method: 'POST' });
        showToast(result.tools_ready ? 'Tools marked as staged' : 'Tools unmarked');
        refreshEvents();
        loadBacklog();
        // Update button in panel without closing it
        const btn = document.querySelector('.btn-tools-toggle');
        if (btn) {
            btn.classList.toggle('staged', !!result.tools_ready);
            btn.textContent = result.tools_ready ? 'Tools Staged' : 'Mark Tools Staged';
        }
    } catch (e) {
        console.error('Failed to toggle tools ready:', e);
        showToast(e.message || 'Failed to toggle tools ready');
    }
}

// ── Toast Notifications ──────────────────────────────────────────────────────

function showToast(message, duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    container.appendChild(toast);
    // Trigger animation
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ── Machine Ops Panel ────────────────────────────────────────────────────────

let machineOpsActive = null; // Currently displayed machine id

function initMachineOpsClick() {
    // Use a MutationObserver to attach click handlers when resources render
    const calEl = document.getElementById('gantt-calendar');
    if (!calEl) return;

    const attachClicks = () => {
        calEl.querySelectorAll('.ec-resource').forEach(el => {
            if (el._machOpsClick) return; // already attached
            el._machOpsClick = true;
            el.style.cursor = 'pointer';
            el.addEventListener('click', (e) => {
                // Find the machine index from resource element position
                const allRes = Array.from(calEl.querySelectorAll('.ec-resource'));
                const idx = allRes.indexOf(el);
                if (idx >= 0 && idx < machines.length) {
                    showMachineOps(machines[idx].id, machines[idx].name);
                }
            });
        });
    };

    // Attach now and re-attach after calendar re-renders
    attachClicks();
    const observer = new MutationObserver(() => attachClicks());
    observer.observe(calEl, { childList: true, subtree: true });
}

async function showMachineOps(machineId, machineName) {
    machineOpsActive = machineId;
    const panel = document.getElementById('machine-panel');
    const body = document.getElementById('machine-panel-body');
    document.getElementById('machine-panel-title').textContent = machineName + ' — Ops Queue';

    body.innerHTML = '<div style="padding:12px;color:var(--text-subtle)">Loading...</div>';
    panel.classList.add('open');

    try {
        const blocks = await fetchJSON(`/api/blocks?machine=${machineId}`);
        // Sort by start_time
        blocks.sort((a, b) => new Date(a.start) - new Date(b.start));

        if (blocks.length === 0) {
            body.innerHTML = '<div style="padding:12px;color:var(--text-subtle)">No ops on this machine</div>';
            return;
        }

        body.innerHTML = `<div class="machine-panel-ops" id="machine-ops-list" data-machine-id="${machineId}">
            ${blocks.map((b, i) => {
                const p = b.extendedProps || {};
                const hours = p.override_hours || p.est_hours || 1;
                const fmtH = typeof hours === 'number' ? hours.toFixed(1) : hours;
                const startD = new Date(b.start);
                const endD = new Date(b.end);
                const timeFmt = (d) => d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
                    + ' ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
                const statusBadge = p.status === 'running' ? 'green' : p.status === 'complete' ? 'blue' : 'yellow';
                return `<div class="machine-panel-op" draggable="true" data-block-id="${p.block_id}" data-index="${i}" data-wo="${p.wo_number}">
                    <span class="machine-ops-handle">&#9776;</span>
                    <div class="mp-op-drawing" data-wo="${p.wo_number}"></div>
                    <div class="machine-ops-info">
                        <strong>WO${p.wo_number} Op${p.op_number}</strong>
                        <span class="text-muted">${p.part_name || p.op_name || ''} · ${fmtH}h</span>
                        <span class="op-time">${timeFmt(startD)} — ${timeFmt(endD)}</span>
                        <span class="text-muted"><span class="badge badge-${statusBadge}">${p.status || 'scheduled'}</span></span>
                    </div>
                </div>`;
            }).join('')}
        </div>`;

        initMachineOpsDragReorder();
        loadMachinePanelDrawings(blocks);
    } catch (e) {
        body.innerHTML = `<div style="padding:12px;color:var(--accent-red)">Failed to load: ${e.message}</div>`;
    }
}

/** Fetch part drawings per unique WO and inject thumbnails into the machine ops panel. */
async function loadMachinePanelDrawings(blocks) {
    // Collect unique WO numbers
    const woSet = new Set();
    for (const b of blocks) {
        const wo = (b.extendedProps || {}).wo_number;
        if (wo) woSet.add(wo);
    }
    // Fetch each WO's drawing (in parallel)
    const drawingMap = {};
    await Promise.all([...woSet].map(async (wo) => {
        try {
            const data = await fetchJSON(`/api/workorders/${wo}/drawing`);
            if (data && data.url) drawingMap[wo] = data;
        } catch (_) {}
    }));
    // Inject thumbnails into placeholder divs
    document.querySelectorAll('.mp-op-drawing').forEach(el => {
        const wo = el.dataset.wo;
        const d = drawingMap[wo];
        if (d && d.url) {
            if (d.type === 'pdf') {
                el.innerHTML = `<iframe src="${d.url}#toolbar=0&navpanes=0" class="mp-drawing-thumb" title="${d.title || 'Drawing'}"></iframe>`;
            } else {
                el.innerHTML = `<img src="${d.url}" class="mp-drawing-thumb" alt="${d.title || 'Part'}" onclick="event.stopPropagation();openDrawingLightbox('${d.url}','${d.type}')">`;
            }
        } else {
            el.style.display = 'none';
        }
    });
}

function initMachineOpsDragReorder() {
    const list = document.getElementById('machine-ops-list');
    if (!list) return;

    let dragItem = null;
    let dragOverItem = null;
    const itemSel = '.machine-panel-op';

    list.querySelectorAll(itemSel).forEach(item => {
        item.addEventListener('dragstart', (e) => {
            dragItem = item;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', item.dataset.blockId);
        });
        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            list.querySelectorAll(itemSel).forEach(el => el.classList.remove('drag-over'));
            if (dragItem && dragOverItem && dragItem !== dragOverItem) {
                reorderMachineOps();
            }
            dragItem = null;
            dragOverItem = null;
        });
        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (item !== dragItem) {
                list.querySelectorAll(itemSel).forEach(el => el.classList.remove('drag-over'));
                item.classList.add('drag-over');
                dragOverItem = item;
                // Reorder DOM in real-time for visual feedback
                const items = Array.from(list.querySelectorAll(itemSel));
                const dragIdx = items.indexOf(dragItem);
                const overIdx = items.indexOf(item);
                if (dragIdx < overIdx) {
                    list.insertBefore(dragItem, item.nextSibling);
                } else {
                    list.insertBefore(dragItem, item);
                }
            }
        });
        item.addEventListener('drop', (e) => {
            e.preventDefault();
        });
        // Click row to show block details in bottom panel
        item.addEventListener('click', (e) => {
            if (e.target.closest('.machine-ops-handle')) return; // ignore handle clicks
            const blockId = parseInt(item.dataset.blockId);
            const evt = allEvents.find(ev => ev.extendedProps?.block_id === blockId);
            if (evt) showBlockDetails(evt);
        });
    });
}

async function reorderMachineOps() {
    const list = document.getElementById('machine-ops-list');
    if (!list) return;
    const machineId = list.dataset.machineId;

    const items = Array.from(list.querySelectorAll('.machine-panel-op'));
    const blockIds = items.map(el => parseInt(el.dataset.blockId));

    // Get the blocks data from allEvents
    const blocks = blockIds.map(id => allEvents.find(e => e.extendedProps?.block_id === id)).filter(Boolean);
    if (blocks.length === 0) return;

    // Find earliest start among all blocks
    let anchor = new Date(Math.min(...blocks.map(b => new Date(b.start).getTime())));

    // Calculate new times for each block in the new order, chaining them
    const updates = [];
    for (const b of blocks) {
        const p = b.extendedProps || {};
        const hours = p.override_hours || p.est_hours || ((new Date(b.end) - new Date(b.start)) / 3600000);
        const newStart = new Date(anchor);
        const newEnd = addBusinessHours(newStart, hours);
        updates.push({
            blockId: p.block_id,
            start_time: toLocalISO(newStart),
            end_time: toLocalISO(newEnd),
        });
        anchor = newEnd; // next op starts where this one ends
    }

    // Send batch updates
    try {
        for (const u of updates) {
            await fetchJSON(`/api/blocks/${u.blockId}`, {
                method: 'PUT',
                body: { start_time: u.start_time, end_time: u.end_time },
            });
        }
        showToast('Ops reordered', 2000);
        refreshEvents();
        // Refresh the panel after events update
        const machine = machines.find(m => m.id == machineId);
        if (machine) {
            setTimeout(() => showMachineOps(machine.id, machine.name), 500);
        }
    } catch (e) {
        showToast('Reorder failed: ' + (e.message || 'Unknown error'));
        refreshEvents();
    }
}

// ── Board Filters ────────────────────────────────────────────────────────────

const FILTER_STORAGE_KEY = 'scheduler_board_filters';

function getFilterState() {
    return {
        search: document.getElementById('filter-search')?.value || '',
        customer: document.getElementById('filter-customer')?.value || '',
        materialType: document.getElementById('filter-material-type')?.value || '',
        scheduled: document.getElementById('filter-scheduled')?.checked ?? true,
        running: document.getElementById('filter-running')?.checked ?? true,
        complete: document.getElementById('filter-complete')?.checked ?? false,
        pastdue: document.getElementById('filter-pastdue')?.checked ?? true,
        urgent: document.getElementById('filter-urgent')?.checked ?? true,
        normal: document.getElementById('filter-normal')?.checked ?? true,
        nodate: document.getElementById('filter-nodate')?.checked ?? true,
        needsProgram: document.getElementById('filter-needs-program')?.checked ?? false,
        needsMaterial: document.getElementById('filter-needs-material')?.checked ?? false,
        needsTools: document.getElementById('filter-needs-tools')?.checked ?? false,
    };
}

function saveFilterState() {
    try {
        localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(getFilterState()));
    } catch (e) { /* ignore */ }
}

function loadFilterState() {
    try {
        const saved = localStorage.getItem(FILTER_STORAGE_KEY);
        if (!saved) return;
        const state = JSON.parse(saved);
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = val; };
        setVal('filter-search', state.search || '');
        setVal('filter-customer', state.customer || '');
        setVal('filter-material-type', state.materialType || '');
        setChk('filter-scheduled', state.scheduled ?? true);
        setChk('filter-running', state.running ?? true);
        setChk('filter-complete', state.complete ?? false);
        setChk('filter-pastdue', state.pastdue ?? true);
        setChk('filter-urgent', state.urgent ?? true);
        setChk('filter-normal', state.normal ?? true);
        setChk('filter-nodate', state.nodate ?? true);
        setChk('filter-needs-program', state.needsProgram ?? false);
        setChk('filter-needs-material', state.needsMaterial ?? false);
        setChk('filter-needs-tools', state.needsTools ?? false);
    } catch (e) { /* ignore */ }
}

function populateCustomerFilter(events) {
    const select = document.getElementById('filter-customer');
    if (!select) return;
    const current = select.value;
    const customers = [...new Set(
        events.map(e => e.extendedProps?.customer).filter(Boolean)
    )].sort();
    // Keep "All Customers" option, rebuild rest
    select.innerHTML = '<option value="">All Customers</option>';
    customers.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        select.appendChild(opt);
    });
    // Restore selection if still valid
    if (current && customers.includes(current)) {
        select.value = current;
    }
}

function populateMaterialTypeFilter(events) {
    const select = document.getElementById('filter-material-type');
    if (!select) return;
    const current = select.value;
    const materials = [...new Set(
        events.map(e => e.extendedProps?.material_type).filter(Boolean)
    )].sort();
    select.innerHTML = '<option value="">All Materials</option>';
    materials.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        select.appendChild(opt);
    });
    if (current && materials.includes(current)) {
        select.value = current;
    }
}

function getUrgencyCategory(dueDateStr) {
    if (!dueDateStr) return 'nodate';
    const due = new Date(dueDateStr);
    const now = new Date();
    const days = (due - now) / 86400000;
    if (days < 0) return 'pastdue';
    if (days < 3) return 'urgent';
    return 'normal';
}

function applyFilters() {
    if (!ec) return;
    const f = getFilterState();

    const isDefault = !f.search && !f.customer && !f.materialType && f.scheduled && f.running && !f.complete
        && f.pastdue && f.urgent && f.normal && f.nodate && !f.needsProgram && !f.needsMaterial && !f.needsTools;

    const filtered = allEvents.filter(evt => {
        const p = evt.extendedProps || {};

        // Status filter
        const status = p.status || 'scheduled';
        if (status === 'scheduled' && !f.scheduled) return false;
        if (status === 'running' && !f.running) return false;
        if (status === 'complete' && !f.complete) return false;

        // Text search
        if (f.search) {
            const q = f.search.toLowerCase();
            const haystack = [
                p.wo_number, p.part_name, p.part_number,
                p.op_name, p.customer, evt.title
            ].filter(Boolean).join(' ').toLowerCase();
            if (!haystack.includes(q)) return false;
        }

        // Customer filter
        if (f.customer && (p.customer || '') !== f.customer) return false;

        // Material type filter
        if (f.materialType && (p.material_type || '') !== f.materialType) return false;

        // Urgency filter
        const urgency = getUrgencyCategory(p.due_date);
        if (urgency === 'pastdue' && !f.pastdue) return false;
        if (urgency === 'urgent' && !f.urgent) return false;
        if (urgency === 'normal' && !f.normal) return false;
        if (urgency === 'nodate' && !f.nodate) return false;

        // Needs filters — show only ops that need these items
        const r = p.readiness || {};
        if (f.needsProgram && r.program_ready) return false;
        if (f.needsMaterial && r.material_ready) return false;
        if (f.needsTools && r.tools_ready) return false;

        return true;
    });

    ec.setOption('events', filtered);

    // Update active filter count badge
    const countEl = document.getElementById('filter-active-count');
    if (countEl) {
        const activeCount = allEvents.length - filtered.length;
        if (!isDefault && activeCount > 0) {
            countEl.textContent = activeCount + ' hidden';
            countEl.style.display = '';
        } else {
            countEl.style.display = 'none';
        }
    }

    // Also filter backlog by needs checkboxes
    if (f.needsProgram || f.needsMaterial || f.needsTools) {
        const filteredBacklog = backlogOps.filter(op => {
            const r = op.readiness || {};
            if (f.needsProgram && r.program_ready) return false;
            if (f.needsMaterial && r.material_ready) return false;
            if (f.needsTools && r.tools_ready) return false;
            return true;
        });
        renderBacklog(filteredBacklog);
    }

    saveFilterState();
}

function clearFilters() {
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = val; };
    setVal('filter-search', '');
    setVal('filter-customer', '');
    setVal('filter-material-type', '');
    setChk('filter-scheduled', true);
    setChk('filter-running', true);
    setChk('filter-complete', false);
    setChk('filter-pastdue', true);
    setChk('filter-urgent', true);
    setChk('filter-normal', true);
    setChk('filter-nodate', true);
    setChk('filter-needs-program', false);
    setChk('filter-needs-material', false);
    setChk('filter-needs-tools', false);
    applyFilters();
}

// ── Context Menu (Hide WO / Op) ─────────────────────────────────────────────

function showBacklogContextMenu(x, y, woNumber, opId) {
    // Remove any existing menu
    const old = document.getElementById('backlog-context-menu');
    if (old) old.remove();

    const menu = document.createElement('div');
    menu.id = 'backlog-context-menu';
    menu.className = 'context-menu';
    menu.innerHTML = `
        <div class="context-menu-item" data-action="hide-wo">Hide WO ${woNumber} from Scheduler</div>
        <div class="context-menu-item" data-action="hide-op">Hide This Op (${opId})</div>
    `;
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    document.body.appendChild(menu);

    menu.querySelector('[data-action="hide-wo"]').addEventListener('click', async () => {
        menu.remove();
        if (!confirm(`Hide WO ${woNumber} and all its ops from the scheduler?\n\nAny scheduled (non-locked) blocks for this WO will be removed.`)) return;
        try {
            const result = await fetchJSON(`/api/workorders/${woNumber}/hide`, { method: 'POST' });
            if (result.removed_blocks > 0) {
                showToast(`WO ${woNumber} hidden — ${result.removed_blocks} block(s) removed`);
                refreshEvents();
            } else {
                showToast(`WO ${woNumber} hidden`);
            }
            loadBacklog();
            loadHiddenCount();
        } catch (e) {
            showToast(e.message || 'Failed to hide WO');
        }
    });

    menu.querySelector('[data-action="hide-op"]').addEventListener('click', async () => {
        menu.remove();
        if (!confirm(`Hide operation ${opId} from the scheduler?\n\nAny scheduled (non-locked) block for this op will be removed.`)) return;
        try {
            const result = await fetchJSON(`/api/operations/${opId}/hide`, { method: 'POST' });
            if (result.removed_blocks > 0) {
                showToast(`Op ${opId} hidden — ${result.removed_blocks} block(s) removed`);
                refreshEvents();
            } else {
                showToast(`Op ${opId} hidden`);
            }
            loadBacklog();
            loadHiddenCount();
        } catch (e) {
            showToast(e.message || 'Failed to hide op');
        }
    });
}

// ── Hidden Items Dropdown ───────────────────────────────────────────────────

async function loadHiddenCount() {
    try {
        const [wos, ops] = await Promise.all([
            fetchJSON('/api/workorders/hidden'),
            fetchJSON('/api/operations/hidden'),
        ]);
        const total = wos.length + ops.length;
        const badge = document.getElementById('hidden-wo-count');
        if (badge) {
            if (total > 0) {
                badge.textContent = total;
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (e) {
        console.error('Failed to load hidden count:', e);
    }
}

async function toggleHiddenDropdown() {
    const dd = document.getElementById('hidden-wos-dropdown');
    if (!dd) return;
    if (dd.classList.contains('open')) {
        dd.classList.remove('open');
        return;
    }
    dd.innerHTML = '<div style="padding:12px;color:var(--text-subtle)">Loading...</div>';
    dd.classList.add('open');
    try {
        const [wos, ops] = await Promise.all([
            fetchJSON('/api/workorders/hidden'),
            fetchJSON('/api/operations/hidden'),
        ]);
        if (wos.length === 0 && ops.length === 0) {
            dd.innerHTML = '<div style="padding:12px;color:var(--text-subtle);font-size:12px">No hidden items</div>';
            return;
        }
        let html = '';
        if (wos.length > 0) {
            html += '<div class="hidden-section-title">Work Orders</div>';
            html += wos.map(wo => `
                <div class="hidden-wo-row">
                    <div>
                        <strong>WO${wo.wo_number}</strong>
                        <span style="color:var(--text-muted);font-size:11px;margin-left:4px">${wo.part_name || wo.part_number || ''}</span>
                    </div>
                    <button class="btn" style="font-size:11px;padding:2px 8px" onclick="unhideWo('${wo.wo_number}')">Unhide</button>
                </div>
            `).join('');
        }
        if (ops.length > 0) {
            html += '<div class="hidden-section-title">Individual Ops</div>';
            html += ops.map(op => `
                <div class="hidden-wo-row">
                    <div>
                        <strong>WO${op.wo_number} Op${op.op_number}</strong>
                        <span style="color:var(--text-muted);font-size:11px;margin-left:4px">${op.part_name || op.op_name || ''}</span>
                    </div>
                    <button class="btn" style="font-size:11px;padding:2px 8px" onclick="unhideOp('${op.id}')">Unhide</button>
                </div>
            `).join('');
        }
        dd.innerHTML = html;
    } catch (e) {
        dd.innerHTML = '<div style="padding:12px;color:var(--accent-red)">Failed to load</div>';
    }
}

async function unhideWo(woNumber) {
    try {
        await fetchJSON(`/api/workorders/${woNumber}/hide`, { method: 'POST' });
        showToast(`WO ${woNumber} restored to backlog`);
        loadBacklog();
        loadHiddenCount();
        toggleHiddenDropdown(); // refresh dropdown contents
        toggleHiddenDropdown(); // reopen with fresh data
    } catch (e) {
        showToast(e.message || 'Failed to unhide WO');
    }
}

async function unhideOp(opId) {
    try {
        await fetchJSON(`/api/operations/${opId}/hide`, { method: 'POST' });
        showToast(`Op ${opId} restored to backlog`);
        loadBacklog();
        loadHiddenCount();
        toggleHiddenDropdown(); // refresh dropdown contents
        toggleHiddenDropdown(); // reopen with fresh data
    } catch (e) {
        showToast(e.message || 'Failed to unhide op');
    }
}

// ── Board Filters ────────────────────────────────────────────────────────────

function initFilters() {
    loadFilterState();

    // Toggle filter panel visibility
    const toggle = document.getElementById('filter-toggle');
    const controls = document.getElementById('filter-controls');
    if (toggle && controls) {
        // Restore collapsed state
        const wasOpen = localStorage.getItem('filter_bar_open') === 'true';
        if (wasOpen) controls.style.display = 'flex';
        toggle.addEventListener('click', () => {
            const open = controls.style.display === 'none';
            controls.style.display = open ? 'flex' : 'none';
            localStorage.setItem('filter_bar_open', open);
        });
    }

    // Wire up all filter controls
    const filterIds = [
        'filter-search', 'filter-customer', 'filter-material-type',
        'filter-scheduled', 'filter-running', 'filter-complete',
        'filter-pastdue', 'filter-urgent', 'filter-normal', 'filter-nodate',
        'filter-needs-program', 'filter-needs-material', 'filter-needs-tools',
    ];
    filterIds.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const event = el.type === 'checkbox' ? 'change' : 'input';
        el.addEventListener(event, () => applyFilters());
        // Also listen for change on selects
        if (el.tagName === 'SELECT') el.addEventListener('change', () => applyFilters());
    });

    // Clear button
    const clearBtn = document.getElementById('filter-clear');
    if (clearBtn) clearBtn.addEventListener('click', clearFilters);

    // Populate dropdowns from current events and apply initial filters
    populateCustomerFilter(allEvents);
    populateMaterialTypeFilter(allEvents);
    applyFilters();
}
