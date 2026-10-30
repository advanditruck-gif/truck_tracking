const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const inr = v => '₹' + (+v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const km = v => v == null ? '—' : (+v).toLocaleString('en-IN');
const fmtDate = s => { if (!s) return '—'; const d = new Date(s); if (isNaN(d)) return s; return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) };
const kmText = v => v == null ? '—' : km(v) + ' km';
const row = (label, value, cls) => '<div class="rep-row"><span>' + esc(label) + '</span><b' + (cls ? ' class="' + cls + '"' : '') + '>' + esc(value) + '</b></div>';

const todayStr = () => { const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) };

let ALL = [], dateFilter = todayStr(); // opens on today's report; pick another date to see other days

async function load() {
    const app = $('#app');
    app.innerHTML = '<p class="mu">Loading report…</p>';
    try {
        const r = await fetch('/api/report');
        ALL = await r.json();
    } catch (e) {
        app.innerHTML = '<p class="rep-empty">Could not load the report: ' + esc(e.message) + '</p>';
        return;
    }
    draw();
}

function summary(rows) {
    const sum = k => rows.reduce((a, r) => a + (+r[k] || 0), 0);
    return {
        runs: rows.length,
        distance: rows.reduce((a, r) => a + (r.distance_km || 0), 0),
        petrol: sum('petrol_amount'),
        diesel: sum('diesel_amount'),
        balance: sum('balance_amount'),
    };
}

function draw() {
    const rows = dateFilter ? ALL.filter(r => r.date === dateFilter) : ALL;
    const s = summary(rows);

    const cards = '<section class="rep-summary">' +
        '<div class="rep-card"><b>' + s.runs + '</b><span>Runs</span></div>' +
        '<div class="rep-card"><b>' + km(s.distance) + '</b><span>Total distance (km)</span></div>' +
        '<div class="rep-card"><b>' + inr(s.petrol) + '</b><span>Total petrol</span></div>' +
        '<div class="rep-card"><b>' + inr(s.diesel) + '</b><span>Total diesel</span></div>' +
        '<div class="rep-card"><b>' + inr(s.balance) + '</b><span>Balance (collected − fuel)</span></div>' +
        '</section>';

    const bar = '<div class="rep-bar"><div class="field"><label for="rep-date">Date</label>' +
        '<input type="date" id="rep-date" value="' + esc(dateFilter) + '">' +
        (dateFilter ? '<button class="g rep-clear" id="rep-clear" type="button">All dates</button>' : '') +
        '</div><button id="rep-csv">Export CSV</button></div>';

    const head = '<tr><th>Date</th><th>Start KM</th><th>Start time</th><th>End KM</th><th>End time</th>' +
        '<th>Distance</th><th>Petrol</th><th>Diesel</th><th>Collected</th><th>Balance</th><th>Areas covered</th><th>Status</th></tr>';

    const body = rows.map(r => '<tr>' +
        '<td>' + esc(fmtDate(r.date)) + '</td>' +
        '<td class="num">' + km(r.start_km) + '</td>' +
        '<td>' + esc(r.start_time) + '</td>' +
        '<td class="num">' + km(r.end_km) + '</td>' +
        '<td>' + esc(r.end_time || '—') + '</td>' +
        '<td class="num">' + (r.distance_km != null ? km(r.distance_km) : '—') + '</td>' +
        '<td class="num">' + inr(r.petrol_amount) + '</td>' +
        '<td class="num">' + inr(r.diesel_amount) + '</td>' +
        '<td class="num">' + inr(r.collected_amount) + '</td>' +
        '<td class="num ' + (r.balance_amount < 0 ? 'balance-neg' : 'balance-pos') + '">' + inr(r.balance_amount) + '</td>' +
        '<td class="areas">' + (r.areas_covered.length ? r.areas_covered.map(a => '<span class="area-pill">' + esc(a) + '</span>').join('') : '<span class="mu">—</span>') + '</td>' +
        '<td><span class="status-pill ' + (r.is_open ? 'open' : 'closed') + '">' + (r.is_open ? 'In progress' : 'Closed') + '</span></td>' +
        '</tr>').join('');

    const table = rows.length
        ? '<div class="rep-table-wrap"><table class="rep"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>'
        : '<div class="rep-table-wrap"><div class="rep-empty">No runs recorded yet' + (dateFilter ? ' for this date' : '') + '.</div></div>';

    const runCards = rows.length
        ? '<div class="rep-cards">' + rows.map(r => '<div class="rep-card-run">' +
            '<div class="rep-card-run-head"><span class="rep-card-run-date">' + esc(fmtDate(r.date)) + '</span>' +
            '<span class="status-pill ' + (r.is_open ? 'open' : 'closed') + '">' + (r.is_open ? 'In progress' : 'Closed') + '</span></div>' +
            row('Start KM', kmText(r.start_km)) +
            row('Start time', r.start_time || '—') +
            row('End KM', kmText(r.end_km)) +
            row('End time', r.end_time || '—') +
            row('Total Petrol', inr(r.petrol_amount)) +
            row('Total Diesel', inr(r.diesel_amount)) +
            row('Balance amount', inr(r.balance_amount), r.balance_amount < 0 ? 'balance-neg' : 'balance-pos') +
            row('Areas covered', r.areas_covered.length ? r.areas_covered.join(', ') : '—') +
            '</div>').join('') + '</div>'
        : '<div class="rep-cards"><div class="rep-empty">No runs recorded yet' + (dateFilter ? ' for this date' : '') + '.</div></div>';

    $('#app').innerHTML = cards + bar + runCards + table;
    $('#rep-date').onchange = e => { dateFilter = e.target.value; draw() };
    $('#rep-clear') && ($('#rep-clear').onclick = () => { dateFilter = ''; draw() });
    $('#rep-csv').onclick = () => exportCsv(rows);
}

function exportCsv(rows) {
    const header = ['date', 'start_km', 'start_time', 'end_km', 'end_time', 'distance_km',
        'petrol_amount', 'diesel_amount', 'collected_amount', 'balance_amount', 'areas_covered', 'status'];
    const lines = [header].concat(rows.map(r => [
        r.date || '', r.start_km ?? '', r.start_time || '', r.end_km ?? '', r.end_time || '',
        r.distance_km ?? '', r.petrol_amount, r.diesel_amount, r.collected_amount, r.balance_amount,
        r.areas_covered.join(' | '), r.is_open ? 'In progress' : 'Closed'
    ]));
    const data = lines.map(row => row.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\n');
    const name = 'ad-vandi-report-' + new Date().toISOString().slice(0, 10) + '.csv';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([data], { type: 'text/csv' }));
    a.download = name;
    a.click();
}

load();