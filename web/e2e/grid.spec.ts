/** The library grid: scrubber jumps, keyboard navigation, and loading only what is needed. */
import { expect, isPhone, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('the scrubber lands at the start of a month, also when jumping back up', async ({ page }) => {
	test.skip(isPhone(page), 'desktop only');
	const scrubber = page.getByRole('slider', { name: 'Jump to date' });
	await scrubber.focus();
	await page.keyboard.press('End');
	await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
	for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowUp');
	const key = await scrubber.getAttribute('aria-valuetext');
	const section = page
		.locator('section')
		.filter({ has: page.getByRole('heading', { name: key! }) });
	await expect
		.poll(async () => (await section.boundingBox())!.y, { message: 'section top near the top' })
		.toBeLessThan(80);
	expect((await section.boundingBox())!.y).toBeGreaterThan(-10);
	await expect(section.locator('.tile').first()).toBeInViewport();
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

test('first load fetches one page, and facets only once the filters are open', async ({ page }) => {
	const pages: string[] = [];
	const facets: string[] = [];
	page.on('request', (r) => {
		if (/\/api\/assets\?/.test(r.url())) pages.push(r.url());
		if (r.url().includes('/api/assets/facets')) facets.push(r.url());
	});
	await page.goto('/');
	await expect(page.locator('.tile img').first()).toBeVisible();
	await page.waitForTimeout(1500);
	expect(pages).toHaveLength(1);
	if (isPhone(page)) {
		expect(facets).toHaveLength(0);
		await page.getByRole('button', { name: 'Filter', exact: true }).click();
		await expect.poll(() => facets.length).toBeGreaterThan(0);
	} else {
		await expect.poll(() => facets.length).toBeGreaterThan(0);
	}
});

test('only photos within about a screen and a half are in the page', async ({ page }) => {
	await expect(page.locator('.tile').first()).toBeVisible();
	const height = 300;
	await page.setViewportSize({ width: page.viewportSize()!.width, height });
	await page.evaluate(() => window.scrollTo(0, 1500));
	await page.waitForTimeout(400);
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
