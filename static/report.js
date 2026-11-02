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
const dateFromKey = key => {
    const [year, month, day] = key.split('-').map(Number);
    return new Date(year, month - 1, day);
};
const dateKey = date => {
    const p = n => String(n).padStart(2, '0');
    return date.getFullYear() + '-' + p(date.getMonth() + 1) + '-' + p(date.getDate());
};
const addDays = (date, days) => {
    const result = new Date(date);
    result.setDate(result.getDate() + days);
    return result;
};
const fmtDateKey = key => dateFromKey(key).toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric'
});
const hasDateFilter = () => Boolean(dateStart && dateEnd);
const isDateInRange = date => !hasDateFilter() || (date >= dateStart && date <= dateEnd);
const labels = {
    start_km: 'Odometer — start',
    stop_km: 'Odometer — end',
    location: 'Location photo',
    fuel: 'Fuel bill',
    visit: 'Business visit'
};
const folders = [
    { id: 'all', label: 'All records' },
    { id: 'odo', label: 'Odometer' },
    { id: 'fuel', label: 'Fuel bills' },
    { id: 'petrol', label: 'Petrol', child: true },
    { id: 'diesel', label: 'Diesel', child: true },
    { id: 'location', label: 'Location' },
    { id: 'visit', label: 'Business visits' }
];

const folderIcons = {
    all: '<path d="M4 5h16v14H4z"/><path d="M8 9h8M8 13h8M8 17h5"/>',
    odo: '<circle cx="12" cy="12" r="8"/><path d="M12 12l4-4M8 16h8"/>',
    fuel: '<path d="M5 21V4h9v17M4 21h12"/><path d="M7 7h5v4H7z"/><path d="M14 8h2l3 3v6a2 2 0 0 0 4 0v-5l-3-3"/>',
    location: '<path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    visit: '<path d="M3 10h18l-2-6H5z"/><path d="M5 10v10h14V10M9 20v-6h6v6"/><path d="M3 10a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0"/>'
};
const folderIcon = folder => folder.child
    ? '·'
    : '<svg class="rep-folder-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      folderIcons[folder.id] + '</svg>';

let REPORTS = [], RECORDS = [], selectedFolder = 'all', dateStart = '', dateEnd = '';
let draftStart = '', draftEnd = '', calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let imageViewer, imageViewerImage, imageViewerCanvas, imageZoom = 1, imageFit = 1, imageTrigger;
let imageViewerPortrait = false;

function viewerImageSize() {
    const sourcePortrait = imageViewerImage.naturalHeight > imageViewerImage.naturalWidth;
    const rotated = sourcePortrait !== imageViewerPortrait;
    return {
        rotated,
        width: rotated ? imageViewerImage.naturalHeight : imageViewerImage.naturalWidth,
        height: rotated ? imageViewerImage.naturalWidth : imageViewerImage.naturalHeight,
        rotation: imageViewerPortrait ? 'rotate(90deg)' : 'rotate(-90deg)'
    };
}

function setImageZoom(value) {
    if (!imageViewerImage.naturalWidth) return;
    imageZoom = Math.max(0.5, Math.min(4, value));
    const size = viewerImageSize();
    const width = size.width * imageFit * imageZoom;
    const height = size.height * imageFit * imageZoom;
    const viewport = imageViewerCanvas.parentElement;
    imageViewerCanvas.style.width = Math.max(viewport.clientWidth, width) + 'px';
    imageViewerCanvas.style.height = Math.max(viewport.clientHeight, height) + 'px';
    imageViewerImage.style.width = (size.rotated ? height : width) + 'px';
    imageViewerImage.style.height = (size.rotated ? width : height) + 'px';
    imageViewerImage.style.transform = size.rotated ? size.rotation : '';
    $('#rep-image-zoom-level').textContent = Math.round(imageZoom * 100) + '%';
}

function fitImageViewer() {
    if (!imageViewerImage.naturalWidth) return;
    const viewport = imageViewerImage.parentElement;
    const size = viewerImageSize();
    imageFit = Math.min(
        viewport.clientWidth / size.width,
        viewport.clientHeight / size.height,
        1
    );
    setImageZoom(imageZoom);
}

function closeImageViewer() {
    if (!imageViewer || imageViewer.hidden) return;
    imageViewer.hidden = true;
    document.body.classList.remove('rep-image-viewer-open');
    imageViewerImage.removeAttribute('src');
    if (imageTrigger) imageTrigger.focus();
}

function fitImageThumbnail(image) {
    if (!image.complete || !image.naturalWidth) return;
    const preview = image.closest('.rep-image-preview');
    if (!preview) return;
    const targetPortrait = image.closest('.rep-image-card').dataset.imageOrientation === 'portrait';
    const sourcePortrait = image.naturalHeight > image.naturalWidth;
    const rotated = sourcePortrait !== targetPortrait;
    if (!rotated) {
        image.classList.remove('rep-orientation-rotated');
        image.style.removeProperty('width');
        image.style.removeProperty('height');
        image.style.removeProperty('transform');
        return;
    }

    const bounds = preview.getBoundingClientRect();
    const scale = Math.min(
        bounds.width / image.naturalHeight,
        bounds.height / image.naturalWidth
    );
    image.classList.add('rep-orientation-rotated');
    image.style.width = image.naturalWidth * scale + 'px';
    image.style.height = image.naturalHeight * scale + 'px';
    image.style.transform = 'translate(-50%, -50%) ' +
        (targetPortrait ? 'rotate(90deg)' : 'rotate(-90deg)');
}

function fitImageThumbnails() {
    document.querySelectorAll('.rep-image-card img').forEach(image => {
        if (image.complete) {
            fitImageThumbnail(image);
        } else if (!image.dataset.orientationListener) {
            image.dataset.orientationListener = 'pending';
            image.addEventListener('load', () => {
                delete image.dataset.orientationListener;
                fitImageThumbnail(image);
            }, { once: true });
        }
    });
}

function openImageViewer(url, title, trigger) {
    imageTrigger = trigger;
    imageViewerPortrait = trigger.dataset.imageOrientation === 'portrait';
    imageZoom = 0.5;
    imageViewer.querySelector('.rep-image-viewer-title').textContent = title;
    imageViewerImage.alt = title;
    imageViewerImage.onload = () => {
        fitImageViewer();
        imageViewer.querySelector('.rep-image-viewer-viewport').scrollTo(0, 0);
    };
    imageViewerImage.onerror = () => {
        imageViewer.querySelector('.rep-image-viewer-title').textContent = 'Could not load image';
    };
    imageViewerImage.src = url;
    imageViewer.hidden = false;
    document.body.classList.add('rep-image-viewer-open');
    imageViewer.querySelector('[data-image-viewer-close]').focus();
}

function setupImageViewer() {
    imageViewer = document.createElement('div');
    imageViewer.className = 'rep-image-viewer';
    imageViewer.id = 'rep-image-viewer';
    imageViewer.hidden = true;
    imageViewer.setAttribute('role', 'dialog');
    imageViewer.setAttribute('aria-modal', 'true');
    imageViewer.setAttribute('aria-label', 'Image viewer');
    imageViewer.innerHTML = '<div class="rep-image-viewer-panel">' +
        '<header class="rep-image-viewer-header"><b class="rep-image-viewer-title"></b>' +
        '<button type="button" class="rep-image-viewer-close" data-image-viewer-close aria-label="Close image viewer">×</button></header>' +
        '<div class="rep-image-viewer-viewport"><div class="rep-image-viewer-canvas">' +
        '<img class="rep-image-viewer-image" alt=""></div></div>' +
        '<div class="rep-image-viewer-controls"><button type="button" data-image-zoom="-1" aria-label="Zoom out">−</button>' +
        '<span id="rep-image-zoom-level" aria-live="polite">100%</span>' +
        '<button type="button" data-image-zoom="1" aria-label="Zoom in">+</button>' +
        '<button type="button" data-image-zoom-reset>Fit</button></div></div>';
    document.body.append(imageViewer);
    imageViewerImage = imageViewer.querySelector('.rep-image-viewer-image');
    imageViewerCanvas = imageViewer.querySelector('.rep-image-viewer-canvas');

    imageViewer.addEventListener('click', event => {
        if (event.target === imageViewer || event.target.closest('[data-image-viewer-close]')) {
            closeImageViewer();
            return;
        }
        const zoomButton = event.target.closest('[data-image-zoom]');
        if (zoomButton) {
            setImageZoom(imageZoom * (Number(zoomButton.dataset.imageZoom) > 0 ? 1.25 : 0.8));
        } else if (event.target.closest('[data-image-zoom-reset]')) {
            imageZoom = 1;
            fitImageViewer();
            imageViewer.querySelector('.rep-image-viewer-viewport').scrollTo(0, 0);
        }
    });
    imageViewer.querySelector('.rep-image-viewer-viewport').addEventListener('wheel', event => {
        event.preventDefault();
        setImageZoom(imageZoom * (event.deltaY < 0 ? 1.15 : 0.87));
    }, { passive: false });
    document.addEventListener('keydown', event => {
        if (imageViewer.hidden) return;
        if (event.key === 'Escape') closeImageViewer();
        if (event.key === '+' || event.key === '=') setImageZoom(imageZoom * 1.25);
        if (event.key === '-') setImageZoom(imageZoom * 0.8);
    });
    window.addEventListener('resize', fitImageViewer);
    window.addEventListener('resize', fitImageThumbnails);
    $('#app').addEventListener('click', event => {
        const trigger = event.target.closest('[data-image-url]');
        if (trigger) openImageViewer(trigger.dataset.imageUrl, trigger.dataset.imageTitle, trigger);
    });
}

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

function renderCalendarMonth(year, month) {
    const first = new Date(year, month, 1);
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const offset = first.getDay();
    const cells = [];
    for (let i = 0; i < offset; i++) cells.push('<span class="rep-calendar-empty"></span>');
    for (let day = 1; day <= daysInMonth; day++) {
        const key = dateKey(new Date(year, month, day));
        const selected = key === draftStart || key === draftEnd;
        const inRange = draftStart && draftEnd && key > draftStart && key < draftEnd;
        cells.push('<button type="button" class="rep-calendar-day' + (selected ? ' selected' : '') +
            (inRange ? ' in-range' : '') + '" data-calendar-date="' + key + '" aria-pressed="' +
            Boolean(selected) + '">' + day + '</button>');
    }
    while (cells.length % 7) cells.push('<span class="rep-calendar-empty"></span>');
    const weekdays = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
        .map(day => '<span class="rep-calendar-weekday">' + day + '</span>').join('');
    const monthName = first.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    return '<div class="rep-calendar-month"><h3>' + monthName + '</h3><div class="rep-calendar-grid">' +
        weekdays + cells.join('') + '</div></div>';
}

function renderDateCalendars() {
    const secondMonth = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 1);
    $('#rep-date-calendars').innerHTML =
        renderCalendarMonth(calendarMonth.getFullYear(), calendarMonth.getMonth()) +
        renderCalendarMonth(secondMonth.getFullYear(), secondMonth.getMonth());
    const rangeText = draftStart && draftEnd
        ? fmtDateKey(draftStart) + ' – ' + fmtDateKey(draftEnd)
        : draftStart ? 'Select an end date' : 'Pick a start and an end date';
    $('#rep-date-selection').textContent = rangeText;
    $('#rep-date-apply').disabled = !(draftStart && draftEnd);
}

function setDateRange(start, end) {
    dateStart = start;
    dateEnd = end;
    draw();
}

function applyPreset(preset) {
    const today = dateFromKey(todayStr());
    let start = '', end = '';
    if (preset === 'today') start = end = dateKey(today);
    if (preset === 'yesterday') start = end = dateKey(addDays(today, -1));
    if (preset === 'last7') {
        start = dateKey(addDays(today, -6));
        end = dateKey(today);
    }
    if (preset === 'last30') {
        start = dateKey(addDays(today, -29));
        end = dateKey(today);
    }
    if (preset === 'thisMonth') {
        start = dateKey(new Date(today.getFullYear(), today.getMonth(), 1));
        end = dateKey(today);
    }
    if (preset === 'lastMonth') {
        start = dateKey(new Date(today.getFullYear(), today.getMonth() - 1, 1));
        end = dateKey(new Date(today.getFullYear(), today.getMonth(), 0));
    }
    setDateRange(start, end);
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
        if (!isDateInRange(recordDate(record))) return false;
        const category = categoryOf(record);
        if (selectedFolder === 'all') return true;
        if (selectedFolder === 'odo') return category === 'odo';
        if (selectedFolder === 'fuel') return ['petrol', 'diesel'].includes(category);
        return category === selectedFolder;
    }).sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')));
}

function folderCount(folderId, records, runCount) {
    const images = records.filter(record => record.has_image);
    if (folderId === 'all') return runCount;
    if (folderId === 'odo') return images.filter(record => categoryOf(record) === 'odo').length;
    if (folderId === 'fuel') return images.filter(record => ['petrol', 'diesel'].includes(categoryOf(record))).length;
    if (folderId === 'visit') return records.filter(record => categoryOf(record) === 'visit').length;
    return images.filter(record => categoryOf(record) === folderId).length;
}

function renderSidebar(records) {
    const runCount = REPORTS.filter(report => isDateInRange(reportDate(report))).length;
    return '<aside class="rep-sidebar" id="report-folders" aria-label="Record folders">' +
        '<div class="rep-sidebar-title">FOLDERS</div>' +
        folders.map(folder => {
            const count = folderCount(folder.id, records, runCount);
            return '<button class="rep-folder' + (folder.child ? ' child' : '') +
                (selectedFolder === folder.id ? ' active' : '') + '" data-folder="' + folder.id + '"' +
                (folder.id === 'fuel' ? ' aria-label="All fuel bills"' : '') + '>' +
                '<span class="rep-folder-icon">' + folderIcon(folder) + '</span><span class="rep-folder-name">' +
                esc(folder.label) + '</span><span class="rep-folder-count">' + count + '</span></button>';
        }).join('') +
        '<a class="rep-back-link" href="/">← Back to run log</a></aside>';
}

function renderToolbar(imageCount = null) {
    const dateLabel = hasDateFilter()
        ? (dateStart === dateEnd ? fmtDateKey(dateStart) : fmtDateKey(dateStart) + ' – ' + fmtDateKey(dateEnd))
        : 'All Time';
    const headingDate = hasDateFilter()
        ? 'Records for ' + (dateStart === dateEnd ? fmtDateKey(dateStart) : fmtDateKey(dateStart) + ' – ' + fmtDateKey(dateEnd))
        : 'Full history from the database';
    return '<div class="rep-toolbar"><div class="rep-toolbar-heading"><h1>' +
        esc((folders.find(folder => folder.id === selectedFolder) || folders[0]).label) +
        '</h1><p class="mu">' + esc(headingDate) +
        '</p></div>' + (imageCount === null ? '' :
        '<div class="rep-image-toolbar-title"><h2>Images</h2><span class="rep-section-count">' + imageCount + '</span></div>') +
        '<div class="rep-toolbar-actions"><span class="rep-date-label">Date</span><button class="rep-date-trigger" id="rep-date-trigger" type="button" ' +
        'aria-haspopup="dialog" aria-expanded="false">' + esc(dateLabel) + '<span aria-hidden="true">▦</span></button></div></div>' +
        '<div class="rep-date-picker-backdrop" id="rep-date-picker" hidden><section class="rep-date-picker" role="dialog" ' +
        'aria-modal="true" aria-label="Filter records by date"><nav class="rep-date-presets" aria-label="Date range presets">' +
        '<button type="button" data-date-preset="any">All Time</button>' +
        '<button type="button" data-date-preset="today">Today</button>' +
        '<button type="button" data-date-preset="yesterday">Yesterday</button>' +
        '<button type="button" data-date-preset="last7">Last 7 days</button>' +
        '<button type="button" data-date-preset="last30">Last 30 days</button>' +
        '<button type="button" data-date-preset="thisMonth">This month</button>' +
        '<button type="button" data-date-preset="lastMonth">Last month</button>' +
        '<button type="button" data-date-preset="custom">Custom range</button></nav>' +
        '<div class="rep-date-picker-main"><div class="rep-date-calendar-nav">' +
        '<button type="button" data-calendar-nav="-1" aria-label="Previous month">‹</button>' +
        '<div class="rep-date-calendars" id="rep-date-calendars"></div>' +
        '<button type="button" data-calendar-nav="1" aria-label="Next month">›</button></div>' +
        '<footer class="rep-date-picker-footer"><span id="rep-date-selection" aria-live="polite"></span>' +
        '<div><button type="button" class="g" data-date-cancel>Cancel</button>' +
        '<button type="button" data-date-apply id="rep-date-apply" disabled>Apply</button></div></footer></div></section></div>';
}

function renderImages(records) {
    const images = records.filter(record => record.has_image);
    const cards = images.map(record => {
        const imageUrl = '/report/image/' + encodeURIComponent(record.id) + '?v=2';
        const fuel = record.data.fuel_for || record.data.product;
        const title = record.type === 'fuel' ? (fuel || 'Fuel bill') :
            (labels[record.type] || 'Uploaded image');
        const time = record.at && !isNaN(new Date(record.at))
            ? new Date(record.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
            : 'Time unavailable';
        const orientation = record.type === 'fuel' ? 'portrait' : 'landscape';
        return '<button class="rep-image-card" type="button" data-image-url="' + imageUrl +
            '" data-image-title="' + esc(title) + '" data-image-orientation="' + orientation +
            '" aria-label="View ' + esc(title) + '">' +
            '<div class="rep-image-preview"><img src="' + imageUrl + '" alt="' + esc(title) + '" loading="lazy"></div>' +
            '<span><b>' + esc(title) + '</b><small>' + esc(fmtDate(recordDate(record))) + ' · ' +
            esc(time) + '</small></span></button>';
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
            ? '<button class="rep-record-image" type="button" data-image-url="/report/image/' +
              encodeURIComponent(record.id) + '?v=2" data-image-orientation="' +
              (record.type === 'fuel' ? 'portrait' : 'landscape') + '" data-image-title="' +
              esc(labels[record.type] || 'Uploaded image') + '">Open image</button>'
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
    const runs = REPORTS.filter(report => isDateInRange(reportDate(report)));
    const sum = key => runs.reduce((total, report) => total + (+report[key] || 0), 0);
    return '<section class="rep-summary">' +
        '<div class="rep-card"><b>' + runs.length + '</b><span>Runs</span></div>' +
        '<div class="rep-card"><b>' + km(runs.reduce((total, report) => total + (report.distance_km || 0), 0)) +
        '</b><span>Total distance (km)</span></div>' +
        '<div class="rep-card"><b>' + inr(sum('collected_amount')) + '</b><span>Total collected</span></div>' +
        '<div class="rep-card"><b>' + inr(sum('petrol_amount') + sum('diesel_amount')) +
        '</b><span>Total fuel bills</span></div>' +
        '<div class="rep-card"><b>' + inr(sum('balance_amount')) + '</b><span>Balance</span></div></section>';
}

function renderRunSummary() {
    if (selectedFolder !== 'all') return '';
    const runs = REPORTS.filter(report => isDateInRange(reportDate(report)));
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
    const rows = REPORTS.filter(report => isDateInRange(reportDate(report)));
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
    const datedRecords = RECORDS.filter(record => isDateInRange(recordDate(record)));
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
    fitImageThumbnails();
    const header = document.querySelector('.report-main>.top');
    header.querySelector('.rep-toolbar-heading')?.remove();
    const pageHeading = document.querySelector('.rep-toolbar-heading');
    header.appendChild(pageHeading);
    const folderToggle = header.querySelector('.rep-folder-toggle');
    const closeFolderMenu = () => {
        document.body.classList.remove('report-folders-open');
        folderToggle.setAttribute('aria-expanded', 'false');
        folderToggle.setAttribute('aria-label', 'Open folders');
    };
    folderToggle.onclick = () => {
        const isOpen = document.body.classList.toggle('report-folders-open');
        folderToggle.setAttribute('aria-expanded', String(isOpen));
        folderToggle.setAttribute('aria-label', isOpen ? 'Close folders' : 'Open folders');
    };
    document.onclick = event => {
        if (document.body.classList.contains('report-folders-open') &&
            !event.target.closest('.rep-sidebar, .rep-folder-toggle')) {
            closeFolderMenu();
        }
    };
    document.querySelectorAll('[data-folder]').forEach(button => {
        button.onclick = () => { selectedFolder = button.dataset.folder; closeFolderMenu(); draw() };
    });
    if (!window.matchMedia('(max-width: 640px)').matches) closeFolderMenu();
    const picker = $('#rep-date-picker');
    const dateTrigger = $('#rep-date-trigger');
    const closeDatePicker = () => {
        picker.hidden = true;
        dateTrigger.setAttribute('aria-expanded', 'false');
    };
    document.onkeydown = event => {
        if (event.key === 'Escape') {
            closeDatePicker();
            closeFolderMenu();
        }
    };
    dateTrigger.onclick = () => {
        draftStart = dateStart;
        draftEnd = dateEnd;
        const month = draftStart ? dateFromKey(draftStart) : new Date();
        calendarMonth = new Date(month.getFullYear(), month.getMonth(), 1);
        renderDateCalendars();
        picker.hidden = false;
        dateTrigger.setAttribute('aria-expanded', 'true');
    };
    picker.onclick = event => {
        if (event.target === picker || event.target.closest('[data-date-cancel]')) {
            closeDatePicker();
            return;
        }
        const presetButton = event.target.closest('[data-date-preset]');
        if (presetButton) {
            const preset = presetButton.dataset.datePreset;
            if (preset === 'any') {
                setDateRange('', '');
            } else if (preset === 'custom') {
                presetButton.classList.add('active');
                return;
            } else {
                applyPreset(preset);
            }
            return;
        }
        const monthButton = event.target.closest('[data-calendar-nav]');
        if (monthButton) {
            calendarMonth.setMonth(calendarMonth.getMonth() + Number(monthButton.dataset.calendarNav));
            renderDateCalendars();
            return;
        }
        const dayButton = event.target.closest('[data-calendar-date]');
        if (dayButton) {
            const selectedDate = dayButton.dataset.calendarDate;
            if (!draftStart || draftEnd) {
                draftStart = selectedDate;
                draftEnd = '';
            } else if (selectedDate < draftStart) {
                draftEnd = draftStart;
                draftStart = selectedDate;
            } else {
                draftEnd = selectedDate;
            }
            renderDateCalendars();
            return;
        }
        if (event.target.closest('[data-date-apply]') && draftStart && draftEnd) {
            setDateRange(draftStart, draftEnd);
        }
    };
    const csv = $('#rep-csv');
    if (csv) csv.onclick = exportCsv;
}

setupImageViewer();
load();
