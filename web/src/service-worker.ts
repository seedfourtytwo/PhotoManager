/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
/**
 * Caches the app shell only (built JS/CSS, icons, the SPA page), so the app opens fast and
 * installs as a PWA. Never caches /api: photos and metadata are private per user and are left
 * to the normal HTTP cache.
 */
import { build, files, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `shell-${version}`;
const SHELL = [...build, ...files.filter((f) => !f.endsWith('robots.txt')), '/'];

sw.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(SHELL))
			.then(() => sw.skipWaiting())
	);
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => sw.clients.claim())
	);
});

sw.addEventListener('fetch', (event) => {
	const url = new URL(event.request.url);
	if (event.request.method !== 'GET' || url.origin !== sw.location.origin) return;
	if (url.pathname.startsWith('/api/')) return;
	const shellFile = SHELL.includes(url.pathname);
	// Navigations get the SPA page (fallback index.html); everything else only if it's shell.
	if (event.request.mode === 'navigate') {
		event.respondWith(
			fetch(event.request).catch(async () => (await caches.match('/')) ?? Response.error())
		);
	} else if (shellFile) {
		event.respondWith(caches.match(url.pathname).then((hit) => hit ?? fetch(event.request)));
	}
});
