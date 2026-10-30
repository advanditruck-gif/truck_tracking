const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const inr = v => '₹' + (+v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const km = v => v == null ? '—' : (+v).toLocaleString('en-IN');
const fmtDate = s => {
    if (!s) return '—';
    const d = new Date(s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};
const localDateKey = s => {
    const d = new Date(s);
    if (isNaN(d)) return '';
    const p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
};
const todayStr = () => {
    const d = new Date(), p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
};
const labels = {
    start_km: 'Odometer — start',
    stop_km: 'Odometer — end',
    location: 'Location photo',
    fuel: 'Fuel bill',
    visit: 'Business visit'
};
const folders = [
    { id: 'all', label: 'All records', icon: '▤' },
    { id: 'odo', label: 'Odometer', icon: '◉' },
    { id: 'fuel', label: 'Fuel bills', icon: '▣' },
    { id: 'petrol', label: 'Petrol', icon: '·', child: true },
    { id: 'diesel', label: 'Diesel', icon: '·', child: true },
    { id: 'location', label: 'Location', icon: '⌖' },
    { id: 'visit', label: 'Business visits', icon: '▧' }
];

let REPORTS = [], RECORDS = [], selectedFolder = 'all', dateFilter = '';

function categoryOf(record) {
    if (record.type === 'start_km' || record.type === 'stop_km') return 'odo';
    if (record.type === 'location') return 'location';
    if (record.type === 'visit') return 'visit';
    if (record.type === 'fuel') {
        const fuel = String(record.data.fuel_for || record.data.product || '').toLowerCase();
        return fuel.includes('petrol') ? 'petrol' : fuel.includes('diesel') ? 'diesel' : 'fuel';
    }
    return 'all';
}

function recordDate(record) {
    return localDateKey(record.at) || String(record.at || '').slice(0, 10);
}

function reportDate(report) {
    const raw = String(report.date || '');
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    return localDateKey(raw) || raw;
}

async function load() {
    const app = $('#app');
    app.innerHTML = '<p class="mu">Loading records…</p>';
    try {
        const response = await fetch('/api/report/records');
        if (!response.ok) throw new Error('Server returned ' + response.status);
        const data = await response.json();
        REPORTS = data.reports || [];
        RECORDS = data.records || [];
        draw();
    } catch (error) {
        app.innerHTML = '<p class="rep-empty">Could not load records: ' + esc(error.message) + '</p>';
    }
}

function selectedRecords() {
    return RECORDS.filter(record => {
        if (dateFilter && recordDate(record) !== dateFilter) return false;
        const category = categoryOf(record);
        if (selectedFolder === 'all') return true;
        if (selectedFolder === 'odo') return category === 'odo';
        if (selectedFolder === 'fuel') return ['petrol', 'diesel'].includes(category);
        return category === selectedFolder;
    }).sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')));
}

function folderCount(folderId, records) {
    const images = records.filter(record => record.has_image);
    if (folderId === 'all') return records.length;
    if (folderId === 'odo') return images.filter(record => categoryOf(record) === 'odo').length;
    if (folderId === 'fuel') return images.filter(record => ['petrol', 'diesel'].includes(categoryOf(record))).length;
    if (folderId === 'visit') return records.filter(record => categoryOf(record) === 'visit').length;
    return images.filter(record => categoryOf(record) === folderId).length;
}

function renderSidebar(records) {
    return '<aside class="rep-sidebar" aria-label="Record folders">' +
        '<div class="rep-sidebar-title">FOLDERS</div>' +
        folders.map(folder => {
            const count = folderCount(folder.id, records);
            return '<button class="rep-folder' + (folder.child ? ' child' : '') +
                (selectedFolder === folder.id ? ' active' : '') + '" data-folder="' + folder.id + '"' +
                (folder.id === 'fuel' ? ' aria-label="All fuel bills"' : '') + '>' +
                '<span class="rep-folder-icon">' + folder.icon + '</span><span class="rep-folder-name">' +
                esc(folder.label) + '</span><span class="rep-folder-count">' + count + '</span></button>';
        }).join('') +
        '<a class="rep-back-link" href="/">← Back to run log</a></aside>';
}

function renderToolbar(imageCount = null) {
    return '<div class="rep-toolbar"><div class="rep-toolbar-heading"><h1>' +
        esc((folders.find(folder => folder.id === selectedFolder) || folders[0]).label) +
        '</h1><p class="mu">' + (dateFilter ? 'Records for ' + esc(fmtDate(dateFilter)) : 'Full history from the database') +
        '</p></div>' + (imageCount === null ? '' :
        '<div class="rep-image-toolbar-title"><h2>Images</h2><span class="rep-section-count">' + imageCount + '</span></div>') +
        '<div class="rep-toolbar-actions"><label for="rep-date">Date</label>' +
        '<input type="date" id="rep-date" value="' + esc(dateFilter) + '">' +
        (dateFilter ? '<button class="g rep-clear" id="rep-clear" type="button">All dates</button>' : '') +
        '</div></div>';
}

function renderImages(records) {
    const images = records.filter(record => record.has_image);
    const cards = images.map(record => {
        const imageUrl = '/report/image/' + encodeURIComponent(record.id);
        const fuel = record.data.fuel_for || record.data.product;
        const title = record.type === 'fuel' ? (fuel || 'Fuel bill') :
            (labels[record.type] || 'Uploaded image');
        const time = record.at && !isNaN(new Date(record.at))
            ? new Date(record.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
            : 'Time unavailable';
        return '<a class="rep-image-card" href="' + imageUrl + '" target="_blank" rel="noopener">' +
            '<img src="' + imageUrl + '" alt="' + esc(title) + '" loading="lazy">' +
            '<span><b>' + esc(title) + '</b><small>' + esc(fmtDate(recordDate(record))) + ' · ' +
            esc(time) + '</small></span></a>';
    }).join('');
    return '<section class="rep-section rep-image-section">' +
        (cards ? '<div class="rep-image-grid">' + cards + '</div>' :
            '<div class="rep-empty">No images in this folder for the selected date.</div>') +
        '</section>';
}

function formatValue(value) {
    if (Array.isArray(value)) return value.map(formatValue).join(', ');
    if (value && typeof value === 'object') return JSON.stringify(value);
    if (value === true) return 'Yes';
    if (value === false) return 'No';
    return String(value);
}

function renderRecords(records) {
    const cards = records.map(record => {
        const time = record.at && !isNaN(new Date(record.at))
            ? new Date(record.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
            : 'Time unavailable';
        const detailRows = Object.entries(record.data || {})
            .filter(([, value]) => value !== null && value !== undefined && value !== '')
            .map(([key, value]) => '<div class="rep-detail"><span>' + esc(key.replace(/_/g, ' ')) +
                '</span><b>' + esc(formatValue(value)) + '</b></div>').join('');
        const imageLink = record.has_image && !['all', 'visit'].includes(selectedFolder)
            ? '<a class="rep-record-image" href="/report/image/' + encodeURIComponent(record.id) +
              '" target="_blank" rel="noopener">Open image</a>'
            : '';
        return '<article class="rep-record"><header><div><h3>' +
            esc(labels[record.type] || record.type.replace(/_/g, ' ')) +
            (record.type === 'fuel' ? ' · ' + esc(record.data.fuel_for || record.data.product || '') : '') +
            '</h3><span>' + esc(fmtDate(recordDate(record))) + ' · ' + esc(time) + '</span></div>' +
            '<small>Run ' + esc(record.run ?? '—') + '</small></header>' +
            '<div class="rep-details">' + (detailRows || '<span class="mu">No text details stored.</span>') +
            '</div>' + imageLink + '</article>';
    }).join('');
    return '<section class="rep-section"><div class="rep-section-head"><h2>Database records</h2>' +
        '<span class="rep-section-count">' + records.length + '</span></div>' +
        (cards ? '<div class="rep-record-list">' + cards + '</div>' :
            '<div class="rep-empty">No records in this folder for the selected date.</div>') +
        '</section>';
}

function renderRunKpis() {
    const runs = REPORTS.filter(report => !dateFilter || reportDate(report) === dateFilter);
    const sum = key => runs.reduce((total, report) => total + (+report[key] || 0), 0);
    return '<section class="rep-summary">' +
        '<div class="rep-card"><b>' + runs.length + '</b><span>Runs</span></div>' +
        '<div class="rep-card"><b>' + km(runs.reduce((total, report) => total + (report.distance_km || 0), 0)) +
        '</b><span>Total distance (km)</span></div>' +
        '<div class="rep-card"><b>' + inr(sum('petrol_amount')) + '</b><span>Total petrol</span></div>' +
        '<div class="rep-card"><b>' + inr(sum('diesel_amount')) + '</b><span>Total diesel</span></div>' +
        '<div class="rep-card"><b>' + inr(sum('balance_amount')) + '</b><span>Balance (collected − fuel)</span></div></section>';
}

function renderRunSummary() {
    if (selectedFolder !== 'all') return '';
    const runs = REPORTS.filter(report => !dateFilter || reportDate(report) === dateFilter);
    const rows = runs.map(report => '<tr><td>' + esc(fmtDate(report.date)) + '</td>' +
        '<td>' + km(report.start_km) + '</td><td>' + esc(report.start_time || '—') + '</td>' +
        '<td>' + km(report.end_km) + '</td><td>' + esc(report.end_time || '—') + '</td>' +
        '<td>' + km(report.distance_km) + '</td><td>' + inr(report.petrol_amount) + '</td>' +
        '<td>' + inr(report.diesel_amount) + '</td><td>' + inr(report.collected_amount) + '</td>' +
        '<td>' + inr(report.balance_amount) + '</td><td>' + esc(report.areas_covered.join(', ') || '—') + '</td>' +
        '<td>' + (report.is_open ? 'In progress' : 'Closed') + '</td></tr>').join('');
    const table = '<section class="rep-section"><div class="rep-section-head"><h2>Run summary</h2>' +
        '<button class="g rep-export" id="rep-csv" type="button">Export CSV</button></div>' +
        (rows ? '<div class="rep-table-wrap"><table class="rep"><thead><tr><th>Date</th><th>Start KM</th>' +
            '<th>Start time</th><th>End KM</th><th>End time</th><th>Distance</th><th>Petrol</th><th>Diesel</th>' +
            '<th>Collected</th><th>Balance</th><th>Areas</th><th>Status</th></tr></thead><tbody>' + rows +
            '</tbody></table></div>' : '<div class="rep-empty">No runs for the selected date.</div>') +
        '</section>';
    return table;
}

function exportCsv() {
    const rows = REPORTS.filter(report => !dateFilter || reportDate(report) === dateFilter);
    const header = ['date', 'start_km', 'start_time', 'end_km', 'end_time', 'distance_km',
        'petrol_amount', 'diesel_amount', 'collected_amount', 'balance_amount', 'areas_covered', 'status'];
    const lines = [header].concat(rows.map(report => [
        report.date || '', report.start_km ?? '', report.start_time || '', report.end_km ?? '',
        report.end_time || '', report.distance_km ?? '', report.petrol_amount, report.diesel_amount,
        report.collected_amount, report.balance_amount, report.areas_covered.join(' | '),
        report.is_open ? 'In progress' : 'Closed'
    ]));
    const data = lines.map(row => row.map(value => '"' + String(value).replace(/"/g, '""') + '"').join(',')).join('\n');
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(new Blob([data], { type: 'text/csv' }));
    anchor.download = 'ad-vandi-report-' + todayStr() + '.csv';
    anchor.click();
    URL.revokeObjectURL(anchor.href);
}

function draw() {
    const records = selectedRecords();
    const datedRecords = dateFilter ? RECORDS.filter(record => recordDate(record) === dateFilter) : RECORDS;
    const showImages = ['odo', 'fuel', 'petrol', 'diesel', 'location'].includes(selectedFolder);
    const imageCount = showImages ? records.filter(record => record.has_image).length : null;
    const showRecordDetails = !['all', 'odo'].includes(selectedFolder);
    const isAllRecords = selectedFolder === 'all';
    document.querySelector('main.report-main').classList.toggle('report-all-records', isAllRecords);
    const overview = isAllRecords
        ? '<div class="rep-overview">' + renderToolbar() + renderRunKpis() + '</div>'
        : renderToolbar(imageCount);
    $('#app').innerHTML = '<div class="rep-layout' + (isAllRecords ? ' all-records' : '') + '">' +
        renderSidebar(datedRecords) +
        '<section class="rep-content">' + overview +
        (showImages ? renderImages(records) : '') +
        (isAllRecords ? renderRunSummary() : showRecordDetails ? renderRecords(records) : '') + '</section></div>';
    const header = document.querySelector('.report-main>.top');
    header.querySelector('.rep-toolbar-heading')?.remove();
    const pageHeading = document.querySelector('.rep-toolbar-heading');
    header.appendChild(pageHeading);
    document.querySelectorAll('[data-folder]').forEach(button => {
        button.onclick = () => { selectedFolder = button.dataset.folder; draw() };
    });
    $('#rep-date').onchange = event => { dateFilter = event.target.value; draw() };
    const clear = $('#rep-clear');
    if (clear) clear.onclick = () => { dateFilter = ''; draw() };
    const csv = $('#rep-csv');
    if (csv) csv.onclick = exportCsv;
}

load();
