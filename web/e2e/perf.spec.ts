/**
 * Performance probe for the library grid (docs/wiring/web.md, "Performance"). Not part of the
 * normal run: start a 10k-photo mock and a production build, then
 *
 *   MOCK_COUNT=10000 MOCK_PORT=9311 node mock-api/server.ts &
 *   pnpm build && PA_API=http://127.0.0.1:9311 pnpm exec vite preview --port 9312 &
 *   PERF=1 E2E_BASE_URL=http://127.0.0.1:9312 pnpm exec playwright test perf --project phone
 *
 * It prints one JSON line per measurement; nothing is asserted beyond sanity.
 */
import type { CDPSession, Page } from '@playwright/test';
import { expect, signIn, test } from './helpers.ts';

test.skip(!process.env.PERF, 'set PERF=1 (see the comment at the top)');

async function throttle(page: Page, rate: number): Promise<CDPSession> {
	const cdp = await page.context().newCDPSession(page);
	await cdp.send('Emulation.setCPUThrottlingRate', { rate });
	return cdp;
}

test('library grid on a 10k library', async ({ page }, info) => {
	test.setTimeout(180_000);
	await signIn(page, '/settings');
	const assetRequests: string[] = [];
	page.on('request', (r) => {
		if (/\/api\/assets(\?|\/facets)/.test(r.url())) assetRequests.push(r.url());
	});
	await page.addInitScript(() => {
		const w = window as unknown as { __long: number[] };
		w.__long = [];
		new PerformanceObserver((list) => {
			for (const e of list.getEntries()) w.__long.push(e.duration);
		}).observe({ type: 'longtask', buffered: true });
	});
	const cdp = await throttle(page, 4);

	// 1. Time to first thumbnails (navigation start → first decoded tile image).
	const started = Date.now();
	await page.goto('/');
	await page.waitForFunction(() =>
		[...document.querySelectorAll<HTMLImageElement>('.tile img')].some(
			(i) => i.complete && i.naturalWidth > 0
		)
	);
	const firstThumbs = Date.now() - started;
	await page.waitForTimeout(1500);
	const requestsAtStart = assetRequests.length;
	const pagesAtStart = assetRequests.filter((u) => /\/api\/assets\?/.test(u)).length;
	const nodesAtTop = await page.evaluate(() => document.getElementsByTagName('*').length);

	// 2. Long tasks while scrolling 30 screens, frame by frame like a flick.
	await page.evaluate(() => ((window as unknown as { __long: number[] }).__long = []));
	const scrollStart = Date.now();
	await page.evaluate(async () => {
		for (let i = 0; i < 30 * 12; i++) {
			window.scrollBy(0, window.innerHeight / 12);
			await new Promise((r) => requestAnimationFrame(r));
		}
	});
	const scrollMs = Date.now() - scrollStart;
	await page.waitForTimeout(1000);
	const long = await page.evaluate(() => (window as unknown as { __long: number[] }).__long);
	const nodesScrolled = await page.evaluate(() => document.getElementsByTagName('*').length);
	const tiles = await page.locator('.tile').count();
	await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });

	const result = {
		project: info.project.name,
		firstThumbsMs: firstThumbs,
		assetRequestsInFirst1500ms: requestsAtStart,
		pagesFetchedAtStart: pagesAtStart,
		domNodesAtTop: nodesAtTop,
		domNodesAfter30Screens: nodesScrolled,
		tilesInDomAfter30Screens: tiles,
		scroll30ScreensMs: scrollMs,
		longTasksWhileScrolling: long.length,
		longTaskTotalMs: Math.round(long.reduce((a, b) => a + b, 0)),
		longestTaskMs: Math.round(Math.max(0, ...long))
	};
	console.log(`PERF ${JSON.stringify(result)}`);
	expect(firstThumbs).toBeGreaterThan(0);
});
