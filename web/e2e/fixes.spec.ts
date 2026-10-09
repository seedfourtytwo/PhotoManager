/** Small fixes from the E2E review that have no journey of their own. */
import {
	expect,
	isPhone,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	toast
} from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('counts follow a hide: the header and the filter panel', async ({ page }) => {
	const meta = page.locator('header .meta');
	await expect(meta).toContainText(/[\d,]+ photos/);
	const before = Number((await meta.textContent())!.match(/([\d,]+) photos/)![1].replace(',', ''));
	if (isPhone(page)) await page.getByRole('button', { name: 'Filter', exact: true }).click();
	const panel = page.getByRole('complementary', { name: 'Filters' });
	await expect(panel.locator('.total')).toContainText(`${before}`);
	if (isPhone(page)) await panel.getByRole('button', { name: 'Done' }).click();
	await selectTiles(page, [0]);
	await selectionAction(page, 'Hide');
	await expect(meta).toContainText(`${before - 1} photos`);
	if (isPhone(page)) await page.getByRole('button', { name: 'Filter', exact: true }).click();
	await expect(panel.locator('.total')).toContainText(`${before - 1}`);
});

test('a double click on Move to trash trashes once', async ({ page }) => {
	test.skip(isPhone(page), 'double click');
	let deletes = 0;
	await page.route('**/api/assets', async (route) => {
		if (route.request().method() === 'DELETE') {
			deletes++;
			await new Promise((r) => setTimeout(r, 300));
		}
		await route.continue();
	});
	await selectTiles(page, [0]);
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'Move to trash' })
		.dblclick();
	await expect(toast(page)).toContainText('Moved 1 photo to the trash');
	expect(deletes).toBe(1);
	await expect(toast(page)).not.toContainText(/not found/i);
});

test('the two Hide buttons have different names', async ({ page }) => {
	test.skip(isPhone(page), 'the filter panel is a sheet on phones');
	await selectTiles(page, [0]);
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'More' })
		.click();
	await expect(page.getByRole('button', { name: 'Hide', exact: true })).toHaveCount(1);
	await expect(page.getByRole('button', { name: 'Hide filters' })).toHaveCount(1);
});

test('sliders are wide enough to use', async ({ page }) => {
	await page.locator('.tile').first().click();
	await page.getByRole('button', { name: 'Download' }).click();
	await page.getByLabel('JPEG').check();
	const slider = page.getByRole('dialog', { name: 'Download photo' }).getByRole('slider');
	expect((await slider.boundingBox())!.width).toBeGreaterThan(100);
});

test('dark is the default theme, even on a light system', async ({ browser }) => {
	const context = await browser.newContext({ colorScheme: 'light' });
	const page = await context.newPage();
	await signIn(page);
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
	const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
	expect(bg).toBe('rgb(13, 15, 18)'); // --bg, dark (themes.css)
	await context.close();
});
