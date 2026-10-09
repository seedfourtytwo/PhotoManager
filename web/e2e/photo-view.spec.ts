/** Redesign step 3 (spec §4.3–4.5): the photo view's bar and gestures, the time ruler, the selection pill. */
import type { Locator, Page } from '@playwright/test';
import {
	centre,
	expect,
	expectAccessible,
	isPhone,
	resetMock,
	signIn,
	test,
	toast,
	touchDown,
	touchSwipe
} from './helpers.ts';

const loupe = (page: Page) => page.getByRole('dialog', { name: 'Photo viewer' });
const alt = (viewer: Locator) => viewer.locator('img.photo').getAttribute('alt');

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test.describe('photo view', () => {
	test('phone: a double tap on the photo favourites it, like the Favourite button', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const favourite = loupe(page).getByRole('button', { name: 'Favourite' });
		await expect(favourite).toHaveAttribute('aria-pressed', 'false');
		const photo = await centre(loupe(page).locator('img.photo'));
		await page.touchscreen.tap(photo.x, photo.y);
		await page.touchscreen.tap(photo.x, photo.y);
		await expect(favourite).toHaveAttribute('aria-pressed', 'true');
		// The double tap leaves the bar in sight, and its button takes the favourite back.
		await expect(loupe(page).getByRole('toolbar', { name: 'Photo actions' })).toHaveCSS(
			'opacity',
			'1'
		);
		await favourite.tap();
		await expect(favourite).toHaveAttribute('aria-pressed', 'false');
	});

	test('phone: the photo follows the finger and springs back from a short drag', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const frame = loupe(page).locator('.frame');
		const was = await alt(loupe(page));
		const rest = (await frame.boundingBox())!.x;
		const from = await centre(frame);
		const lift = await touchDown(page, from, { x: from.x - 40, y: from.y });
		await expect.poll(async () => (await frame.boundingBox())!.x).toBeLessThan(rest - 20);
		await lift();
		await expect
			.poll(async () => Math.round((await frame.boundingBox())!.x))
			.toBe(Math.round(rest));
		expect(await alt(loupe(page))).toBe(was);
	});

	test('phone: each gesture and its button reach the same state', async ({ page }) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const photo = await centre(viewer.locator('.stage'));
		const first = await alt(viewer);

		// Sideways: the swipe and the edge buttons step the same way.
		await touchSwipe(page, photo, { x: photo.x - 200, y: photo.y });
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', first!);
		const second = await alt(viewer);
		await viewer.getByRole('button', { name: 'Previous photo' }).click();
		await expect(viewer.locator('img.photo')).toHaveAttribute('alt', first!);
		await viewer.getByRole('button', { name: 'Next photo' }).click();
		await expect(viewer.locator('img.photo')).toHaveAttribute('alt', second!);
		await touchSwipe(page, photo, { x: photo.x + 200, y: photo.y });
		await expect(viewer.locator('img.photo')).toHaveAttribute('alt', first!);

		// Up for the details, and Info.
		const details = viewer.getByRole('complementary', { name: 'About this photo' });
		const info = viewer.getByRole('button', { name: 'Info' });
		await touchSwipe(page, photo, { x: photo.x, y: photo.y - 200 });
		await expect(details).toBeVisible();
		await expect(info).toHaveAttribute('aria-pressed', 'true');
		await info.click();
		await expect(details).toHaveCount(0);
		await info.click();
		await expect(details).toBeVisible();
		await touchSwipe(page, { x: photo.x, y: 150 }, { x: photo.x, y: 400 });
		await expect(details).toHaveCount(0);

		// Down to close, and Close.
		await touchSwipe(page, { x: photo.x, y: 150 }, { x: photo.x, y: 450 });
		await expect(viewer).toHaveCount(0);
		await page.locator('.tile').first().click();
		await viewer.getByRole('button', { name: 'Close' }).click();
		await expect(viewer).toHaveCount(0);
	});

	test('the bar reads the photo’s date, time and file name in the data face', async ({ page }) => {
		await page.locator('.tile').first().click();
		const readout = loupe(page).locator('.readout');
		await expect(readout).toContainText(/\d{4}-\d{2}-\d{2} · \d{2}:\d{2}/);
		await expect(readout).toContainText(/\d+ × \d+ · \S+\.\w{3,4}$/);
		await expect(readout).toHaveCSS('font-family', /Martian Mono/);
	});

	test('the bar holds Favourite, Download, Album, Edit and More; More holds the rest', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		const bar = loupe(page).locator('.bar');
		const actions = bar.locator('.acts > button, .acts > .menu > button');
		await expect(actions).toHaveText(['Favourite', 'Download', 'Album', 'Edit', 'More']);
		await expect(actions.locator('svg')).toHaveCount(5);
		await expect(bar.getByRole('button', { name: 'Fix date' })).toHaveCount(0);
		await bar.getByRole('button', { name: 'More' }).click();
		await expect(bar.getByRole('button', { name: 'Private' })).toBeVisible();
		await expect(bar.getByRole('button', { name: 'Fix date' })).toBeVisible();
		await expectAccessible(page);
	});

	test('Album adds the open photo to an album', async ({ page }) => {
		await page.locator('.tile').first().click();
		await loupe(page).getByRole('button', { name: 'Album' }).click();
		const dialog = page.getByRole('dialog', { name: 'Add to album' });
		await expect(dialog.getByText('1 photo', { exact: true })).toBeVisible();
		await dialog.getByLabel('New album title').fill('From the photo view');
		await dialog.getByRole('button', { name: 'Add' }).click();
		await expect(toast(page)).toContainText('Created “From the photo view” with 1 photo');
		await expect(loupe(page)).toBeVisible();
		if (!isPhone(page))
			await expect(loupe(page).getByRole('link', { name: 'From the photo view' })).toBeVisible();
	});

	test('Escape closes More, not the photo view', async ({ page }) => {
		test.skip(isPhone(page), 'keyboard');
		await page.locator('.tile').first().click();
		const more = loupe(page).getByRole('button', { name: 'More' });
		await more.click();
		await expect(more).toHaveAttribute('aria-expanded', 'true');
		await page.keyboard.press('Escape');
		await expect(more).toHaveAttribute('aria-expanded', 'false');
		await expect(loupe(page)).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(loupe(page)).toHaveCount(0);
	});
});
