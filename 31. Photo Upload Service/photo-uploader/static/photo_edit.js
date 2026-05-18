(function() {
    const form = document.getElementById('edit-form');
    const delBtn = document.getElementById('delete-btn');

    if (form) {
        const entityType = form.dataset.entityType;
        const entityId = form.dataset.entityId;
        const photoId = form.dataset.photoId;
        const currentOp = form.dataset.currentOp || '';
        const select = document.getElementById('operation_select');

        const param = entityType === 'workorder' ? 'wo' : 'part';
        fetch(`/api/operations?${param}=${encodeURIComponent(entityId)}`)
            .then(r => r.json())
            .then(data => {
                const ops = data.ops || [];
                if (!ops.length) {
                    select.innerHTML = '<option value="">No operations found</option>';
                    return;
                }
                const parts = ['<option value="">— select operation —</option>'];
                for (const op of ops) {
                    const num = op.opNumber || op.operationNumber || op.number || '';
                    const desc = op.description || op.desc || '';
                    const label = desc ? `${num} — ${desc}` : `${num}`;
                    const sel = String(num) === String(currentOp) ? ' selected' : '';
                    parts.push(`<option value="${num}"${sel}>${label}</option>`);
                }
                select.innerHTML = parts.join('');
            })
            .catch(err => {
                console.error('ops fetch failed', err);
                select.innerHTML = '<option value="">Error loading operations</option>';
            });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const opNum = select.value;
            if (!opNum) {
                alert('Pick an operation first.');
                return;
            }
            const opt = select.options[select.selectedIndex];
            const desc = (opt.textContent.split(' — ')[1] || '').trim();
            const r = await fetch(`/api/photos/${photoId}/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    operation_number: opNum,
                    operation_desc: desc,
                    retry: true,
                }),
            });
            if (r.ok) {
                window.location = '/queue';
            } else {
                let msg = 'HTTP ' + r.status;
                try { msg = (await r.json()).error || msg; } catch (_) {}
                alert('Save failed: ' + msg);
            }
        });
    }

    const claudeBtn = document.getElementById('claude-btn');
    if (claudeBtn) {
        claudeBtn.addEventListener('click', async () => {
            if (!confirm('Send this photo to the Claude folder? Upload attempts will stop.')) return;
            const photoId = claudeBtn.dataset.photoId;
            const r = await fetch(`/api/photos/${photoId}/send-to-claude`, {method: 'POST'});
            if (r.ok) {
                window.location = '/queue';
            } else {
                let msg = 'HTTP ' + r.status;
                try { msg = (await r.json()).error || msg; } catch (_) {}
                alert('Failed: ' + msg);
            }
        });
    }

    if (delBtn) {
        delBtn.addEventListener('click', async () => {
            if (!confirm('Delete this photo? This cannot be undone.')) return;
            const photoId = delBtn.dataset.photoId;
            const r = await fetch(`/api/photos/${photoId}/delete`, {method: 'POST'});
            if (r.ok) {
                window.location = '/queue';
            } else {
                alert('Delete failed');
            }
        });
    }
})();
