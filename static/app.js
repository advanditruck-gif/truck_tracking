const K = 'trk1', $ = s => document.querySelector(s);
let S; try { S = JSON.parse(localStorage.getItem(K)) } catch (e) { } S = S || { run: null, ev: [] }; S.pending = S.pending || [];
const showToast = (txt, ms = 3200) => {
    const el = $('#pwa-toast'); if (!el) return;
    el.textContent = txt; el.hidden = false;
    clearTimeout(el._tm); el._tm = setTimeout(() => { el.hidden = true }, ms);
};

const keep = () => { try { localStorage.setItem(K, JSON.stringify(S)) } catch (e) { } };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let sample = null; (async () => { try { if (window.claude) sample = await claude.use('sample') } catch (e) { } })();
const FIELDS = { cluster: ['km', 'date', 'time'], geo: ['date', 'time', 'road', 'location', 'district', 'state', 'gps'], fuel: ['date', 'time', 'receipt_no', 'product', 'rate', 'volume', 'amount', 'vehicle_no'], visit: ['business_name', 'area', 'amount_collected'] };
const P = {
    cluster: 'Read the vehicle instrument cluster. Prioritize the odometer value shown beside or above "ODO" (usually near the bottom of the display); ignore people, hands, reflections, and other dashboard values. Transcribe the odometer digits exactly as a number, without units or separators. Also read the displayed date and time if legible. Always return all three keys, using null only for a value that is genuinely unreadable. Return valid JSON only, in this shape: {"km": 7148, "date": "2026-10-28", "time": "20:00"}. Use null for unreadable values and 24-hour time.',
    geo: 'GPS-stamped camera photo. Read the overlay text. Return JSON {"date":"YYYY-MM-DD","time":"HH:MM" 24h,"road":"street line","location":"locality line","district":"","state":"","gps":"lat,lng if visible else empty"}.',
    fuel: 'Fuel pump bill, layout varies. Return JSON {"date":"YYYY-MM-DD","time":"HH:MM" 24h,"receipt_no":"receipt/voucher no, the unique id","product":"","rate":number,"volume":number,"amount":number,"vehicle_no":""}.'
};
async function extract(kind, blob) {
    try {
        if (sample) return await sample.json(P[kind] + ' Reply with JSON only; null if unreadable.', { images: [blob] });
        const f = new FormData(); f.append('kind', kind); f.append('image', blob, 'p.jpg');
        const r = await fetch('/api/extract', { method: 'POST', body: f }); if (!r.ok) return { _error: 'Server error ' + r.status + ' (see the terminal running app.py)' }; return await r.json();
    } catch (e) { return { _error: 'Cannot reach server: ' + e.message } }
}
async function reverseGeocode(coords) {
    try {
        const [lat, lon] = coords.split(',').map(Number); if (!Number.isFinite(lat) || !Number.isFinite(lon)) return { _error: 'Phone GPS coordinates are unavailable.' };
        const r = await fetch('/api/reverse-geocode?' + new URLSearchParams({ lat: String(lat), lon: String(lon) })); const d = await r.json(); if (!r.ok) return { _error: d.error || 'Address lookup failed.' }; return d;
    } catch (e) { return { _error: 'Address lookup failed: ' + e.message } }
}
function modal(h, kind = '') { const m = document.createElement('div'); m.className = 'md ' + kind; m.innerHTML = '<div class="bx">' + h + '</div>'; document.body.append(m); return m }
const busy = t => { const m = modal('<div class="spin"></div><h3>' + t + '</h3><p class="mu">This takes a few seconds.</p>', 'md-loading'); return () => m.remove() };
async function shrink(src) {
    const bm = await createImageBitmap(src), r = Math.min(1, 1920 / Math.max(bm.width, bm.height)), c = document.createElement('canvas');
    c.width = bm.width * r; c.height = bm.height * r; c.getContext('2d').drawImage(bm, 0, 0, c.width, c.height);
    return new Promise(ok => c.toBlob(ok, 'image/jpeg', .92))
}
const thumb = async b => {
    const bm = await createImageBitmap(b), c = document.createElement('canvas'); c.width = c.height = 96;
    const s = Math.min(bm.width, bm.height); c.getContext('2d').drawImage(bm, 0, 0, s, s, 0, 0, 96, 96); return c.toDataURL('image/jpeg', .6)
};
const gpsNow = fresh => new Promise(ok => { if (!navigator.geolocation) return ok({ err: 'This browser has no GPS support.' }); navigator.geolocation.getCurrentPosition(p => ok({ c: p.coords.latitude.toFixed(5) + ',' + p.coords.longitude.toFixed(5) }), e => ok({ err: e.code === 1 ? 'Location permission is blocked. Allow Location for this site in the browser settings.' : e.code === 3 ? 'GPS timed out. Turn on the phone Location switch and try again.' : 'GPS position unavailable. Turn on the phone Location switch.' }), { enableHighAccuracy: true, timeout: fresh ? 15000 : 20000, maximumAge: fresh ? 0 : 60000 }) });
// Live camera only: no gallery picker. Fallback = native camera intent (capture) if getUserMedia is blocked.
function shoot(title) {
    return new Promise(res => {
        const m = modal('<h3>' + title + '</h3><div class="vf"><video autoplay playsinline muted></video></div><p class="hint">Fill the frame with the subject and hold steady.</p><input type="file" accept="image/*" capture="environment" hidden><div class="row"><button class="g" id="x">Cancel</button><button id="c">' + ico('camera') + 'Capture</button></div>', 'md-camera');
        const v = m.querySelector('video'), frame = m.querySelector('.vf'), fb = m.querySelector('input'); let st = null, cam = false;
        const end = b => { st && st.getTracks().forEach(t => t.stop()); m.remove(); res(b) };
        navigator.mediaDevices?.getUserMedia({ video: { facingMode: { ideal: 'environment' }, aspectRatio: { ideal: frame.clientWidth / frame.clientHeight } }, audio: false }).then(s => { st = s; cam = true; v.srcObject = s }).catch(() => { v.hidden = true });
        m.querySelector('#x').onclick = () => end(null);
        m.querySelector('#c').onclick = async () => {
            if (!cam) return fb.click();
            const sourceWidth = v.videoWidth, sourceHeight = v.videoHeight, frameRatio = frame.clientWidth / frame.clientHeight;
            let sx = 0, sy = 0, sw = sourceWidth, sh = sourceHeight;
            if (sourceWidth / sourceHeight > frameRatio) { sw = sourceHeight * frameRatio; sx = (sourceWidth - sw) / 2 }
            else { sh = sourceWidth / frameRatio; sy = (sourceHeight - sh) / 2 }
            const c = document.createElement('canvas'); c.width = Math.round(sw); c.height = Math.round(sh);
            c.getContext('2d').drawImage(v, sx, sy, sw, sh, 0, 0, c.width, c.height);
            c.toBlob(async b => end(await shrink(b)), 'image/jpeg', .95)
        };
        fb.onchange = async () => fb.files[0] && end(await shrink(fb.files[0]));
    })
}
const LBL = { km: 'Odometer (km)', business_name: 'Business name', amount_collected: 'Amount collected (₹)', receipt_no: 'Receipt or voucher no.', vehicle_no: 'Vehicle no.', gps: 'GPS', rate: 'Rate (₹/L)', volume: 'Volume (L)', amount: 'Amount (₹)' }, NARROW = ['date', 'time', 'rate', 'volume', 'amount', 'district', 'state', 'product', 'vehicle_no'];
const validOdometer = value => /^\d+(?:\.\d+)?$/.test(String(value ?? '').replace(/,/g, '').trim());
function review(title, kind, vals, th, note) {
    if (kind === 'visit') return reviewVisit(vals);
    return new Promise(res => {
        const m = modal('<h3>' + title + '</h3><p class="mu sub">Check the detected values, then save. Cancel to retake the photo.</p>' + (th ? '<img class="th" src="' + th + '" alt="">' : '') + (note ? '<p class="note' + (/failed|No values|Nothing|not read/i.test(note) ? ' err' : '') + '">' + esc(note) + '</p>' : '') + '<div id="fl"></div><div class="row"><button class="g" id="x">Cancel</button><button id="ok">Save</button></div>', 'md-review'), ins = {};
        const save = m.querySelector('#ok');
        FIELDS[kind].forEach(k => {
            const l = document.createElement('label'); l.textContent = LBL[k] || k.replace(/_/g, ' '); if (!NARROW.includes(k)) l.className = 'wide'; const i = document.createElement('input'); i.value = vals[k] ?? ''; i.readOnly = true;
            ins[k] = i; l.append(i);
            if (kind === 'cluster' && k === 'km') {
                if (!validOdometer(i.value)) {
                    save.disabled = true;
                    const error = document.createElement('small'); error.className = 'field-error';
                    error.textContent = 'Odometer reading is required. Cancel and retake the photo.';
                    l.append(error);
                }
            }
            m.querySelector('#fl').append(l)
        });
        m.querySelector('#x').onclick = () => { m.remove(); res(null) };
        m.querySelector('#ok').onclick = () => { const o = {}; for (const k in ins) o[k] = ins[k].value.trim(); m.remove(); res(o) }
    })
}
function reviewVisit(vals) {
    return new Promise(res => {
        const businesses = ['MAGNUS', 'MERCHX', 'M&D', 'ALIMS'];
        const priorBusiness = String(vals.business_name || '');
        const isKnownBusiness = businesses.some(b => b.toLowerCase() === priorBusiness.toLowerCase());
        const initialAreas = Array.isArray(vals.area) ? vals.area : vals.area ? [vals.area] : [];
        const areas = initialAreas.map(a => String(a).trim()).filter(Boolean);
        const m = modal('<h3>Business details</h3><p class="mu sub">Add a business visit to today’s log.</p><div class="visit-form">' +
            '<label for="visit-business">Business</label><select id="visit-business"><option value="">Select a business</option>' +
            businesses.map(b => '<option value="' + b + '">' + b + '</option>').join('') +
            '<option value="__other">Other</option></select>' +
            '<label class="other-business-label" for="visit-business-other" hidden>Business name</label><input id="visit-business-other" type="text" placeholder="Type business name" autocomplete="organization" hidden>' +
            '<label for="visit-area">Areas covered today</label><div class="area-entry"><input id="visit-area" type="text" placeholder="e.g. Thalangara" autocomplete="off"><button class="g area-add" id="area-add" type="button">Add</button></div>' +
            '<div class="area-tags" id="area-tags" aria-live="polite"></div><p class="visit-error" id="visit-error" role="alert" hidden></p>' +
            '<label for="visit-amount">Amount collected (₹)</label><input id="visit-amount" type="number" inputmode="decimal" min="0" step="any" placeholder="0">' +
            '</div><div class="row"><button class="g" id="x">Cancel</button><button id="ok">Save</button></div>', 'md-review md-visit');
        const business = m.querySelector('#visit-business'), other = m.querySelector('#visit-business-other');
        const otherLabel = m.querySelector('.other-business-label'), areaInput = m.querySelector('#visit-area');
        const tags = m.querySelector('#area-tags'), error = m.querySelector('#visit-error');
        business.value = priorBusiness ? isKnownBusiness ? businesses.find(b => b.toLowerCase() === priorBusiness.toLowerCase()) : '__other' : '';
        if (business.value === '__other') other.value = priorBusiness;
        const renderAreas = () => {
            tags.innerHTML = areas.map((area, index) => '<span class="area-tag">' + esc(area) +
                '<button type="button" aria-label="Remove ' + esc(area) + '" data-area-index="' + index + '">×</button></span>').join('');
            tags.querySelectorAll('[data-area-index]').forEach(button => {
                button.onclick = () => { areas.splice(Number(button.dataset.areaIndex), 1); renderAreas() };
            });
        };
        const addArea = () => {
            const area = areaInput.value.trim();
            if (!area) { areaInput.focus(); return }
            if (!areas.some(existing => existing.toLocaleLowerCase() === area.toLocaleLowerCase())) areas.push(area);
            areaInput.value = ''; error.hidden = true; renderAreas(); areaInput.focus();
        };
        const updateBusiness = () => {
            const showOther = business.value === '__other';
            other.hidden = !showOther; otherLabel.hidden = !showOther;
            if (showOther) other.focus();
        };
        business.onchange = updateBusiness;
        m.querySelector('#area-add').onclick = addArea;
        areaInput.onkeydown = event => {
            if (event.key === 'Enter') { event.preventDefault(); addArea() }
        };
        renderAreas();
        m.querySelector('#x').onclick = () => { m.remove(); res(null) };
        m.querySelector('#ok').onclick = () => {
            const businessName = business.value === '__other' ? other.value.trim() : business.value;
            if (!businessName) {
                error.textContent = business.value === '__other' ? 'Enter the business name.' : 'Select a business.';
                error.hidden = false; (business.value === '__other' ? other : business).focus(); return;
            }
            if (!areas.length) { error.textContent = 'Add at least one area.'; error.hidden = false; areaInput.focus(); return }
            const amount = m.querySelector('#visit-amount').value.trim();
            m.remove();
            res({ business_name: businessName, area: areas, amount_collected: amount });
        };
    })
}
async function sendEventPayload(p) {
    const r = await fetch('/api/events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) });
    return r.ok;
}
async function syncPendingEvents() {
    if (!navigator.onLine || !S.pending || !S.pending.length) return;
    const queue = S.pending.slice(), remaining = [];
    for (const item of queue) {
        try {
            const ok = await sendEventPayload(item);
            if (!ok) remaining.push(item);
        } catch (e) {
            remaining.push(item);
        }
    }
    const synced = S.pending.length - remaining.length;
    S.pending = remaining; keep();
    if (synced > 0) showToast('Synced ' + synced + ' offline event' + (synced > 1 ? 's' : '') + ' to server.');
}
function add(t, d, th) {
    const e = { t, at: new Date().toISOString(), d, th }; S.ev.push(e); keep();
    const payload = { run: S.run && S.run.id, t, at: e.at, d };
    if (!sample) {
        if (!navigator.onLine) {
            S.pending = S.pending || []; S.pending.push(payload); keep();
            showToast('Saved offline. Will sync when reconnected.');
        } else {
            sendEventPayload(payload).then(ok => {
                if (!ok) { S.pending = S.pending || []; S.pending.push(payload); keep() }
            }).catch(() => {
                S.pending = S.pending || []; S.pending.push(payload); keep();
            });
        }
    }
    render();
}
async function snap(kind, title, extra = {}) {
    const gp = kind === 'geo' ? gpsNow() : null; const b = await shoot(title); if (!b) return null; const gpsFinal = kind === 'geo' ? gpsNow(true).then(async f => { if (f.c) return f; const w = await gp; return w.c ? w : f }) : null; const capturedAt = new Date(), done = busy('Reading image…');
    const [d, th, g] = await Promise.all([extract(kind, b), thumb(b), gpsFinal]); done();
    const gps = (g && g.c) || '', gpsErr = (g && g.err) || ''; const v = Object.assign({}, d, extra); if (kind === 'geo') v.device_gps = gps; if (kind === 'geo' && !v.gps) v.gps = gps;
    const coordinates = gps || v.gps; let geoError = ''; if (kind === 'geo' && !coordinates) geoError = 'GPS failed: ' + (gpsErr || 'no position found.'); if (kind === 'geo' && coordinates) { const address = await reverseGeocode(coordinates); geoError = address._error || ''; for (const key of ['road', 'state']) if (!v[key] && address[key]) v[key] = address[key]; if (address.location) v.location = address.location; if (address.district) v.district = address.district; }
    if (kind === 'geo' && String(v.state || '').trim().toLowerCase() === 'kerala' && String(v.district || '').trim().toLowerCase() === 'ernad') v.district = 'Malappuram';
    if (kind === 'cluster' || kind === 'geo') {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        v.date = v.date || String(capturedAt.getDate()).padStart(2, '0') + '-' + months[capturedAt.getMonth()] + '-' + capturedAt.getFullYear();
        v.time = v.time || capturedAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    const err = d && d._error; if (d) delete d._error; const hasValues = FIELDS[kind].some(k => d && d[k] != null && String(d[k]).trim() !== ''); const note = kind === 'geo' ? 'Address lookup uses phone GPS via OpenStreetMap (© OpenStreetMap contributors).' + (geoError ? ' ' + geoError : '') : (err ? 'Reading failed: ' + err : (!hasValues ? 'No values returned. Server replied: ' + JSON.stringify(d) + ' (open /api/ping to check the server version)' : (kind === 'cluster' && !validOdometer(v.km) ? 'The odometer was not read. Cancel and retake the photo.' : '')));
    const o = await review(title, kind, v, URL.createObjectURL(b), note); return o && { o, th }
}
// ---- actions
async function start() {
    try { Notification.requestPermission() } catch (e) { }
    const r = await snap('cluster', 'Upload cluster image'); if (!r) return;
    S.run = { id: Date.now(), start: new Date().toISOString(), due: null, end: null }; add('start_km', r.o, r.th); await visit()
}
async function visit() { const o = await review('Business details', 'visit', {}); if (!o) return; add('visit', o); await loc('Capture location image') }
async function loc(t) {
    const r = await snap('geo', t || 'Upload current location image'); if (!r) return;
    S.run.due = Date.now() + 30 * 60000; S.run.notified = false; add('location', r.o, r.th)
}
function fuel() {
    const m = modal('<h3>Choose fuel type</h3><p class="mu sub">Pick what you are refuelling.</p><button class="fuel-option" id="p"><span class="fuel-icon">P</span><span><b>Petrol</b><small>Generator, ₹1000 preset</small></span><span class="fuel-arrow">›</span></button><button class="fuel-option" id="d"><span class="fuel-icon">D</span><span><b>Diesel</b><small>Vehicle, ₹1500 preset</small></span><span class="fuel-arrow">›</span></button><button class="g" id="x">Cancel</button>', 'md-choice');
    const go = async (type, preset) => {
        m.remove(); const r = await snap('fuel', 'Upload fuel bill', {}); if (!r) return;
        const rc = r.o.receipt_no; if (!rc) return alert('Receipt/voucher number is required.');
        if (S.ev.some(e => e.t === 'fuel' && e.d.receipt_no === rc)) return alert('Duplicate bill: receipt ' + rc + ' was already uploaded.');
        if (!r.o.product) r.o.product = type.split(' - ')[0];
        r.o.fuel_for = type; r.o.preset = preset; r.o.flag = Number(r.o.amount) !== preset ? 'Amount differs from ₹' + preset : '';
        add('fuel', r.o, r.th)
    };
    m.querySelector('#p').onclick = () => go('Petrol - Generator', 1000); m.querySelector('#d').onclick = () => go('Diesel - Vehicle', 1500); m.querySelector('#x').onclick = () => m.remove()
}
async function stop() {
    if (!confirm('Stop today’s run?')) return; const r = await snap('cluster', 'Upload cluster image'); if (!r) return;
    S.run.end = new Date().toISOString(); add('stop_km', r.o, r.th)
}
function reset() { if (confirm('Clear today’s data from this device? Export CSV first.')) { S = { run: null, ev: [] }; keep(); render() } }
async function csv() {
    const rows = [['type', 'recorded_at', 'details']].concat(S.ev.map(e => [e.t, e.at, JSON.stringify(e.d)]));
    const data = rows.map(r => r.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\n'), name = 'truck-' + new Date().toISOString().slice(0, 10) + '.csv';
    try { const d = window.claude && await claude.use('downloads'); if (d) return await d.save({ filename: name, data }) } catch (e) { }
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([data], { type: 'text/csv' })); a.download = name; a.click()
}
// ---- render
const N = { start_km: 'Run started', visit: 'Business visit', location: 'Location photo', fuel: 'Fuel bill', stop_km: 'Run stopped' };
const ev = t => S.ev.filter(e => e.t === t);
const IC = {
    camera: '<path d="M4 8h3l1.5-2h7L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>', pin: '<path d="M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    store: '<path d="M3 9l2-5h14l2 5"/><path d="M4 9v11h16V9"/><path d="M9 20v-6h6v6"/>', fuel: '<path d="M5 20V5a1 1 0 011-1h7a1 1 0 011 1v15"/><path d="M4 20h11"/><path d="M14 9h2.5A1.5 1.5 0 0118 10.5V16a1.5 1.5 0 003 0V8l-3-3"/><path d="M7.5 8h4"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>', chev: '<path d="M9 6l6 6-6 6"/>', play: '<path d="M8 5v14l11-7z"/>', download: '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/>',
    again: '<path d="M20 12a8 8 0 11-2.3-5.7"/><path d="M20 4v5h-5"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>'
};
const ico = (n, c = '') => '<svg class="ico ' + c + '" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + IC[n] + '</svg>';
const km = v => v !== '' && v != null && Number.isFinite(+v) ? (+v).toLocaleString('en-IN') : '—', inr = v => '₹' + (+v || 0).toLocaleString('en-IN');
const odo = d => [['Odometer', d.km && km(d.km) + ' km'], ['Read at', [d.date, d.time].filter(Boolean).join(', ')]];
const SUM = {
    start_km: odo, stop_km: odo,
    visit: d => [['Business', d.business_name], ['Area', Array.isArray(d.area) ? d.area.join(', ') : d.area], ['Collected', d.amount_collected && inr(d.amount_collected)]],
    location: d => [['Place', [d.road, d.location].filter(Boolean).join(', ')], ['Region', [d.district, d.state].filter(Boolean).join(', ')], ['GPS', d.gps]],
    fuel: d => [['Fuel', d.fuel_for || d.product], ['Amount', d.amount && inr(d.amount)], ['Volume', d.volume && d.volume + ' L'], ['Receipt', d.receipt_no], ['Check', d.flag]]
};
const rows = e => (SUM[e.t] ? SUM[e.t](e.d) : []).filter(([, v]) => v).map(([k, v]) => '<span><em>' + k + '</em><b>' + esc(v) + '</b></span>').join('').replace(/<b>/g, '<b style="font-weight:600">');
function render() { try { draw() } catch (e) { console.error(e); const A = $('#app'); if (A) A.innerHTML = '<div class="note err"><b>Display error:</b> ' + esc(e.message) + '. Press F12, open Console, and send the red message.</div>' } }
function draw() {
    if (S.run && !ev('start_km')[0]) { S.run = null; keep() }
    const r = S.run, A = $('#app'), done = !!(r && r.end);
    document.querySelectorAll && document.querySelectorAll('.topbar').forEach(x => x.remove());
    if (!$('#status') && document.querySelector('main')) { const h = document.createElement('header'); h.className = 'top'; h.innerHTML = '<a class="brand" href="/" aria-label="Ad Vandi run log home"><img class="brand-logo" src="/static/ad-vandi-logo.png?v=1" alt="Ad Vandi run log"></a><div id="status"></div>'; document.querySelector('main').prepend(h) }
    $('#status').innerHTML = '<span class="chip' + (r && !done ? ' live' : '') + '"><i></i>' + (!r ? 'Not started' : done ? 'Run closed' : 'Run in progress') + '</span>';
    if (!r) {
        const today = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: '2-digit', month: 'short' }).format(new Date()).replace(',', '').toUpperCase();
        A.innerHTML = '<section class="hero"><div class="hero-copy"><div class="eyebrow">TODAY · ' + today + '</div><h2>Start today’s <em>run</em></h2><p>Photograph the odometer to open the log. We then ask for a location photo every 30 minutes and keep visits and fuel bills in one timeline.</p><div class="hero-actions"><button class="btn start-action" id="s">' + ico('play') + 'Start run</button><span class="start-meta">' + ico('clock') + 'Takes 10 seconds</span></div></div>' +
            '<div class="idle-led"><div class="idle-led-head"><span>ODOMETER</span><span class="awaiting"><i></i>AWAITING PHOTO</span></div><div class="odo-digits" aria-label="Odometer awaiting start photo"><span>0</span><span>0</span><span>0</span><span>0</span></div><div class="idle-wait">' + ico('camera') + 'Waiting for the start photo</div><div class="idle-stats"><div><b>0 km</b><small>Distance</small></div><div><b>0</b><small>Visits</small></div><div><b>₹0</b><small>Fuel</small></div></div></div></section>' +
            '<section class="steps" aria-label="How the run log works"><article class="step-card"><span class="step-number">01</span><span class="step-icon">' + ico('camera') + '</span><b>Snap the odometer</b><p>One photo opens today’s log.</p></article><article class="step-card"><span class="step-number">02</span><span class="step-icon">' + ico('pin') + '</span><b>Location check-ins</b><p>A gentle reminder every 30 minutes.</p></article><article class="step-card"><span class="step-number">03</span><span class="step-icon">' + ico('receipt') + '</span><b>Visits &amp; fuel bills</b><p>Everything in a single timeline.</p></article></section>' + (S.ev.length ? '<button class="btn ghost old-data" id="rs">Clear old data</button>' : '');
        $('#s').onclick = start; $('#rs') && ($('#rs').onclick = reset); return
    }
    const sk = +ev('start_km')[0].d.km, ek = ev('stop_km')[0] ? +ev('stop_km')[0].d.km : null, sum = (t, k) => ev(t).reduce((a, e) => a + (+e.d[k] || 0), 0);
    const WIN = 30 * 60000, left = r.due ? r.due - Date.now() : null, over = !done && r.due && left <= 0, min = r.due ? Math.max(0, Math.ceil(left / 60000)) : 0, p = r.due ? Math.min(100, Math.max(0, (1 - left / WIN) * 100)) : 0;
    const ring = done ? '' : '<div class="ring' + (over ? ' is-over' : '') + '" style="--p:' + (over ? 100 : p.toFixed(1)) + '" role="img" aria-label="' + (over ? 'Location photo due now' : r.due ? 'Next location photo in ' + min + ' minutes' : 'No location photo yet') + '"><span><b>' + (over ? 'Now' : r.due ? min : '—') + '</b><small>' + (r.due && !over ? 'min to photo' : 'photo due') + '</small></span></div>';
    const panel = '<section class="led"><div class="led-main"><div><div class="readout xl">' + (done ? km(ek - sk) : km(sk)) + '</div><div class="readout-label">' + (done ? 'Distance driven (km)' : 'Start odometer (km)') + '</div></div>' + ring + '</div>' +
        '<div class="led-row"><div><div class="readout">' + inr(sum('visit', 'amount_collected')) + '</div><div class="readout-label">Collected</div></div><div><div class="readout">' + inr(sum('fuel', 'amount')) + '</div><div class="readout-label">Fuel spent</div></div></div></section>';
    const act = (id, ic, t, sm, cls) => '<button class="act' + (cls || '') + '" id="' + id + '">' + ico(ic) + '<span><strong>' + t + '</strong><small>' + sm + '</small></span>' + ico('chev', 'chev') + '</button>';
    const banner = over ? '<div class="due-banner" role="alert"><div><b>Location photo due</b><span>30 minutes have passed since the last one.</span></div><button class="btn" id="l2">Upload now</button></div>' : '';
    const controls = done ? '<div class="acts"><button class="btn lg" id="e">' + ico('download') + 'Export CSV</button><button class="btn ghost" id="rs">' + ico('again') + 'Start new day</button></div>' :
        '<div class="acts">' + act('l', 'pin', 'Upload current location image', 'Geo-tagged camera photo', over ? ' is-due' : '') + act('v', 'store', 'New business visit', 'Business, area and amount collected') + act('f', 'fuel', 'Upload fuel bill', 'Petrol for the generator or diesel for the vehicle') + '</div>' +
        '<button class="btn quiet" id="st">' + ico('stop') + 'Stop run</button><button class="link" id="dm">Demo: skip the 30-minute wait</button>';
    const tl = '<section class="tlwrap"><h3>Today’s timeline <span class="count">' + S.ev.length + '</span></h3><ol class="tl">' + S.ev.slice().reverse().map(e => '<li data-t="' + e.t + '">' + (e.th ? '<img src="' + e.th + '" alt="">' : '') + '<div class="tl-body"><div class="tl-head"><strong>' + N[e.t] + '</strong><time>' + new Date(e.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + '</time></div><div class="kv">' + rows(e) + '</div></div></li>').join('') + '</ol></section>';
    A.innerHTML = '<div class="grid"><div>' + banner + panel + controls + '</div>' + tl + '</div>';
    const b = (i, f) => $('#' + i) && ($('#' + i).onclick = f); b('l', () => loc()); b('l2', () => loc()); b('v', visit); b('f', fuel); b('st', stop); b('e', csv); b('rs', reset);
    b('dm', () => { r.due = Date.now() - 1; r.notified = false; keep(); render() })
}
setInterval(() => {
    const r = S.run; if (r && !r.end && r.due && Date.now() > r.due && !r.notified) {
        r.notified = true; keep();
        try { new Notification('UPLOAD CURRENT LOCATION IMAGE', { body: '30 minutes passed', requireInteraction: true, vibrate: [600, 200, 600, 200, 600] }); navigator.vibrate && navigator.vibrate([300, 150, 300]) } catch (e) { } render()
    }
    else if (r && !r.end && !document.querySelector('.md')) render()
}, 5000);
render();
// ---- alert sound for the 30-minute location photo (uses static/alert.mp3)
const ALERT_GAP_MS = 100; // 0.1 second pause between repeats
const SND = new Audio('/static/alert.mp3'); SND.preload = 'auto'; SND.volume = 1;
let unlocked = false, ringing = false, forced = false; // forced = alarm started by a server push
// stop pull-to-refresh: scrolling up at the top reloads the page and silences the alert
(() => { const s = document.createElement('style'); s.textContent = 'html,body{overscroll-behavior-y:contain}'; document.head.appendChild(s) })();
function audioAllowed() { return navigator.userActivation ? navigator.userActivation.hasBeenActive : unlocked }
function unlockAudio() { // a real tap on the page is needed once; muted play does NOT prove the browser allowed sound
    if (unlocked) return;
    SND.muted = false; SND.volume = shouldRing() ? 1 : 0; // silent unlock when nothing is due
    SND.play().then(() => {
        unlocked = true; hideEnableBar();
        if (shouldRing()) { ringing = true; SND.volume = 1 } else { SND.pause(); SND.currentTime = 0; SND.volume = 1 }
    }).catch(() => { SND.volume = 1 });
}
['pointerup', 'touchend', 'click', 'keydown'].forEach(n => window.addEventListener(n, unlockAudio, { passive: true, capture: true }));
// "Enable sound" bar: shown whenever the browser is still blocking the sound, so one tap on it fixes everything
function hideEnableBar() { const b = document.getElementById('soundEnableBar'); if (b) b.remove() }
function showEnableBar() {
    if (unlocked || document.getElementById('soundEnableBar') || !document.body) return;
    const b = document.createElement('button'); b.id = 'soundEnableBar'; b.textContent = '🔊 Tap here to enable alert sound';
    b.style.cssText = 'position:fixed;left:12px;right:12px;top:12px;z-index:99998;padding:14px;font-size:16px;font-weight:700;border:0;border-radius:12px;background:#e8ca78;color:#15120c';
    b.onclick = () => { unlockAudio(); setTimeout(() => { if (!unlocked) { SND.play().then(() => { unlocked = true; hideEnableBar(); setTimeout(() => { if (!shouldRing()) { SND.pause(); SND.currentTime = 0 } }, 400) }).catch(() => { }) } }, 0) };
    document.body.appendChild(b);
}
setTimeout(() => { if (!audioAllowed()) showEnableBar() }, 1500);
function isDue() { const r = S.run; return !!(r && !r.end && r.due && Date.now() > r.due && !document.querySelector('.md')) }
function shouldRing() { return forced || isDue() }
function ring() {
    if (!shouldRing()) { ringing = false; SND.pause(); return }
    ringing = true; SND.currentTime = 0;
    try { navigator.vibrate && navigator.vibrate([600, 200, 600]) } catch (e) { }
    SND.play().catch(() => { ringing = false; showEnableBar() });
}
SND.addEventListener('ended', () => setTimeout(ring, ALERT_GAP_MS));
// if the browser pauses the sound by itself (scroll, focus change) while it should be ringing, start it again
SND.addEventListener('pause', () => { if (ringing && !SND.ended && shouldRing()) SND.play().catch(() => { }) });
document.addEventListener('visibilitychange', () => { if (!document.hidden && !ringing && shouldRing()) ring() });
// plays the sound again and again (0.1 s gap) from the moment 30 minutes are up until the next location photo is uploaded
setInterval(() => { if (!ringing && shouldRing()) ring() }, 1000);

// STOP button for alarms started by a server push (the 30-minute alert stops itself when the photo is uploaded)
function stopForced() { forced = false; ringing = false; SND.pause(); SND.currentTime = 0; const b = document.getElementById('alarmStopBar'); if (b) b.style.display = 'none' }
function showStopBar() {
    let b = document.getElementById('alarmStopBar');
    if (!b) {
        b = document.createElement('button'); b.id = 'alarmStopBar'; b.textContent = '🔔 STOP ALARM'; b.onclick = stopForced;
        b.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:99999;padding:16px;font-size:18px;font-weight:700;border:0;border-radius:12px;background:#c62828;color:#fff';
        document.body.appendChild(b);
    }
    b.style.display = 'block';
}
if ('serviceWorker' in navigator) navigator.serviceWorker.addEventListener('message', e => {
    if (e.data && e.data.type === 'ALARM') { forced = true; showStopBar(); if (!ringing) ring() }
});

// ---- PWA Lifecycle, Offline & Install Handlers
function updateNetworkBadge() {
    const chip = $('#offline-chip');
    if (chip) chip.hidden = navigator.onLine;
    if (navigator.onLine) syncPendingEvents();
    else showToast('Offline mode active. Logs are saved locally.');
}
window.addEventListener('online', updateNetworkBadge);
window.addEventListener('offline', updateNetworkBadge);
updateNetworkBadge();

// PWA Install prompt handling
let deferredInstall = null;
window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    deferredInstall = e;
    const btn = $('#install-btn');
    if (btn) {
        btn.hidden = false;
        btn.onclick = async () => {
            if (!deferredInstall) return;
            btn.hidden = true;
            deferredInstall.prompt();
            const res = await deferredInstall.userChoice;
            if (res && res.outcome === 'accepted') showToast('Installing Ad Vandi...');
            deferredInstall = null;
        };
    }
});

window.addEventListener('appinstalled', () => {
    deferredInstall = null;
    const btn = $('#install-btn');
    if (btn) btn.hidden = true;
    showToast('Ad Vandi installed successfully!');
});

// Service Worker Registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { scope: '/' })
            .then(reg => {
                reg.addEventListener('updatefound', () => {
                    const w = reg.installing;
                    w && w.addEventListener('statechange', () => {
                        if (w.state === 'installed' && navigator.serviceWorker.controller) {
                            showToast('Update available. Refresh to load new version.');
                        }
                    });
                });
            })
            .catch(err => console.warn('[PWA] SW register:', err));
    });
}

// App Shortcut routing (e.g. /?action=start)
(() => {
    const p = new URLSearchParams(window.location.search);
    const act = p.get('action');
    if (act) {
        window.history.replaceState({}, document.title, window.location.pathname);
        setTimeout(() => {
            if (act === 'start' && !S.run) start();
            else if (act === 'location' && S.run && !S.run.end) loc();
            else if (act === 'visit' && S.run && !S.run.end) visit();
            else if (act === 'fuel' && S.run && !S.run.end) fuel();
        }, 400);
    }
})();