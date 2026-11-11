/* Ad Vandi Service Worker (PWA) */
const CACHE_NAME = 'advandi-v2.5';
const REPORT_IMAGE_CACHE_MAX_AGE = 24 * 60 * 60 * 1000;
const REPORT_IMAGE_CACHE_LIMIT = 100;

function reportImageCacheMetadataRequest(request) {
    const url = new URL(request.url);
    const metadataPath = '/__sw_cache__/report-image/' +
        encodeURIComponent(url.pathname + url.search);
    return new Request(new URL(metadataPath, self.location.origin));
}

async function trimReportImageCache(cache) {
    const imageRequests = (await cache.keys()).filter(request => {
        const url = new URL(request.url);
        return url.origin === self.location.origin &&
            url.pathname.startsWith('/report/image/');
    });
    if (imageRequests.length <= REPORT_IMAGE_CACHE_LIMIT) return;

    const images = await Promise.all(imageRequests.map(async request => {
        const metadata = await cache.match(reportImageCacheMetadataRequest(request));
        const { cachedAt = 0 } = metadata ? await metadata.json() : {};
        return { request, cachedAt: Number(cachedAt) || 0 };
    }));
    images.sort((a, b) => a.cachedAt - b.cachedAt);
    await Promise.all(images.slice(0, images.length - REPORT_IMAGE_CACHE_LIMIT).map(async image => {
        await cache.delete(image.request);
        await cache.delete(reportImageCacheMetadataRequest(image.request));
    }));
}

const PRECACHE_ASSETS = [
    '/',
    '/static/style.css',
    '/static/theme.css',
    '/static/theme.js',
    '/static/ad-vandi-logo-light.svg',
    '/static/app.js',
    '/static/ad-vandi-logo.png',
    '/static/alert.mp3',
    '/manifest.webmanifest',
    '/static/icons/icon.svg',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/icons/icon-maskable-512.png',
    '/static/icons/apple-touch-icon.png',
    '/static/icons/favicon.png'
];

const EXTERNAL_ASSETS = [
    'https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600;700&display=swap'
];

self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(async cache => {
            await Promise.allSettled(
                PRECACHE_ASSETS.map(url =>
                    cache.add(new Request(url, { cache: 'reload' })).catch(err => {
                        console.warn('[SW] Precache failed for:', url, err);
                    })
                )
            );
            await Promise.allSettled(
                EXTERNAL_ASSETS.map(url =>
                    cache.add(url).catch(err => console.warn('[SW] External font precache failed:', err))
                )
            );
        })
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => {
                    console.log('[SW] Removing old cache:', k);
                    return caches.delete(k);
                })
            )
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', event => {
    const req = event.request;
    const url = new URL(req.url);

    // Non-GET requests (e.g. POST /api/events, /api/extract) are handled directly by network
    if (req.method !== 'GET') {
        return;
    }

    // Report image IDs are stable; cache them briefly for fast repeat views.
    if (url.pathname.startsWith('/report/image/')) {
        event.respondWith((async () => {
            const cache = await caches.open(CACHE_NAME);
            const metadataRequest = reportImageCacheMetadataRequest(req);
            const cached = await cache.match(req);
            const metadata = cached && await cache.match(metadataRequest);
            if (cached && metadata) {
                const { cachedAt = 0 } = await metadata.json();
                const age = Date.now() - Number(cachedAt);
                if (age >= 0 && age < REPORT_IMAGE_CACHE_MAX_AGE) {
                    return cached;
                }
            }

            let response;
            try {
                response = await fetch(req);
            } catch (error) {
                if (cached) return cached;
                throw error;
            }

            if (response.status === 200 || response.type === 'opaque') {
                try {
                    await cache.put(req, response.clone());
                    await cache.put(metadataRequest, new Response(
                        JSON.stringify({ cachedAt: Date.now() }),
                        { headers: { 'Content-Type': 'application/json' } }
                    ));
                    await trimReportImageCache(cache);
                } catch (error) {
                    console.warn('[SW] Could not cache report image:', error);
                }
            } else {
                await cache.delete(req);
                await cache.delete(metadataRequest);
            }
            return response;
        })());
        return;
    }

    // 1. Navigation requests (HTML pages) -> Network first, fallback to cached shell
    if (req.mode === 'navigate') {
        event.respondWith(
            fetch(req)
                .then(res => {
                    if (res && res.status === 200) {
                        const copy = res.clone();
                        caches.open(CACHE_NAME).then(c => c.put(req, copy));
                    }
                    return res;
                })
                .catch(async () => {
                    const cached = await caches.match(req);
                    if (cached) return cached;
                    const shell = await caches.match('/');
                    if (shell) return shell;
                    return new Response(
                        '<!DOCTYPE html><html><body style="background:#080c16;color:#e8ca78;font-family:sans-serif;padding:2rem;text-align:center"><h2>Ad Vandi is Offline</h2><p>Please check your connection and reopen the app.</p></body></html>',
                        { headers: { 'Content-Type': 'text/html' } }
                    );
                })
        );
        return;
    }

    // 2. API calls -> Network only, fallback to offline JSON error
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(req).catch(() => {
                return new Response(
                    JSON.stringify({ error: 'You are currently offline. Check your network connection.', offline: true }),
                    { status: 503, headers: { 'Content-Type': 'application/json' } }
                );
            })
        );
        return;
    }

    // 3. Static assets & scripts -> NETWORK FIRST, fallback to cache
    // This ensures code changes (app.js, style.css) are NEVER blocked by stale cache!
    event.respondWith(
        fetch(req)
            .then(response => {
                if (response && response.status === 200 && (response.type === 'basic' || response.type === 'cors')) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then(c => c.put(req, copy));
                }
                return response;
            })
            .catch(() => caches.match(req))
    );
});

self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// ---------- PUSH ALERTS ----------
self.addEventListener('push', event => {
    let d = { title: 'Alert', body: 'New alert' };
    try {
        if (event.data) d = Object.assign(d, event.data.json());
    } catch (e) {
        if (event.data) d.body = event.data.text();
    }

    event.waitUntil((async () => {
        await self.registration.showNotification(d.title, {
            body: d.body,
            icon: '/static/icons/icon-192.png',
            badge: '/static/icons/favicon.png',
            requireInteraction: true,
            vibrate: [500, 200, 500, 200, 500, 200, 500],
            tag: 'alert',
            renotify: true,
            silent: false,
            data: { url: '/' }
        });

        const wins = await clients.matchAll({ type: 'window', includeUncontrolled: true });
        wins.forEach(w => w.postMessage({ type: 'ALARM' }));
    })());
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || '/';
    event.waitUntil((async () => {
        const wins = await clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const w of wins) {
            if ('focus' in w) return w.focus();
        }
        return clients.openWindow(url);
    })());
});
