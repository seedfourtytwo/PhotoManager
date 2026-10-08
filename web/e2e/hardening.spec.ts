/** Failure states and edge cases from the architecture review: each one was a real dead end. */
import type { Page } from '@playwright/test';
import {
	ADMIN,
	expect,
	isPhone,
	REAL_BACKEND,
	resetMock,
	selectTiles,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

test('map: a drag that starts on a dot pans the map, it does not choose the dot', async ({
	page
}) => {
	test.skip(isPhone(page), 'mouse drag; a touch pan never ends in a click');
	await signIn(page, '/map');
	await expect(page.getByText(/photos with a location/)).toBeVisible();
	const dots = page.getByRole('link', { name: /photos? here/ });
	const centre = async () => {
		const box = (await dots.first().boundingBox())!;
		return [box.x + box.width / 2, box.y + box.height / 2] as const;
	};
	// Zoom in around the biggest dot, so there is room to pan and a dot under the pointer.
	await page.mouse.move(...(await centre()));
	await page.mouse.wheel(0, -100);
	await page.mouse.wheel(0, -100);
	const viewBox = async () => (await page.locator('.map svg').getAttribute('viewBox'))!.split(' ');
	await expect.poll(async () => Number((await viewBox())[2])).toBeLessThan(360);
	const before = await viewBox();
	const [x, y] = await centre();
	await page.mouse.move(x, y);
	await page.mouse.down();
	await page.mouse.move(x + 40, y + 10, { steps: 8 });
	await page.mouse.up();
	const after = await viewBox();
	expect(after[0]).not.toBe(before[0]); // it panned
	expect(after[2]).toBe(before[2]); // and did not zoom into the dot
	await expect(page.locator('section.chosen')).toHaveCount(0);
	// Choosing still works afterwards, from the keyboard and with a click.
	await dots.first().press('Enter');
	await expect(page.locator('section.chosen')).toBeVisible();
});

test('map: a failed page of located photos is reported, not swallowed', async ({ page }) => {
	await page.route(/\/api\/assets\?.*has_location=true/, (route) =>
		route.fulfill({ status: 500, json: { detail: 'the library is busy, try again' } })
	);
	await signIn(page, '/map');
	await expect(page.getByRole('status')).toContainText('The library is busy, try again');
});

test('opening the app while the server is down says so and recovers on Retry', async ({ page }) => {
	await signIn(page);
	await expect(page.locator('.tile').first()).toBeVisible();
	await page.route('**/api/auth/me', (route) => route.abort('connectionrefused'));
	await page.reload();
	const failure = page.getByRole('alert');
	await expect(failure).toContainText("Can't reach the library.");
	await expect(failure).toContainText('The library server could not be reached.');
	await expect(page.getByText('Signing you in…')).toHaveCount(0);

	// Still down: Retry keeps the message. Back up: the library opens.
	await failure.getByRole('button', { name: 'Retry' }).click();
	await expect(failure).toBeVisible();
	await page.unroute('**/api/auth/me');
	await failure.getByRole('button', { name: 'Retry' }).click();
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('a server error on opening is shown, and the app retries when the network returns', async ({
	page
}) => {
	await signIn(page);
	await page.route('**/api/auth/me', (route) =>
		route.fulfill({ status: 503, json: { detail: 'the library is starting' } })
	);
	await page.reload();
	await expect(page.getByRole('alert')).toContainText('The library is starting');
	await page.unroute('**/api/auth/me');
	await page.evaluate(() => window.dispatchEvent(new Event('online')));
	await expect(page.locator('.tile').first()).toBeVisible();
});

/** /api/stats answering that work is running, with a queue that shrinks on every call. */
async function busyStats(page: Page, delayMs = 0) {
	const asked: number[] = [];
	await page.route('**/api/stats', async (route) => {
		asked.push(Date.now());
		const answer = await route.fetch();
		const stats = await answer.json();
		stats.jobs = { ...stats.jobs, running: 1, queued: Math.max(1, 500 - asked.length) };
		if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
		await route.fulfill({ response: answer, json: stats }).catch(() => undefined);
	});
	return asked;
}

test('admin: counts are polled at a steady pace while work is running', async ({ page }) => {
	const asked = await busyStats(page);
	await signIn(page, '/admin');
	await expect(page.getByText(/working: 1 running/)).toBeVisible();
	const from = asked.length;
	await page.waitForTimeout(3200);
	// One request every 1.5 s: two in this window (three with timing slack), not dozens.
	expect(asked.length - from).toBeGreaterThanOrEqual(1);
	expect(asked.length - from).toBeLessThanOrEqual(3);
});

test('admin: polling stops when you leave the page, also with a request in flight', async ({
	page
}) => {
	const asked = await busyStats(page, 400);
	await signIn(page, '/admin');
	await expect(page.getByText(/working: 1 running/)).toBeVisible();
	const next = asked.length + 1;
	await expect.poll(() => asked.length).toBeGreaterThanOrEqual(next); // one is in flight now
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Albums' })
		.click();
	await expect(page.getByRole('heading', { name: 'Albums' })).toBeVisible();
	await page.waitForTimeout(600); // let the request in flight come back
	const settled = asked.length;
	await page.waitForTimeout(3200);
	expect(asked.length).toBe(settled);
});

/** Follow a link the way a click in the app does (no reload). */
async function follow(page: Page, href: string) {
	await page.evaluate((to) => {
		const link = Object.assign(document.createElement('a'), { href: to });
		document.body.append(link);
		link.click();
		link.remove();
	}, href);
}

test('search: clearing the search while one is running does not leave “Searching…”', async ({
	page
}) => {
	await page.route('**/api/search?*', async (route) => {
		await new Promise((r) => setTimeout(r, 800));
		await route.continue().catch(() => undefined);
	});
	await signIn(page, '/search');
	const box = page.getByRole('searchbox', { name: 'Search' });
	await box.fill('sarlat');
	await box.press('Enter');
	await expect(page.getByText('Searching…')).toBeVisible();
	await box.fill('');
	await box.press('Enter');
	await expect(page).toHaveURL(/\/search$/);
	await expect(page.getByText('Find photos by what is in them')).toBeVisible();
	await page.waitForTimeout(1000); // the abandoned search answers; nothing may change
	await expect(page.getByText('Searching…')).toHaveCount(0);
	await expect(page.getByText('Find photos by what is in them')).toBeVisible();
});

test('search: “like this photo” never names the previous photo as its source', async ({ page }) => {
	await resetMock('seed', { models: true });
	await signIn(page);
	const ids = await page
		.locator('.tile')
		.evaluateAll((tiles) => tiles.slice(0, 2).map((t) => t.getAttribute('data-id')));
	await follow(page, `/search?like=${ids[0]}`);
	await expect(page.locator(`a[href="/?photo=${ids[0]}"]`)).toBeVisible();
	// The second photo's details never arrive: the line must not keep naming the first.
	await page.route(`**/api/assets/${ids[1]}`, () => undefined);
	await follow(page, `/search?like=${ids[1]}`);
	await expect(page).toHaveURL(new RegExp(`like=${ids[1]}$`));
	await expect(page.locator(`a[href="/?photo=${ids[0]}"]`)).toHaveCount(0);
});

test('trash: “Empty trash” deletes what the page showed, not what arrived since', async ({
	page
}) => {
	await signIn(page);
	const [first, later] = await page
		.locator('.tile')
		.evaluateAll((tiles) => tiles.slice(0, 2).map((t) => Number(t.getAttribute('data-id'))));
	await page.request.delete('/api/assets', { data: { ids: [first] } });
	await page.goto('/trash');
	await expect(page.locator('.tile')).toHaveCount(1);
	// Meanwhile another device moves a photo to the trash.
	await page.request.delete('/api/assets', { data: { ids: [later] } });
	await page.getByRole('button', { name: 'Empty trash' }).click();
	const dialog = page.getByRole('dialog', { name: 'Delete for good?' });
	await expect(dialog).toContainText('1 library copy');
	const sent = page.waitForRequest('**/api/trash/empty');
	await dialog.getByRole('button', { name: 'Delete for good' }).click();
	expect((await sent).postDataJSON()).toEqual({ ids: [first] });
	await expect(page.getByRole('status')).toContainText('Deleted 1 library copy for good');
	await expect(page.locator(`.tile[data-id="${later}"]`)).toBeVisible();
});

test('a person’s photos: selecting shows the actions and there is a way out', async ({ page }) => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await signIn(page, '/people');
	await page
		.getByRole('link', { name: /^Someone/ })
		.first()
		.click();
	await expect(page.locator('.tile').first()).toBeVisible();
	await selectTiles(page, [0]); // a long press on a phone
	const bar = page.getByRole('toolbar', { name: 'Selected photos' });
	await expect(bar.getByRole('button', { name: 'Add to album' })).toBeVisible();
	if (isPhone(page)) await bar.getByRole('button', { name: 'Clear selection' }).click();
	else await page.keyboard.press('Escape');
	await expect(bar).toHaveCount(0);
});

test('calendar: one failed load does not hide every later answer', async ({ page }) => {
	await signIn(page);
	let fail = true;
	await page.route('**/api/calendar*', (route) =>
		fail
			? route.fulfill({ status: 503, json: { detail: 'the library is busy, try again' } })
			: route.continue()
	);
	await follow(page, '/calendar');
	await expect(page.getByText('The library is busy, try again')).toBeVisible();
	fail = false;
	await follow(page, '/calendar?year=2019');
	await expect(page.getByText('The library is busy, try again')).toHaveCount(0);
	await expect(page.getByRole('heading', { name: '2019' })).toBeVisible();
});

test('print: a refused plan keeps the form, so another choice can fix it', async ({ page }) => {
	await page.route('**/print/plan', (route) =>
		route.request().postDataJSON().trim === 'square-20'
			? route.fulfill({ status: 422, json: { detail: 'this album cannot be laid out square' } })
			: route.continue()
	);
	await signIn(page, '/albums/1/print');
	const size = page.getByRole('combobox', { name: 'Size' });
	await expect(page.getByText(/\d+ pages/).first()).toBeVisible();
	await size.selectOption({ label: 'Square 20 cm' });
	await expect(page.getByRole('alert')).toContainText('This album cannot be laid out square');
	await expect(size).toBeVisible();
	await expect(page.getByRole('button', { name: 'Download PDF' })).toBeDisabled();
	await size.selectOption({ index: 0 });
	await expect(page.getByRole('alert')).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Download PDF' })).toBeEnabled();
});

test('album: an album that failed to open does not block the next one', async ({ page }) => {
	await signIn(page, '/albums/1');
	const title = await page.getByRole('heading', { level: 1 }).textContent();
	await follow(page, '/albums/999999');
	await expect(page.getByRole('link', { name: 'All albums' })).toBeVisible();
	await follow(page, '/albums/1');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(title!);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('album: a slow answer for the album you left does not replace the one you are on', async ({
	page
}) => {
	await signIn(page, '/albums');
	const other = await (
		await page.request.post('/api/albums', { data: { title: 'The other album' } })
	).json();
	await page.route('**/api/albums/1', async (route) => {
		await new Promise((r) => setTimeout(r, 700));
		await route.continue().catch(() => undefined);
	});
	const asked = page.waitForRequest('**/api/albums/1');
	const late = page.waitForResponse('**/api/albums/1');
	await follow(page, '/albums/1');
	await asked;
	await follow(page, `/albums/${other.id}`);
	await expect(page.getByRole('heading', { name: 'The other album' })).toBeVisible();
	await late;
	await page.waitForTimeout(100);
	await expect(page.getByRole('heading', { name: 'The other album' })).toBeVisible();
	await expect(page.locator('.tile')).toHaveCount(0);
});

test('album: two quick moves reach the server in order, the last one last', async ({ page }) => {
	// The first save is slow: unless the second waits for it, it lands first and is overwritten.
	const arrived: number[][] = [];
	let n = 0;
	await page.route('**/api/albums/1/order', async (route) => {
		if (++n === 1) await new Promise((r) => setTimeout(r, 600));
		arrived.push(route.request().postDataJSON().asset_ids);
		await route.continue();
	});
	await signIn(page, '/albums/1');
	const tiles = page.locator('.tile');
	const ids = async () =>
		tiles.evaluateAll((all) => all.map((t) => Number(t.getAttribute('data-id'))));
	const before = await ids();
	await page.getByRole('button', { name: 'Arrange' }).click();
	await tiles.first().focus();
	await page.keyboard.press('Alt+ArrowRight');
	await expect.poll(ids).toEqual([before[1], before[0], ...before.slice(2)]);
	await page.keyboard.press('Alt+ArrowRight'); // while the first save is still on its way
	const moved = [before[1], before[2], before[0], ...before.slice(3)];
	await expect.poll(ids).toEqual(moved);
	await expect.poll(() => arrived.length).toBe(2);
	expect(arrived[1]).toEqual(moved);
	await page.reload();
	await expect.poll(ids).toEqual(moved);
});

/** Count the requests a route gets and hold each one a moment, so a double click overlaps. */
async function countSlow(page: Page, url: string, method: string) {
	const seen = { count: 0 };
	await page.route(url, async (route) => {
		if (route.request().method() !== method) return route.continue();
		seen.count++;
		await new Promise((r) => setTimeout(r, 300));
		await route.continue();
	});
	return seen;
}

test.describe('a double click sends one request', () => {
	test.beforeEach(({ page }) => test.skip(isPhone(page), 'double click'));

	test('New album creates one album', async ({ page }) => {
		const posts = await countSlow(page, '**/api/albums', 'POST');
		await signIn(page, '/albums');
		await page.getByRole('button', { name: 'New album' }).click();
		const dialog = page.getByRole('dialog', { name: 'New album' });
		await dialog.getByLabel('Title').fill('Only once');
		await dialog.getByRole('button', { name: 'Create' }).dblclick();
		await expect(page.getByRole('heading', { name: 'Only once' })).toBeVisible();
		expect(posts.count).toBe(1);
	});

	test('Rename album saves once', async ({ page }) => {
		const patches = await countSlow(page, '**/api/albums/1', 'PATCH');
		await signIn(page, '/albums/1');
		await page.getByRole('button', { name: 'Rename' }).click();
		const dialog = page.getByRole('dialog', { name: 'Rename album' });
		await dialog.getByLabel('Title').fill('Renamed once');
		await dialog.getByRole('button', { name: 'Save' }).dblclick();
		await expect(page.getByRole('heading', { name: 'Renamed once' })).toBeVisible();
		expect(patches.count).toBe(1);
	});

	test('Delete album deletes once, without a “not found” afterwards', async ({ page }) => {
		const deletes = await countSlow(page, '**/api/albums/1', 'DELETE');
		await signIn(page, '/albums/1');
		await page.getByRole('button', { name: 'Delete album' }).click();
		await page
			.getByRole('dialog', { name: 'Delete album?' })
			.getByRole('button', { name: 'Delete album' })
			.dblclick();
		await expect(page.getByRole('status')).toContainText('Album deleted');
		await expect(page).toHaveURL(/\/albums$/);
		expect(deletes.count).toBe(1);
	});

	test('Change PIN changes it once, without “the current PIN is wrong”', async ({ page }) => {
		const posts = await countSlow(page, '**/api/auth/pin', 'POST');
		await signIn(page, '/settings');
		await page.getByLabel('Current PIN').fill(ADMIN.pin);
		await page.getByLabel('New PIN').fill('8642');
		await page.getByRole('button', { name: 'Change PIN' }).dblclick();
		await expect(page.getByRole('status')).toContainText('PIN changed');
		expect(posts.count).toBe(1);
		await expect(page.getByRole('alert')).toHaveCount(0);
	});

	test('Analyse photos queues once', async ({ page }) => {
		const posts = await countSlow(page, '**/api/ml/backfill', 'POST');
		await signIn(page, '/admin');
		await page.getByRole('button', { name: 'Analyse photos not done yet' }).dblclick();
		await expect(page.getByRole('status')).toContainText(/Queued/);
		expect(posts.count).toBe(1);
	});
});

test('library: “select” says how many it takes while more photos are still to load', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'needs a library larger than one page');
	await resetMock('seed', { count: 450 });
	await signIn(page);
	const loaded = await page.getByRole('button', { name: /^Select loaded \(\d+\)$/ }).textContent();
	const n = Number(loaded!.match(/\d+/)![0]);
	expect(n).toBeLessThan(450);
	await page.getByRole('button', { name: /^Select loaded/ }).click();
	await expect(page.getByText(`${n} selected`)).toBeVisible();
	await expect(page.getByRole('button', { name: 'Select all', exact: true })).toHaveCount(0);
});

test('selecting a few photos says nothing about the 10,000 limit', async ({ page }) => {
	await signIn(page);
	await page.getByRole('button', { name: /^Select (all|loaded)/ }).click();
	await expect(page.getByText(/\d+ selected/)).toBeVisible();
	await expect(page.getByText(/the most one action can change/)).toHaveCount(0);
});

test('a link to an old photo opens it at once, not after paging through the library', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'needs a library larger than one page');
	await resetMock('seed', { count: 450 });
	await signIn(page, '/settings');
	// The oldest photo: the last one of the last page.
	let cursor: string | null = null;
	let oldest: number;
	do {
		const query: string = cursor ? `&cursor=${encodeURIComponent(cursor)}` : '';
		const list = await (await page.request.get(`/api/assets?limit=200${query}`)).json();
		oldest = list.items.at(-1).id;
		cursor = list.next_cursor;
	} while (cursor);
	// Every further page of the timeline is slow: the photo must not wait for them.
	await page.route(/\/api\/assets\?.*cursor=/, async (route) => {
		await new Promise((r) => setTimeout(r, 1500));
		await route.continue().catch(() => undefined);
	});
	await page.goto(`/?photo=${oldest}`);
	const loupe = page.getByRole('dialog', { name: 'Photo viewer' });
	await expect(loupe).toBeVisible({ timeout: 1200 });
	// Once the timeline reaches it, the loupe has its neighbours: Previous works.
	await expect(loupe.getByRole('button', { name: /Previous/ })).toBeEnabled({ timeout: 10_000 });
});

test('a person’s photos: a link to a photo beyond the loaded ones still opens it', async ({
	page
}) => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await signIn(page, '/people');
	await page
		.getByRole('link', { name: /^Someone/ })
		.first()
		.click();
	await expect(page.locator('.tile').nth(1)).toBeVisible();
	const second = await page.locator('.tile').nth(1).getAttribute('data-id');
	const person = page.url();
	// As if the photo were on a later page: the list only ever holds the first one.
	await page.route('**/api/people/*/assets*', async (route) => {
		const answer = await route.fetch();
		const list = await answer.json();
		await route.fulfill({
			response: answer,
			json: { items: list.items.slice(0, 1), next_cursor: null }
		});
	});
	await page.goto(`${person}?photo=${second}`);
	await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toBeVisible();
});
