function submitForm(e) {
    e.preventDefault();

    var otsId = document.getElementById('form-ots-id').value;
    var isEdit = !!otsId;

    var fields = ['aka', 'type', 'subclass', 'description', 'location', 'units',
                  'quantity', 'minimumQuantityOnHand', 'material', 'thread', 'od', 'length'];
    var data = {};
    fields.forEach(function(f) {
        var el = document.getElementById(f);
        if (el && el.value.trim() !== '') {
            data[f] = el.value.trim();
        }
    });

    if (!data.aka) { showToast('Item name is required', 'error'); return false; }
    if (!data.type) { showToast('Item type is required', 'error'); return false; }

    var btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    var url, method;
    if (isEdit) {
        url = '/api/cots/' + encodeURIComponent(otsId);
        method = 'PUT';
    } else {
        url = '/api/cots';
        method = 'POST';
    }

    apiFetch(url, { method: method, body: data }).then(function(result) {
        showToast(isEdit ? 'Item updated!' : 'Item created!', 'success');
        if (!isEdit && result && result.otsId) {
            setTimeout(function() { window.location.href = '/edit/' + result.otsId; }, 1000);
        }
        btn.disabled = false;
        btn.textContent = isEdit ? 'Update Item' : 'Create Item';
    }).catch(function() {
        btn.disabled = false;
        btn.textContent = isEdit ? 'Update Item' : 'Create Item';
    });

    return false;
}
