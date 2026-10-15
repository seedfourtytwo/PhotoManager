/** Home (issue 54, spec 2026-10-14 §9): a story read top to bottom, and the story player. */
import type { Page } from '@playwright/test';
import type { AssetOut, AssetPage, HomeData, Memory } from '../src/lib/api/types.ts';
import {
	ADMIN,
	expect,
	expectAccessible,
	isPhone,
	loupe,
	loupeAction,
	REAL_BACKEND,
	resetMock,
	selectTiles,
	selectionAction,
	signIn,
	test,
	toast
} from './helpers.ts';

/** Home as the mock answers it, with `change` laid over it. */
async function homeWith(page: Page, change: (home: HomeData) => Partial<HomeData>) {
	await page.route('**/api/home', async (route) => {
		const response = await route.fetch();
		const home = (await response.json()) as HomeData;
		await route.fulfill({ response, json: { ...home, ...change(home) } });
	});
}

/**
 * A day of the library as On this day: the day of one of its photos, `years` ago. Home leaves
 * dates guessed from a file out, so the photo's date is not a guess.
 */
async function dayOfPhoto(page: Page, years = 3): Promise<HomeData['on_this_day']> {
	const answer = await page.request.get('/api/assets?limit=1&guessed_date=false');
	const { items } = (await answer.json()) as AssetPage;
	const cover = items[0];
	const day = cover.taken_at.slice(0, 10);
	return {
		day,
		years_ago: years,
		exact: true,
		count: 1,
		cover,
		place: 'Lisbon',
		people: [{ id: 2, name: 'Sam' }],
		filter: { from: day, to: day, guessed_date: false }
	};
}

/** A year of the library as Years shows it: the year of one of its photos with a real date. */
async function yearOfPhoto(page: Page): Promise<Memory> {
	const answer = await page.request.get('/api/assets?limit=1&guessed_date=false');
	const [cover] = ((await answer.json()) as AssetPage).items;
	const year = cover.taken_at.slice(0, 4);
	const [from, to] = [`${year}-01-01`, `${year}-12-31`];
	return {
		key: `${from}_${to}`,
		title: year,
		from,
		to,
		count: 12,
		cover,
		filter: { from, to, guessed_date: false }
	};
}

const block = (page: Page, name: string) =>
	page.getByRole('main').getByRole('heading', { level: 2, name, exact: true });

test.beforeEach(async () => {
	await resetMock();
});

test('home: each block shows when it has photos, top to bottom, and not when it has none', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'named people need the ML models, which the E2E server does not have');
	await signIn(page, '/home');
	const day = await dayOfPhoto(page);
	await homeWith(page, () => ({ on_this_day: day }));
	await page.reload();
	const main = page.getByRole('main');

	await expect(main.getByRole('region', { name: 'On this day' })).toBeVisible();
	await expect(main.getByRole('button', { name: /Three years ago today/ })).toContainText(
		'Lisbon, with Sam'
	);
	const titles = main.getByRole('heading', { level: 2 });
	await expect(titles).toHaveText([
		'Rediscover',
		'Memories',
		'Suggested albums',
		'Years',
		'Pinned',
		'People',
		'New this week'
	]);
	await expect(main.getByText(/^\d+ photos arrived from /)).toBeVisible();
	await expect(main.getByRole('link', { name: /^Choose/ })).toHaveAttribute('href', '/');
	await expect(main.getByRole('link', { name: 'All photos' })).toHaveAttribute('href', '/');
	await expect(main.getByRole('link', { name: 'People' })).toHaveAttribute('href', '/people');
	// a cover keeps its shape: never cropped
	const cover = main.getByRole('region', { name: 'On this day' }).locator('img');
	const shape = await cover.evaluate((img: HTMLImageElement) => getComputedStyle(img).objectFit);
	expect(shape).toBe('contain');
	await expectAccessible(page);

	// Nothing on this day, to rediscover, no memories or years, nothing new: not there at all.
	await page.unrouteAll();
	await page.route('**/api/album-suggestions', (route) => route.fulfill({ json: [] }));
	await homeWith(page, (home) => ({
		on_this_day: null,
		rediscover: [],
		memories: [],
		years: [],
		new: { ...home.new, count: 0, sources: [], items: [] }
	}));
	await page.reload();
	await expect(block(page, 'Pinned')).toBeVisible();
	await expect(titles).toHaveText(['Pinned', 'People']);
	await expect(main.getByRole('region', { name: 'On this day' })).toHaveCount(0);
});

test('home: with nothing to show it says so in one sentence, and what to do', async ({ page }) => {
	await signIn(page, '/admin');
	const nothing: HomeData = {
		on_this_day: null,
		rediscover: [],
		memories: [],
		years: [],
		new: { count: 0, days: 7, sources: [], items: [] }
	};
	await page.route('**/api/home', (route) => route.fulfill({ json: nothing }));
	await page.route('**/api/people', (route) => route.fulfill({ json: [] }));
	await page.route('**/api/album-suggestions', (route) => route.fulfill({ json: [] }));
	let libraryEmpty = true;
	await page.route(/\/api\/assets\?/, (route) =>
		libraryEmpty || route.request().url().includes('pinned=true')
			? route.fulfill({ json: { items: [], next_cursor: null } })
			: route.fallback()
	);
	const main = page.getByRole('main');
	const empty = main.locator('.empty-state');

	await page.goto('/home');
	await expect(empty).toContainText('No photos here yet.');
	await expect(empty.getByRole('link', { name: 'Library' })).toBeVisible();
	await expect(main.getByRole('heading', { level: 2 })).toHaveCount(0);

	// Photos, but nothing pinned, no trip, nothing on this day or this week.
	libraryEmpty = false;
	await page.reload();
	await expect(empty).toContainText('Your story starts here.');
	await expect(empty.getByRole('link', { name: 'You' })).toHaveAttribute('href', '/settings');
	await expect(main.getByRole('heading', { level: 2 })).toHaveCount(0);
	await expectAccessible(page);
});

test('You → Home: the account turns blocks off and moves them; its Home follows, a reload too', async ({
	page
}) => {
	await signIn(page, '/settings');
	const editor = page.getByRole('group', { name: 'Home shows, in this order' });
	await expect(editor.getByRole('switch')).toHaveCount(8);
	await editor.getByRole('switch', { name: 'Rediscover' }).click();
	for (let step = 0; step < 3; step++)
		await editor.getByRole('button', { name: 'Move Years up' }).click();
	const order = ['years', 'on_this_day', 'memories', 'suggested', 'pinned', 'people', 'new'];
	await expect
		.poll(async () => (await (await page.request.get('/api/me/look')).json()).homeSections)
		.toEqual(order);
	await expectAccessible(page);

	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Home', exact: true })
		.click();
	const titles = page.getByRole('main').getByRole('heading', { level: 2 });
	for (const reloaded of [false, true]) {
		if (reloaded) await page.reload();
		await expect(titles.first()).toHaveText('Years');
		await expect(block(page, 'Rediscover')).toHaveCount(0);
		// On this day, when there is one, now comes after Years
		const day = page.getByRole('main').getByRole('region', { name: 'On this day' });
		if (await day.count()) {
			const [years, otd] = await Promise.all(
				[block(page, 'Years'), day].map(async (b) => (await b.boundingBox())!.y)
			);
			expect(otd).toBeGreaterThan(years);
		}
	}
});

test('home: a memory plays full screen, steps on a tap, and closes with ×, Escape or Back', async ({
	page
}) => {
	await signIn(page, '/home');
	// a trip or a month at home, else a year (the real backend's small library has no trip)
	const first = page
		.getByRole('main')
		.getByRole('region', { name: /^(Memories|Years)$/ })
		.getByRole('button', { name: /^Play: / })
		.first();
	const title = (await first.locator('.title').textContent())!;
	await first.click();
	const player = page.getByRole('dialog', { name: title });
	await expect(player).toBeVisible();
	const segments = player.locator('.segment');
	await expect(segments.first()).toBeVisible();
	const count = await segments.count();
	expect(count).toBeGreaterThan(1);
	expect(count).toBeLessThanOrEqual(40);
	await expect(player.locator('.fill.done')).toHaveCount(0);
	await player.getByRole('button', { name: 'Next photo' }).click();
	await expect(player.locator('.fill.done')).toHaveCount(1);
	await player.getByRole('button', { name: 'Previous photo' }).click();
	await expect(player.locator('.fill.done')).toHaveCount(0);
	await expectAccessible(page);

	await player.getByRole('button', { name: 'Close' }).click();
	await expect(player).toBeHidden();
	await first.click();
	await expect(player).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(player).toBeHidden();
	await first.click();
	await expect(player).toBeVisible();
	await page.goBack();
	await expect(player).toBeHidden();
	await expect(page).toHaveURL(/\/home$/);
});

test('home: On this day plays its day, titled in words', async ({ page }) => {
	await signIn(page, '/home');
	const day = await dayOfPhoto(page, 1);
	await homeWith(page, () => ({ on_this_day: { ...day!, exact: false } }));
	await page.reload();
	await page.getByRole('button', { name: /A year ago this week/ }).click();
	const player = page.getByRole('dialog', { name: 'A year ago this week' });
	await expect(player).toBeVisible();
	await expect(player.locator('.segment').first()).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(player).toBeHidden();
});

test('home: without On this day, Rediscover opens Home on a large photo that plays the dozen', async ({
	page
}) => {
	await signIn(page, '/home');
	await homeWith(page, () => ({ on_this_day: null }));
	await page.reload();
	const main = page.getByRole('main');
	const rediscover = main.getByRole('region', { name: 'Rediscover' });
	await expect(main.getByRole('heading', { level: 2 }).first()).toHaveText('Rediscover');
	const picks = ((await (await page.request.get('/api/home')).json()) as HomeData).rediscover;
	expect(picks.length).toBeGreaterThan(1);
	expect(picks.length).toBeLessThanOrEqual(12);

	// The first photo, large and whole, titled in plain words; it plays all of them.
	const hero = rediscover.getByRole('button', { name: /^Play: / });
	await expect(hero).toContainText(/ years? ago|From your library|\d{4}/);
	const shape = await hero
		.locator('img')
		.evaluate((img: HTMLImageElement) => getComputedStyle(img).objectFit);
	expect(shape).toBe('contain');
	await hero.click();
	const player = page.getByRole('dialog', { name: 'Rediscover' });
	await expect(player).toBeVisible();
	await expect(player.locator('.segment')).toHaveCount(picks.length);
	await expectAccessible(page);
	await page.keyboard.press('Escape');
	await expect(player).toBeHidden();

	// The others open the photo view, which steps through all of them.
	const grid = rediscover.getByRole('group', { name: 'Photos to rediscover' });
	await grid.locator(`[data-id="${picks[1].id}"]`).click();
	await expect(loupe(page)).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(loupe(page)).toBeHidden();
});

test('home: a suggested album is made only on Keep, and an answered one does not come back', async ({
	page
}) => {
	await signIn(page, '/home');
	const suggested = page.getByRole('main').getByRole('region', { name: 'Suggested albums' });
	const cards = suggested.getByRole('listitem');
	await expect(cards.first()).toBeVisible();
	const [first, second] = (await (await page.request.get('/api/album-suggestions')).json()) as {
		key: string;
		title: string;
		from: string;
		to: string;
	}[];
	const card = (title: string) => cards.filter({ has: page.getByText(title, { exact: true }) });
	await expect(card(first.title).getByRole('link')).toHaveAttribute(
		'href',
		`/?from=${first.from}&to=${first.to}&guessed_date=false`
	);
	await expectAccessible(page);
	const albumsBefore = ((await (await page.request.get('/api/albums')).json()) as unknown[]).length;

	await card(second.title).getByRole('button', { name: 'Discard' }).click();
	await expect(card(second.title)).toHaveCount(0);
	expect(((await (await page.request.get('/api/albums')).json()) as unknown[]).length).toBe(
		albumsBefore
	);

	await card(first.title).getByRole('button', { name: 'Keep' }).click();
	await expect(toast(page)).toContainText(`Album “${first.title}” made.`);
	await expect(card(first.title)).toHaveCount(0);
	await toast(page).getByRole('button', { name: 'Open' }).click();
	await expect(page.getByRole('heading', { level: 1, name: first.title })).toBeVisible();

	await page.goto('/home');
	await expect(block(page, 'Memories')).toBeVisible();
	await expect(card(first.title)).toHaveCount(0);
	await expect(card(second.title)).toHaveCount(0);
});

test('home: a year plays its story, and its heading opens the Library', async ({ page }) => {
	await signIn(page, '/home');
	const year = await yearOfPhoto(page);
	await homeWith(page, () => ({ years: [year] }));
	await page.reload();
	const years = page.getByRole('main').getByRole('region', { name: 'Years' });
	await expect(years.getByRole('link', { name: 'Years' })).toHaveAttribute('href', '/');
	const cover = years.getByRole('button', { name: `Play: ${year.title} 12 photos` });
	await cover.click();
	const player = page.getByRole('dialog', { name: year.title });
	await expect(player).toBeVisible();
	await expect(player.locator('.segment').first()).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(player).toBeHidden();
});

/** The id of the first photo of New this week that is not pinned. */
async function freshUnpinned(page: Page): Promise<number> {
	const home = (await (await page.request.get('/api/home')).json()) as HomeData;
	return home.new.items.find((a: AssetOut) => !a.pinned)!.id;
}

test('home: a photo is pinned and unpinned from the photo view, and Pinned follows', async ({
	page
}) => {
	await signIn(page, '/home');
	const id = await freshUnpinned(page);
	const pinned = page.getByRole('group', { name: 'Pinned photos' }).locator(`[data-id="${id}"]`);
	await expect(block(page, 'New this week')).toBeVisible();
	await expect(pinned).toHaveCount(0);

	await page.getByRole('group', { name: 'New photos' }).locator(`[data-id="${id}"]`).click();
	await expect(loupe(page)).toBeVisible();
	await loupeAction(page, 'Pin to Home');
	await expect(toast(page)).toHaveText('Pinned to Home.');
	await page.keyboard.press('Escape');
	await expect(loupe(page)).toBeHidden();
	await expect(pinned).toHaveCount(1);

	await pinned.click();
	await expect(loupe(page)).toBeVisible();
	await loupeAction(page, 'Unpin from Home');
	await expect(toast(page)).toHaveText('Unpinned from Home.');
	await page.keyboard.press('Escape');
	await expect(loupe(page)).toBeHidden();
	await expect(pinned).toHaveCount(0);
});

test('home: photos selected in the Library are pinned from the pill’s More', async ({ page }) => {
	await signIn(page, '/?year=2019');
	await selectTiles(page, [0, 1]);
	const ids = await page
		.locator('.tile[aria-pressed="true"]')
		.evaluateAll((tiles) => tiles.map((t) => Number((t as HTMLElement).dataset.id)));
	await selectionAction(page, 'Pin to Home');
	await expect(toast(page)).toHaveText('Pinned 2 photos to Home.');
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Home', exact: true })
		.click();
	const grid = page.getByRole('group', { name: 'Pinned photos' });
	for (const id of ids) await expect(grid.locator(`[data-id="${id}"]`)).toHaveCount(1);
});

/** Another tab of the same browser: signed in already, with a first page of its own. */
const newTab = (page: Page) => page.context().newPage();

/** Signing in on the sign-in page itself, as someone opening the app does: no page asked for. */
async function signInPlainly(page: Page) {
	await page.goto('/login');
	await page.getByRole('button', { name: ADMIN.name, exact: true }).click();
	await page.getByLabel('PIN').fill(ADMIN.pin);
}

test('start page: a session opens on Home; Library tapped later stays Library, a reload too', async ({
	page
}) => {
	await signInPlainly(page);
	await expect(page).toHaveURL(/\/home$/);
	const nav = page.getByRole('navigation', { name: 'Main' });
	await expect(nav.getByRole('link', { name: 'Home', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await nav.getByRole('link', { name: 'Library', exact: true }).click();
	await expect(page).toHaveURL(/\/$/);
	await page.reload();
	await expect(page.locator('.tile').first()).toBeVisible();
	await expect(page).toHaveURL(/\/$/);

	// A new tab is a new start: `/` opens Home.
	const tab = await newTab(page);
	await tab.goto('/');
	await expect(tab).toHaveURL(/\/home$/);
	await tab.close();
});

test('start page: the look decides, Library or no Home at all', async ({
	page,
	browser,
	baseURL
}) => {
	await signIn(page, '/admin');
	const setLook = (sheet: Record<string, unknown>) =>
		page.evaluate(async (body) => {
			const me = (await (await fetch('/api/auth/me')).json()) as { id: number };
			await fetch(`/api/admin/accounts/${me.id}/look`, {
				method: 'PUT',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			});
		}, sheet);
	// Another browser: nothing of the look cached, the server's answer decides.
	const elsewhere = await browser.newContext({ baseURL });
	const there = await elsewhere.newPage();
	const home = there
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Home', exact: true });

	await setLook({ startPage: 'library' });
	await signInPlainly(there);
	await expect(there.locator('.tile').first()).toBeVisible();
	await expect(there).toHaveURL(/\/$/);
	await expect(home).toBeVisible();

	await setLook({ showToday: false });
	await there.reload();
	await expect(there.locator('.tile').first()).toBeVisible();
	await expect(home).toHaveCount(0);
	await expect(there).toHaveURL(/\/$/);
	await elsewhere.close();
});

test('home: fits a phone 320 px wide without scrolling sideways', async ({ page }) => {
	test.skip(!isPhone(page), 'a phone’s width');
	await page.setViewportSize({ width: 320, height: 640 });
	await signIn(page, '/home');
	await expect(block(page, 'New this week')).toBeVisible();
	const wide = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(wide).toBe(0);
	const dock = page.getByRole('navigation', { name: 'Main' });
	for (const link of await dock.getByRole('link').all()) await expect(link).toBeInViewport();
});
