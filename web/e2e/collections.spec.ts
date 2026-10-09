import { expect, expectAccessible, resetMock, signIn, test } from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

test('collections: people, places and albums show what is in them, and each leads there', async ({
	page
}) => {
	await signIn(page, '/collections');
	const main = page.getByRole('main');
	const sam = main.getByRole('link', { name: /^Sam \d+ photos$/ });
	const album = main.getByRole('link', { name: /^Summers at the house \d+ photos$/ });
	await expect(sam).toBeVisible();
	await expect(album).toBeVisible();
	await expect(main.getByRole('link', { name: /^Carnac \d+ photos$/ })).toBeVisible();
	// a cover is a real picture, not an empty frame
	await expect
		.poll(() => album.locator('img').evaluate((img: HTMLImageElement) => img.naturalWidth))
		.toBeGreaterThan(0);
	await expectAccessible(page);

	await sam.click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	await expect(page.getByRole('heading', { level: 1, name: 'Sam' })).toBeVisible();
	await page.goBack();
	await album.click();
	await expect(page).toHaveURL(/\/albums\/\d+$/);
	await expect(page.getByRole('heading', { level: 1, name: 'Summers at the house' })).toBeVisible();
});

test('collections: a place opens the library filtered by that place', async ({ page }) => {
	await signIn(page, '/collections');
	const place = page.getByRole('main').getByRole('link', { name: /^Carnac (\d+) photos$/ });
	const count = /(\d+) photos/.exec((await place.textContent()) ?? '')?.[1];
	await place.click();
	await expect(page).toHaveURL(/\/\?place=Carnac$/);
	await expect(page.getByRole('main')).toContainText(`${count} photos`);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('collections: nothing on the page is wider than the screen', async ({ page }) => {
	await signIn(page, '/collections');
	await expect(page.getByRole('main').getByRole('link', { name: /^Sam / })).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBe(0);
});
