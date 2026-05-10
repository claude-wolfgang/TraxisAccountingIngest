// ── Operator View — Progress, Flags, Celebrations ───────────────────────────

let selectedMachine = null;
let currentBlock = null;
let audioCtx = null;

// ── Initialization ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    // Restore machine from localStorage
    selectedMachine = localStorage.getItem('operator_machine');

    const machines = await fetchJSON('/api/machines');
    renderMachineSelector(machines);

    if (selectedMachine) {
        document.getElementById('machine-selector').style.display = 'none';
        document.getElementById('machine-label').textContent =
            machines.find(m => m.id === selectedMachine)?.name || selectedMachine;
        document.getElementById('machine-label').style.cursor = 'pointer';
        document.getElementById('machine-label').onclick = () => {
            localStorage.removeItem('operator_machine');
            selectedMachine = null;
            document.getElementById('machine-selector').style.display = '';
            document.getElementById('machine-label').textContent = '';
            document.getElementById('now-running').style.display = 'none';
            document.getElementById('no-job').style.display = 'none';
            document.getElementById('up-next').style.display = 'none';
        };
        loadMachineData();
    }

    // Refresh every 15s
    setInterval(() => {
        if (selectedMachine) loadMachineData();
    }, 15000);
});

// ── Machine Selector ─────────────────────────────────────────────────────────

function renderMachineSelector(machines) {
    const container = document.getElementById('machine-selector');
    container.innerHTML = machines.map(m => `
        <button class="machine-btn ${m.id === selectedMachine ? 'selected' : ''}"
                onclick="selectMachine('${m.id}', '${m.name}')">
            ${m.name}
        </button>
    `).join('');
}

function selectMachine(id, name) {
    selectedMachine = id;
    localStorage.setItem('operator_machine', id);
    document.getElementById('machine-selector').style.display = 'none';
    document.getElementById('machine-label').textContent = name;
    document.getElementById('machine-label').style.cursor = 'pointer';
    document.getElementById('machine-label').onclick = () => {
        localStorage.removeItem('operator_machine');
        selectedMachine = null;
        document.getElementById('machine-selector').style.display = '';
        document.getElementById('machine-label').textContent = '';
        document.getElementById('now-running').style.display = 'none';
        document.getElementById('no-job').style.display = 'none';
        document.getElementById('up-next').style.display = 'none';
        document.getElementById('completed-today').style.display = 'none';
    };
    loadMachineData();
}

// ── Load Machine Data ────────────────────────────────────────────────────────

async function loadMachineData() {
    if (!selectedMachine) return;

    const now = new Date();
    const weekEnd = new Date(now.getTime() + 7 * 86400000);

    const blocks = await fetchJSON(
        `/api/blocks?machine=${selectedMachine}&start=${now.toISOString()}&end=${weekEnd.toISOString()}`
    );

    // Find currently running or next scheduled
    const running = blocks.find(b => b.extendedProps?.status === 'running');
    const scheduled = blocks.filter(b =>
        b.extendedProps?.status === 'scheduled' && new Date(b.start) >= now
    ).sort((a, b) => new Date(a.start) - new Date(b.start));

    currentBlock = running || scheduled[0] || null;

    if (currentBlock) {
        showCurrentJob(currentBlock);
        const queue = running ? scheduled : scheduled.slice(1);
        showQueue(queue);
    } else {
        document.getElementById('now-running').style.display = 'none';
        document.getElementById('no-job').style.display = 'block';
    }

    // Load stats
    const stats = await fetchJSON('/api/stats');
    if (stats.completed_today > 0) {
        document.getElementById('completions-banner').style.display = 'block';
        document.getElementById('completions-count').textContent = stats.completed_today;
    }
}

// ── Show Current Job ─────────────────────────────────────────────────────────

function showCurrentJob(block) {
    const p = block.extendedProps;
    document.getElementById('now-running').style.display = 'block';
    document.getElementById('no-job').style.display = 'none';

    document.getElementById('job-title').textContent =
        `WO${p.wo_number} Op${p.op_number}`;
    document.getElementById('job-detail').textContent =
        `${p.part_name || p.op_name || ''} — ${p.customer || ''}`;

    const dueText = formatDueDate(p.due_date);
    const dueClass = getDueClass(p.due_date);
    document.getElementById('job-due').textContent = dueText;
    document.getElementById('job-due').className = `due-countdown ${dueClass}`;

    updateQtyDisplay(p.qty_complete || 0, p.qty_required || 0);
}

function updateQtyDisplay(done, total) {
    document.getElementById('qty-done').textContent = done;
    document.getElementById('qty-total').textContent = total;
    const pct = total > 0 ? Math.min(100, Math.round(done / total * 100)) : 0;
    document.getElementById('progress-fill').style.width = pct + '%';
}

// ── Show Queue ───────────────────────────────────────────────────────────────

function showQueue(queue) {
    if (queue.length === 0) {
        document.getElementById('up-next').style.display = 'none';
        return;
    }

    document.getElementById('up-next').style.display = 'block';
    document.getElementById('queue-items').innerHTML = queue.map(b => {
        const p = b.extendedProps;
        const dueText = formatDueDate(p.due_date);
        const dueClass = getDueClass(p.due_date);
        const time = new Date(b.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return `
            <div class="queue-item">
                <div>
                    <strong>WO${p.wo_number} Op${p.op_number}</strong>
                    <div style="font-size:12px; color:var(--text-muted)">${p.part_name || p.op_name || ''}</div>
                </div>
                <div style="text-align:right">
                    <div class="due-countdown ${dueClass}" style="font-size:12px">${dueText}</div>
                    <div style="font-size:11px; color:var(--text-subtle)">${time}</div>
                </div>
            </div>
        `;
    }).join('');
}

// ── Part Buttons ─────────────────────────────────────────────────────────────

async function addParts(qty) {
    if (!currentBlock) return;
    const blockId = currentBlock.extendedProps.block_id;

    try {
        const result = await fetchJSON(`/api/blocks/${blockId}/progress`, {
            method: 'POST',
            body: { qty, operator: 'operator' },
        });

        updateQtyDisplay(result.qty_complete, result.qty_required);

        // Update local state
        currentBlock.extendedProps.qty_complete = result.qty_complete;
        currentBlock.extendedProps.progress = result.progress;

        // Brief visual feedback
        const btns = document.querySelectorAll('.part-btn');
        btns.forEach(b => b.style.background = 'rgba(34,197,94,0.3)');
        setTimeout(() => btns.forEach(b => b.style.background = ''), 200);
    } catch (e) {
        console.error('Failed to update progress:', e);
    }
}

// ── Mark Complete ────────────────────────────────────────────────────────────

async function markComplete() {
    if (!currentBlock) return;
    const blockId = currentBlock.extendedProps.block_id;

    try {
        const result = await fetchJSON(`/api/blocks/${blockId}/complete`, {
            method: 'POST',
            body: { operator: 'operator' },
        });

        // Celebration!
        playChime();
        fireConfetti();

        // Update completions count
        document.getElementById('completions-banner').style.display = 'block';
        document.getElementById('completions-count').textContent = result.completed_today;

        // Reload after a moment
        setTimeout(() => loadMachineData(), 2000);
    } catch (e) {
        console.error('Failed to complete:', e);
    }
}

// ── Flag Modal ───────────────────────────────────────────────────────────────

function openFlagModal() {
    document.getElementById('flag-modal').classList.add('open');
    document.getElementById('flag-description').value = '';
}

function closeFlagModal() {
    document.getElementById('flag-modal').classList.remove('open');
}

async function submitFlag() {
    const category = document.getElementById('flag-category').value;
    const description = document.getElementById('flag-description').value.trim();

    if (!description) {
        document.getElementById('flag-description').style.borderColor = 'var(--accent-red)';
        return;
    }

    try {
        await fetchJSON('/api/flags', {
            method: 'POST',
            body: {
                block_id: currentBlock?.extendedProps?.block_id,
                operation_id: currentBlock?.extendedProps ? `${currentBlock.extendedProps.wo_number}-${currentBlock.extendedProps.op_number}` : null,
                machine_id: selectedMachine,
                category,
                description,
                flagged_by: 'operator',
            },
        });
        closeFlagModal();
    } catch (e) {
        console.error('Failed to submit flag:', e);
    }
}

// ── Celebrations: Confetti ───────────────────────────────────────────────────

function fireConfetti() {
    const canvas = document.getElementById('confetti-canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const pieces = [];
    const colors = ['#22c55e', '#3b82f6', '#eab308', '#f97316', '#a855f7', '#ef4444', '#06b6d4'];

    for (let i = 0; i < 120; i++) {
        pieces.push({
            x: canvas.width / 2 + (Math.random() - 0.5) * 200,
            y: canvas.height / 2,
            vx: (Math.random() - 0.5) * 16,
            vy: -Math.random() * 18 - 4,
            w: Math.random() * 10 + 4,
            h: Math.random() * 6 + 2,
            color: colors[Math.floor(Math.random() * colors.length)],
            rot: Math.random() * Math.PI * 2,
            rotV: (Math.random() - 0.5) * 0.3,
            gravity: 0.3 + Math.random() * 0.2,
        });
    }

    let frame = 0;
    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let alive = false;
        for (const p of pieces) {
            p.x += p.vx;
            p.vy += p.gravity;
            p.y += p.vy;
            p.rot += p.rotV;
            p.vx *= 0.99;

            if (p.y < canvas.height + 50) {
                alive = true;
                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rot);
                ctx.fillStyle = p.color;
                ctx.globalAlpha = Math.max(0, 1 - frame / 120);
                ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
                ctx.restore();
            }
        }
        frame++;
        if (alive && frame < 150) {
            requestAnimationFrame(animate);
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }
    animate();
}

// ── Celebrations: Chime (Web Audio) ──────────────────────────────────────────

function playChime() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    playNote(523, 0);     // C5
    playNote(659, 0.12);  // E5
    playNote(784, 0.24);  // G5
    playNote(1047, 0.4);  // C6 — extra note for completion
}

function playNote(freq, delay) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.15, audioCtx.currentTime + delay);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + delay + 0.5);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(audioCtx.currentTime + delay);
    osc.stop(audioCtx.currentTime + delay + 0.6);
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
