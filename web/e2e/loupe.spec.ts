/** The loupe: chrome that comes back on touch, real swipes, URL state, rights, guarded actions. */
import {
	centre,
	expect,
	expectAccessible,
	GUEST,
	isPhone,
	resetMock,
	signIn,
	test,
	touchSwipe
} from './helpers.ts';

const loupe = (page: import('@playwright/test').Page) =>
	page.getByRole('dialog', { name: 'Photo viewer' });

test.describe('as admin', () => {
	test.beforeEach(async ({ page }) => {
		await resetMock();
		await signIn(page);
	});

	test('phone: idle chrome comes back on a tap, and a tap on the photo toggles it', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const toolbar = loupe(page).getByRole('toolbar', { name: 'Photo actions' });
		await expect(toolbar).toHaveCSS('opacity', '0', { timeout: 5000 });
		const photo = await centre(loupe(page).locator('img.photo'));
		await page.touchscreen.tap(photo.x, photo.y);
		await expect(toolbar).toHaveCSS('opacity', '1');
		await page.touchscreen.tap(photo.x, photo.y);
		await expect(toolbar).toHaveCSS('opacity', '0');
		await page.touchscreen.tap(photo.x, photo.y);
		await expect(toolbar).toHaveCSS('opacity', '1');
		await toolbar.getByRole('button', { name: 'Close' }).tap();
		await expect(loupe(page)).toHaveCount(0);
	});

	test('phone: real vertical swipes show info (up) and close (down)', async ({ page }) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const photo = await centre(loupe(page).locator('.stage'));
		await touchSwipe(page, photo, { x: photo.x, y: photo.y - 200 });
		await expect(
			loupe(page).getByRole('complementary', { name: 'About this photo' })
		).toBeVisible();
		await touchSwipe(page, { x: photo.x, y: 150 }, { x: photo.x, y: 400 });
		await expect(loupe(page).getByRole('complementary')).toHaveCount(0);
		const alt = await loupe(page).locator('img.photo').getAttribute('alt');
		await touchSwipe(page, photo, { x: photo.x - 200, y: photo.y });
		await expect(loupe(page).locator('img.photo')).not.toHaveAttribute('alt', alt!);
		await touchSwipe(page, { x: photo.x, y: 150 }, { x: photo.x, y: 450 });
		await expect(loupe(page)).toHaveCount(0);
	});

	test('the open photo is in the URL: reload keeps it, closing returns focus to its tile', async ({
		page
	}) => {
		const second = page.locator('.tile').nth(1);
		const id = await second.getAttribute('data-id');
		await second.click();
		await expect(page).toHaveURL(new RegExp(`[?&]photo=${id}$`));
		await page.reload();
		await expect(loupe(page)).toBeVisible();
		await expect(page).toHaveURL(new RegExp(`photo=${id}`));
		// Step to the next photo, then close: the grid shows and focuses that photo's tile.
		await loupe(page).getByRole('button', { name: 'Next photo' }).click();
		await expect(page).not.toHaveURL(new RegExp(`photo=${id}$`));
		const current = new URL(page.url()).searchParams.get('photo');
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(loupe(page)).toHaveCount(0);
		await expect(page).not.toHaveURL(/photo=/);
		const tile = page.locator(`.tile[data-id="${current}"]`);
		await expect(tile).toBeFocused();
		await expect(tile).toBeInViewport();
	});

	test('a deep photo far down the timeline reopens from its URL', async ({ page }) => {
		await page.goto('/?year=2012');
		const last = page.locator('.tile').last();
		const id = await last.getAttribute('data-id');
		await page.goto(`/?photo=${id}`);
		await expect(loupe(page)).toBeVisible();
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(page.locator(`.tile[data-id="${id}"]`)).toBeFocused();
	});

	test('favourite: a double click sends one request and ends favourited', async ({ page }) => {
		let patches = 0;
		await page.route(/\/api\/assets\/\d+\/state$/, async (route) => {
			patches++;
			await new Promise((r) => setTimeout(r, 300));
			await route.continue();
		});
		await page.locator('.tile').first().click();
		const fav = loupe(page).getByRole('button', { name: 'Favourite' });
		await fav.dblclick();
		await expect(fav).toHaveAttribute('aria-pressed', 'true');
		await page.waitForTimeout(500);
		expect(patches).toBe(1);
	});

	test('owner/admin can make a photo private from the loupe', async ({ page }) => {
		await page.locator('.tile').first().click();
		const toggle = loupe(page).getByRole('button', { name: 'Private' });
		const patch = page.waitForRequest((r) => r.method() === 'PATCH' && r.url().endsWith('/state'));
		await toggle.click();
		expect((await patch).postDataJSON()).toEqual({ private: true });
		await expect(toggle).toHaveAttribute('aria-pressed', 'true');
		await expectAccessible(page);
	});
});

test('guest: view-only photos say why they cannot be downloaded; no edit or private', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/', GUEST);
	// The guest sees the old disk (view only) and the phone (download).
	await page.goto('/?source_id=2&to=2015-12-31');
	await page.locator('.tile').first().click();
	const dialog = loupe(page);
	await expect(dialog.getByRole('button', { name: 'Download' })).toBeDisabled();
	await expect(dialog.getByText('view only', { exact: true })).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Edit' })).toHaveCount(0);
	await expect(dialog.getByRole('button', { name: 'Fix date' })).toHaveCount(0);
	await expect(dialog.getByRole('button', { name: 'Private' })).toHaveCount(0);
});

test('more like this, when the models are installed', async ({ page }) => {
	await resetMock('seed', { models: true });
	await signIn(page);
	await page.locator('.tile').first().click();
	await loupe(page).getByRole('button', { name: 'More like this' }).click();
	await expect(page).toHaveURL(/\/search\?like=\d+/);
	await expect(page.getByRole('heading', { name: /Like this photo/ })).toBeVisible();
	await expect(page.locator('.tile').first()).toBeVisible();
});
