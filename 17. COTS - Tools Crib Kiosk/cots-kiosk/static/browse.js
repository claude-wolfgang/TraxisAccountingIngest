var currentPage = 0;
var pageSize = 50;
var currentQuery = '';
var searchTimeout = null;

document.addEventListener('DOMContentLoaded', function() {
    var input = document.getElementById('search-input');
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            clearTimeout(searchTimeout);
            doSearch();
        }
    });
    input.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(doSearch, 350);
    });
    doSearch();
});

function doSearch() {
    currentQuery = document.getElementById('search-input').value.trim();
    currentPage = 0;
    fetchItems();
}

function fetchItems() {
    var url = '/api/cots?page=' + currentPage + '&page_size=' + pageSize;
    if (currentQuery) url += '&q=' + encodeURIComponent(currentQuery);

    apiFetch(url).then(function(data) {
        renderTable(data.records || []);
        renderPagination(data.totalRecords || 0);
        document.getElementById('results-count').textContent =
            (data.totalRecords || 0) + ' items found';
    }).catch(function() {
        document.getElementById('items-tbody').innerHTML =
            '<tr><td colspan="7" class="loading">Failed to load items.</td></tr>';
    });
}

function renderTable(records) {
    var tbody = document.getElementById('items-tbody');
    if (!records.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="loading">No items found.</td></tr>';
        return;
    }
    var html = '';
    records.forEach(function(r) {
        var qty = parseQty(r.quantity);
        var minQty = parseQty(r.minimumQuantityOnHand);
        var qtyClass = (minQty > 0 && qty <= minQty) ? 'qty-low' : '';
        html += '<tr onclick="showDetail(\'' + escapeAttr(r.otsId) + '\')">' +
            '<td>' + esc(r.otsId) + '</td>' +
            '<td><strong>' + esc(r.aka) + '</strong></td>' +
            '<td>' + esc(r.type) + '</td>' +
            '<td>' + esc(r.location) + '</td>' +
            '<td class="' + qtyClass + '">' + qty + '</td>' +
            '<td>' + (minQty || '-') + '</td>' +
            '<td>' + esc(r.description || '') + '</td>' +
            '</tr>';
    });
    tbody.innerHTML = html;
}

function renderPagination(total) {
    var pages = Math.ceil(total / pageSize);
    if (pages <= 1) { document.getElementById('pagination').innerHTML = ''; return; }
    var html = '';
    if (currentPage > 0) {
        html += '<button class="btn btn-secondary" onclick="goPage(' + (currentPage - 1) + ')">Prev</button>';
    }
    html += '<span style="padding:8px 12px;color:#64748b">Page ' + (currentPage + 1) + ' of ' + pages + '</span>';
    if (currentPage < pages - 1) {
        html += '<button class="btn btn-secondary" onclick="goPage(' + (currentPage + 1) + ')">Next</button>';
    }
    document.getElementById('pagination').innerHTML = html;
}

function goPage(page) {
    currentPage = page;
    fetchItems();
}

function showDetail(otsId) {
    apiFetch('/api/cots/' + encodeURIComponent(otsId)).then(function(item) {
        document.getElementById('modal-title').textContent = item.aka || item.otsId;
        document.getElementById('modal-edit-link').href = '/edit/' + encodeURIComponent(item.otsId);

        var fields = [
            ['ID', item.otsId], ['Number', item.number], ['Type', item.type],
            ['Subclass', item.subclass], ['Description', item.description],
            ['Location', item.location], ['Quantity', item.quantity],
            ['Inventory Qty', item.inventoryQuantity],
            ['Min Qty', item.minimumQuantityOnHand], ['Reorder Point', item.minReorderPoint],
            ['Material', item.material], ['Thread', item.thread],
            ['OD', item.od], ['Length', item.length], ['Units', item.units],
            ['Serialized', item.isSerialized], ['Part', item.partPlainText],
            ['Created', item.createdTime], ['Modified', item.lastModifiedTime],
        ];

        var html = '';
        fields.forEach(function(f) {
            var val = f[1];
            if (val === null || val === undefined || val === '') return;
            html += '<div class="modal-field">' +
                '<span class="modal-field-label">' + f[0] + '</span><br>' +
                '<span class="modal-field-value">' + esc(String(val)) + '</span>' +
                '</div>';
        });
        document.getElementById('modal-body').innerHTML = html;
        document.getElementById('detail-modal').classList.remove('hidden');
    });
}

function closeModal() {
    document.getElementById('detail-modal').classList.add('hidden');
}

function parseQty(val) {
    if (val === null || val === undefined || val === '') return 0;
    var n = parseFloat(val);
    return isNaN(n) ? 0 : Math.floor(n);
}

function esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function escapeAttr(s) {
    return String(s).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
