/** Shared E2E helpers: reset the mock, sign in, and a few gestures Playwright lacks. */
import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type Locator, type Page } from '@playwright/test';
import { MOCK_URL } from '../playwright.config.ts';
import type { AssetDetail, Facets, Person } from '../src/lib/api/types.ts';

export const ADMIN = {
	username: process.env.E2E_USER ?? 'admin',
	name: process.env.E2E_NAME ?? 'C',
	pin: process.env.E2E_PIN ?? '1234'
};

/**
 * Where to reset the library before a test: the mock's `/__mock/reset`, or a real backend in
 * test mode (`PA_TEST_MODE=1`, `/__test/reset`, see `just e2e`). Without one, tests that need a
 * known state skip.
 */
export const RESET_URL = process.env.E2E_RESET_URL ?? (MOCK_URL ? `${MOCK_URL}/__mock/reset` : '');
export const REAL_BACKEND = !!process.env.E2E_RESET_URL;

/** Fresh, known state (the mock's seed, or the real backend's seeded snapshot). */
export async function resetMock(
	users: 'seed' | 'none' = 'seed',
	options: { models?: boolean; count?: number; review?: boolean; locked?: string } = {}
) {
	test.skip(!RESET_URL, 'needs a reset endpoint (mock API or backend test mode)');
	test.skip(REAL_BACKEND && !!options.models, 'ML models are a mock-only switch');
	test.skip(REAL_BACKEND && !!options.review, 'photos held for review are a mock-only switch');
	test.skip(REAL_BACKEND && !!options.locked, 'an account locked from the start is mock-only');
	const response = await fetch(RESET_URL, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(REAL_BACKEND ? { users } : { users, ...options })
	});
	expect(response.status).toBe(204);
}

export const GUEST = { username: 'guest', name: 'Guest', pin: '3456' };
export const MEMBER = { username: 'partner', name: 'Partner', pin: '2345' };

export async function signIn(page: Page, path = '/', who = ADMIN) {
	await page.goto(`/login?next=${encodeURIComponent(path)}`);
	await page.getByRole('button', { name: who.name, exact: true }).click();
	await page.getByLabel('PIN').fill(who.pin); // the fourth digit signs in
	await expect(page).toHaveURL(new RegExp(`${path.replace(/[?]/g, '\\?')}$`));
}

/** An admin section of Settings. */
export type AdminSection = 'overview' | 'folders' | 'backups' | 'people' | 'search';

/** Where every Admin spec starts: a fresh library, signed in on that section of Settings. */
export async function openAdmin(page: Page, section: AdminSection = 'overview') {
	await resetMock();
	await signIn(page, `/settings/${section}`);
}

/** Fill a PIN sheet, entry by entry: it asks for the new PIN twice (and the current one first). */
export async function fillPins(sheet: Locator, pins: Record<string, string>) {
	for (const [label, pin] of Object.entries(pins))
		await sheet.getByLabel(label, { exact: true }).fill(pin);
}

/** The avatar, named "You" (and, for an admin, what needs them): it opens You. */
export const avatar = (page: Page) =>
	page.getByRole('link', { name: /^You\b/ }).and(page.locator('.avatar'));

/** Follow a link the way a click in the app does (no reload). */
export async function follow(page: Page, href: string) {
	await page.evaluate((to) => {
		const link = Object.assign(document.createElement('a'), { href: to });
		document.body.append(link);
		link.click();
		link.remove();
	}, href);
}

/**
 * How long a test waits before it says that nothing happened: no second request, no step
 * out of the page, no late answer painted over the screen. Nothing announces that, so the
 * test waits out what could still be on its way (a request `countSlow` holds for 300 ms, a
 * debounced write, a navigation, a frame of drawing) and then looks.
 */
export const NOTHING_HAPPENS_MS = 500;

/**
 * Count the requests a route gets and hold each one a moment, so a double click overlaps.
 * With a `method`, only those requests count and wait.
 */
export async function countSlow(page: Page, url: string | RegExp, method?: string) {
	const seen = { count: 0 };
	await page.route(url, async (route) => {
		if (method && route.request().method() !== method) return route.fallback();
		seen.count++;
		await new Promise((r) => setTimeout(r, 300));
		await route.fallback();
	});
	return seen;
}

/** Answer a route `ms` late. The page may have left by then: an answer nobody waits for is fine. */
export async function delayRoute(page: Page, url: string | RegExp, ms: number) {
	await page.route(url, async (route) => {
		await new Promise((r) => setTimeout(r, ms));
		await route.continue().catch(() => undefined);
	});
}

/**
 * Answer a photo's details with some values replaced: the server's own answer (mock or real
 * backend) with what `change` returns laid over it.
 */
export async function withDetail(
	page: Page,
	change: (detail: AssetDetail) => Partial<AssetDetail>
) {
	await page.route(/\/api\/assets\/\d+$/, async (route) => {
		if (route.request().method() !== 'GET') return route.fallback();
		const response = await route.fetch();
		const detail = (await response.json()) as AssetDetail;
		await route.fulfill({ response, json: { ...detail, ...change(detail) } });
	});
}

/** The app's one-line notice (toast). Other status texts exist: loading lines, "3 selected". */
export const toast = (page: Page) => page.locator('[role="status"][aria-live="polite"]');

/** The interface face (tokens.css --font-ui), as computed: what reads and what shows data. */
export const UI_FACE = /^"?Inter\b/;

export const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 640;

/** Touch pointer events, dispatched directly (Playwright has tap but no long-press). */
async function touch(target: Locator, type: string, dx = 0, dy = 0) {
	const box = (await target.boundingBox())!;
	await target.dispatchEvent(type, {
		pointerType: 'touch',
		isPrimary: true,
		bubbles: true,
		clientX: box.x + box.width / 2 + dx,
		clientY: box.y + box.height / 2 + dy
	});
}

/**
 * A touch held past the grid's long-press threshold: 450 ms, a constant private to
 * PhotoGrid.svelte (`LONG_PRESS_MS`). 600 ms is that with room for a slow machine.
 */
export async function longPress(tile: Locator) {
	await touch(tile, 'pointerdown');
	await tile.page().waitForTimeout(600);
	await touch(tile, 'pointerup');
}

/**
 * The photo view opens and closes as a view transition. While the browser takes its two
 * pictures (from `startViewTransition` until the first moving frame: a frame or two on
 * opening, the trip back through the history on closing) it delivers input to nothing. Once
 * the pictures move, the page takes input again.
 */
export const takesInput = (page: Page) =>
	page.waitForFunction(
		() =>
			!document.documentElement.matches(':active-view-transition') ||
			document
				.getAnimations()
				.some((a) => (a.effect as KeyframeEffect).pseudoElement?.startsWith('::view-transition'))
	);

/**
 * Real touch input through the DevTools protocol: the browser applies touch-action and may
 * cancel the pointer stream, exactly as on a phone (dispatched pointer events would not).
 * The finger goes down at `from` (and rests there for `hold` ms), moves to `to` and stays
 * down; the returned function lifts it.
 */
export async function touchDown(
	page: Page,
	from: { x: number; y: number },
	to: { x: number; y: number },
	{ steps = 8, hold = 0 }: { steps?: number; hold?: number } = {}
): Promise<() => Promise<void>> {
	await takesInput(page);
	const cdp = await page.context().newCDPSession(page);
	const point = (t: number) => [
		{ x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t }
	];
	await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: point(0) });
	if (hold) await page.waitForTimeout(hold);
	for (let i = 1; i <= steps; i++) {
		await cdp.send('Input.dispatchTouchEvent', {
			type: 'touchMove',
			touchPoints: point(i / steps)
		});
		await page.waitForTimeout(16);
	}
	return async () => {
		await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
		await cdp.detach();
	};
}

/** A whole swipe: down at `from`, across to `to`, and up. */
export async function touchSwipe(
	page: Page,
	from: { x: number; y: number },
	to: { x: number; y: number },
	steps = 8
) {
	await (
		await touchDown(page, from, to, { steps })
	)();
}

/** The centre of an element, for touch gestures. */
export async function centre(target: Locator) {
	const box = (await target.boundingBox())!;
	return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/**
 * To the next photo in the photo view as each device does it: a swipe on a phone (which draws
 * no edge arrows), the Next arrow on a laptop.
 */
export async function stepNext(page: Page) {
	const viewer = page.getByRole('dialog', { name: 'Photo viewer' });
	if (!isPhone(page)) return viewer.getByRole('button', { name: 'Next photo' }).click();
	const at = await centre(viewer.locator('.stage'));
	await touchSwipe(page, at, { x: at.x - 200, y: at.y });
}

/** Select photos the way each device does it: the keyboard (x), or long-press then tap. */
export async function selectTiles(page: Page, indexes: number[]) {
	const tiles = page.locator('.tile');
	// The presses below skip Playwright's own wait for a target that takes them, and a page
	// that is still sliding in takes no tap (as on an iPhone): wait for the move to end.
	await expect(page.locator('html')).not.toHaveAttribute('data-page-move');
	for (const [n, i] of indexes.entries()) {
		const tile = tiles.nth(i);
		// Not by the circle: on a wide touch screen it sits at the photo's bottom right, where
		// the dock or the pill may be over it.
		if (!isPhone(page)) {
			await tile.focus();
			await page.keyboard.press('x');
		} else if (n === 0) await longPress(tile);
		else await tile.tap();
	}
	await expect(selectedCount(page)).toHaveText(`${indexes.length} selected`);
}

/** The pill's count ("3 selected"); the Library's title says "3 Selected" as well. */
export const selectedCount = (page: Page) =>
	page.getByRole('toolbar', { name: 'Selected photos' }).getByRole('status');

/** The time scrubber hides at rest: a mouse at the right edge brings it out, or a fast scroll. */
export async function scrubberOut(page: Page) {
	if (isPhone(page))
		await page.evaluate(async () => {
			window.scrollBy(0, 10);
			await new Promise((r) => setTimeout(r, 120));
			window.scrollBy(0, 3 * innerHeight);
		});
	else await page.mouse.move(page.viewportSize()!.width - 8, 400);
	await expect(page.getByRole('slider', { name: 'Jump to date' })).toHaveClass(/out/);
}

/**
 * Scroll the library until a photo's tile is on screen. The grid only draws the rows near
 * the screen, so a photo further down has no tile to scroll to until the page has moved.
 */
export async function scrollToTile(page: Page, id: number): Promise<Locator> {
	const tile = page.locator(`.tile[data-id="${id}"]`);
	await expect(async () => {
		if ((await tile.count()) === 0) {
			await page.evaluate(() => window.scrollBy(0, window.innerHeight));
		}
		await expect(tile).toBeAttached({ timeout: 500 });
	}).toPass();
	await tile.scrollIntoViewIfNeeded();
	return tile;
}

/** A photo the signed-in user may only view (not download), found through the API. */
export async function viewOnlyPhoto(page: Page): Promise<number> {
	const list = await (await page.request.get('/api/assets?source_id=2&limit=200')).json();
	for (const item of list.items as { id: number }[]) {
		const detail = await (await page.request.get(`/api/assets/${item.id}`)).json();
		if (detail.level === 'view') return item.id;
	}
	throw new Error('no view-only photo for this user');
}

/**
 * Select every photo the Library has loaded: Select in the head, then the pill's More, where
 * it says "Select all" (or "Select loaded (n)" while more are to load).
 */
export async function selectEverything(page: Page, name: string | RegExp = /^Select (all|loaded)/) {
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	if (!(await bar.isVisible()))
		await page.getByRole('button', { name: 'Select', exact: true }).click();
	const more = bar.getByRole('button', { name: 'More' });
	if ((await more.getAttribute('aria-expanded')) !== 'true') await more.click();
	await bar.getByRole('button', { name, exact: typeof name === 'string' }).click();
}

/** Run an action of the selection pill; on a phone the later ones are under "More". */
export async function selectionAction(page: Page, name: string | RegExp) {
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	const button = bar.getByRole('button', { name, exact: typeof name === 'string' });
	if (!(await button.isVisible())) await bar.getByRole('button', { name: 'More' }).click();
	await button.click();
}

/**
 * The first month of a year's grid in the When sheet that has photos (the mock's and the real
 * server's libraries differ): its name ("March 2019") and its number (3).
 */
export async function firstMonthWithPhotos(months: Locator) {
	const all = await months.getByRole('button').all();
	const index = (await Promise.all(all.map((month) => month.isEnabled()))).indexOf(true);
	const label = (await all[index].getAttribute('aria-label')) ?? '';
	return { button: all[index], name: label.split(':')[0], number: index + 1 };
}

/**
 * A closed sheet's history step is undone a moment after it closes: going on to another page
 * before that is cut short. Waits until it is gone.
 */
export async function sheetStepGone(page: Page) {
	await page.waitForFunction(() => !JSON.stringify(history.state ?? {}).includes('"sheet"'));
}

/** How many rows `longLists` adds to each list, so it is longer than any screen. */
export const MANY = 40;
const many = <T>(make: (i: number) => T) => Array.from({ length: MANY }, (_, i) => make(i));

/**
 * Long lists in the filter sheets: forty more years (1940 down to 1901), places (Town 1…40),
 * cameras (Camera 1…40) and named people (Person 1…40) added to what the server answers, the
 * mock and the real backend alike. The last one added is the last row of its list.
 */
export async function longLists(page: Page) {
	await page.route(/\/api\/assets\/facets\b/, async (route) => {
		const response = await route.fetch();
		const answer = (await response.json()) as Facets;
		await route.fulfill({
			response,
			json: {
				...answer,
				years: [...answer.years, ...many((i) => ({ year: 1900 + MANY - i, count: MANY - i }))],
				places: [...answer.places, ...many((i) => ({ name: `Town ${i + 1}`, count: MANY - i }))],
				cameras: [...answer.cameras, ...many((i) => ({ name: `Camera ${i + 1}`, count: MANY - i }))]
			}
		});
	});
	await page.route(/\/api\/people(\?.*)?$/, async (route) => {
		const response = await route.fetch();
		const answer = (await response.json()) as Person[];
		const named = many<Person>((i) => ({
			id: 10_000 + i,
			name: `Person ${i + 1}`,
			face_count: 1,
			hidden: false,
			asset_count: 1,
			cover: null,
			portrait: null
		}));
		await route.fulfill({ response, json: [...answer, ...named] });
	});
}

/** The open photo: the photo view (the loupe), a modal dialog. */
export const loupe = (page: Page) => page.getByRole('dialog', { name: 'Photo viewer' });

/** Run an action of the open photo; the ones that are not on its bar are under "More". */
export async function loupeAction(page: Page, name: string) {
	const viewer = loupe(page);
	const button = viewer.getByRole('button', { name, exact: true });
	if (!(await button.isVisible())) await viewer.getByRole('button', { name: 'More' }).click();
	await button.click();
}

/** Zero serious or critical axe violations on the current page. */
export async function expectAccessible(page: Page) {
	const results = await new AxeBuilder({ page }).analyze();
	const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
	expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual(
		[]
	);
}

/**
 * Every spec's `test`. When a test ends, its routes stop first: a handler still on its way
 * (a polling page asks again every second or so) would otherwise lose the answer it fetched
 * as the page closes, fail, and take down whichever test runs next.
 */
export const test = base.extend({
	page: async ({ page }, use) => {
		await use(page);
		await page.unrouteAll({ behavior: 'ignoreErrors' });
	}
});
export { expect };
