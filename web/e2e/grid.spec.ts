/** The library grid: keyboard navigation, and loading only what is needed. */
import { expect, isPhone, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('the grid is one Tab stop; arrow keys move between photos', async ({ page }) => {
	test.skip(isPhone(page), 'keyboard');
	const tiles = page.locator('.tile');
	await expect(tiles.first()).toBeVisible();
	await expect(page.locator('.tile[tabindex="0"]')).toHaveCount(1);
	await tiles.first().focus();
	const first = await tiles.first().getAttribute('data-id');
	await page.keyboard.press('ArrowRight');
	const second = await page.evaluate(() => document.activeElement?.getAttribute('data-id'));
	expect(second).not.toBe(first);
	expect(second).toBe(await tiles.nth(1).getAttribute('data-id'));
	await page.keyboard.press('ArrowDown');
	const below = page.locator('.tile:focus');
	const [a, b] = [await tiles.nth(1).boundingBox(), await below.boundingBox()];
	expect(b!.y).toBeGreaterThan(a!.y + 20);
	await expect(page.locator('.tile[tabindex="0"]')).toHaveCount(1);
	await expect(page.locator('.tile[tabindex="0"]')).toBeFocused();
	// Enter opens the focused photo.
	const focusedId = await below.getAttribute('data-id');
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(new RegExp(`photo=${focusedId}`));
});

test('first load fetches one page, and facets only once a filter is asked', async ({ page }) => {
	const pages: string[] = [];
	const facets: string[] = [];
	page.on('request', (r) => {
		if (/\/api\/assets\?/.test(r.url())) pages.push(r.url());
		if (r.url().includes('/api/assets/facets')) facets.push(r.url());
	});
	await page.goto('/');
	await expect(page.locator('.tile img').first()).toBeVisible();
	await page.waitForTimeout(1500); // a second page, were one asked for, would be on its way by now
	expect(pages).toHaveLength(1);
	// The chips need no counts: a sheet counts its answers when it opens, on every screen.
	expect(facets).toHaveLength(0);
	await page
		.getByRole('group', { name: 'Filters' })
		.getByRole('button', { name: 'When', exact: true })
		.click();
	await expect.poll(() => facets.length).toBeGreaterThan(0);
});

test('only photos within about a screen and a half are in the page', async ({ page }) => {
	await expect(page.locator('.tile').first()).toBeVisible();
	const height = 300;
	await page.setViewportSize({ width: page.viewportSize()!.width, height });
	await page.evaluate(() => window.scrollTo(0, 1500));
	await page.waitForTimeout(400); // the grid redraws its rows after the scroll
	// The grid's one Tab stop stays rendered wherever it is; every other tile is near the screen.
	const tops = await page
		.locator('.tile[tabindex="-1"]')
		.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
	expect(tops.length).toBeGreaterThan(0);
	const row = isPhone(page) ? 120 : 240;
	for (const top of tops) {
		expect(top).toBeGreaterThan(-1.5 * height - row);
		expect(top).toBeLessThan(2.5 * height + row);
	}
});

test('zoom: bigger photos by ⌘+ (a laptop) or the ⋯ menu (a phone), kept after a reload', async ({
	page
}) => {
	await expect(page.locator('.tile').first()).toBeVisible();
	// The first month's grid: taller with larger photos (one tile could be a panorama that
	// fills its row at any size). Measured once the tiles have moved to their places (FLIP).
	const grid = page.locator('section .grid').first();
	const height = async () => {
		await expect
			.poll(() =>
				page.evaluate(
					() => document.getAnimations().filter((a) => a.playState === 'running').length
				)
			)
			.toBe(0);
		return (await grid.boundingBox())!.height;
	};
	const before = await height();
	if (isPhone(page)) {
		await page.getByRole('button', { name: 'Library menu' }).click();
		await page.getByRole('button', { name: 'Larger photos' }).click();
	} else await page.keyboard.press('ControlOrMeta+Equal');
	await expect.poll(height).toBeGreaterThan(before * 1.2);
	const bigger = await height();
	await page.reload();
	await expect(grid).toBeVisible();
	await expect.poll(height).toBeCloseTo(bigger, 0);
	// And back.
	if (isPhone(page)) {
		await page.getByRole('button', { name: 'Library menu' }).click();
		await page.getByRole('button', { name: 'Smaller photos' }).click();
	} else await page.keyboard.press('ControlOrMeta+Minus');
	await expect.poll(height).toBeCloseTo(before, 0);
});

test('phone: two fingers spreading on the photos make them bigger', async ({ page }) => {
	test.skip(!isPhone(page), 'touch');
	const grid = page.locator('section .grid').first();
	await expect(page.locator('.tile').first()).toBeVisible();
	const before = (await grid.boundingBox())!.height;
	const box = (await grid.boundingBox())!;
	const y = box.y + 80;
	const x = box.x + box.width / 2;
	const cdp = await page.context().newCDPSession(page);
	const fingers = (apart: number) => [
		{ x: x - apart / 2, y, id: 1 },
		{ x: x + apart / 2, y, id: 2 }
	];
	await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: fingers(60) });
	for (let apart = 70; apart <= 140; apart += 10) {
		await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: fingers(apart) });
		await page.waitForTimeout(16);
	}
	await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
	await cdp.detach();
	await expect.poll(async () => (await grid.boundingBox())!.height).toBeGreaterThan(before * 1.2);
	// The page itself was not zoomed: the grid did.
	expect(await page.evaluate(() => visualViewport?.scale ?? 1)).toBe(1);
});
