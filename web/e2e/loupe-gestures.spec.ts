/** The photo view under the finger: double tap, drag, pinch, and touches that land mid-transition. */
import type { Locator } from '@playwright/test';
import {
	centre,
	expect,
	isPhone,
	loupe,
	resetMock,
	signIn,
	takesInput,
	test,
	touchDown,
	touchSwipe
} from './helpers.ts';

const alt = (viewer: Locator) => viewer.locator('img.photo').getAttribute('alt');

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test.describe('photo view', () => {
	test('phone: a double tap zooms in on the photo and the next one zooms back out; neither favourites it', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		let patches = 0;
		await page.route(/\/api\/assets\/\d+\/state$/, async (route) => {
			patches++;
			await route.continue();
		});
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const frame = viewer.locator('.frame');
		const fit = (await frame.boundingBox())!.width;
		const photo = await centre(viewer.locator('img.photo'));
		await takesInput(page);
		await page.touchscreen.tap(photo.x, photo.y);
		await page.touchscreen.tap(photo.x, photo.y);
		await expect.poll(async () => (await frame.boundingBox())!.width).toBeCloseTo(fit * 2.5, 0);
		// Zoomed in, the photo has the screen to itself.
		await expect(viewer.getByRole('toolbar', { name: 'Photo actions' })).toHaveCSS('opacity', '0');
		await page.touchscreen.tap(photo.x, photo.y);
		await page.touchscreen.tap(photo.x, photo.y);
		await expect.poll(async () => (await frame.boundingBox())!.width).toBeCloseTo(fit, 0);
		await expect(viewer.getByRole('toolbar', { name: 'Photo actions' })).toHaveCSS('opacity', '1');
		await expect(viewer.getByRole('button', { name: 'Favourite' })).toHaveAttribute(
			'aria-pressed',
			'false'
		);
		expect(patches).toBe(0);
	});

	test('phone: a zoomed photo moves under one finger, stops at its edge, and does not step', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const frame = viewer.locator('.frame');
		const was = await alt(viewer);
		const mid = await centre(viewer.locator('.stage'));
		const fit = (await frame.boundingBox())!.width;
		await viewer.getByRole('button', { name: 'Zoom' }).click();
		await expect(viewer.getByRole('button', { name: 'Zoom' })).toHaveAttribute(
			'aria-pressed',
			'true'
		);
		const screen = page.viewportSize()!.width;
		const box = async () => (await frame.boundingBox())!;
		// Zoomed all the way in and come to rest, before anything is measured from it.
		await expect.poll(async () => (await box()).width).toBeCloseTo(fit * 2.5, 0);
		const rest = (await box()).x;
		await touchSwipe(page, mid, { x: mid.x - 120, y: mid.y });
		await expect.poll(async () => Math.round((await box()).x)).toBe(Math.round(rest - 120));
		// A long way further: the photo's right edge stops at the screen's.
		for (let i = 0; i < 4; i++) await touchSwipe(page, mid, { x: mid.x - 300, y: mid.y });
		await expect.poll(async () => Math.round((await box()).x + (await box()).width)).toBe(screen);
		expect(await alt(viewer)).toBe(was);
		await expect(viewer).toBeVisible();
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

		// Up for the details, and Details.
		const details = viewer.getByRole('complementary', { name: 'Details' });
		const info = viewer.getByRole('button', { name: 'Details' });
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

	test('phone: a touch on hidden chrome that slides away does not eat the next tap', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const toolbar = viewer.getByRole('toolbar', { name: 'Photo actions' });
		const close = viewer.getByRole('button', { name: 'Close' });
		await expect(toolbar).toHaveCSS('opacity', '0', { timeout: 10_000 });
		// A finger lands on the hidden Close and slides off: the chrome is back, nothing pressed.
		const at = await centre(close);
		await (
			await touchDown(page, at, { x: at.x + 150, y: at.y })
		)();
		await expect(toolbar).toHaveCSS('opacity', '1');
		await expect(viewer).toBeVisible();
		// What is in sight can be pressed.
		await page.touchscreen.tap(at.x, at.y);
		await expect(viewer).toHaveCount(0);
	});

	test('phone: the tap that brings the chrome back does not press the button under it', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const toolbar = viewer.getByRole('toolbar', { name: 'Photo actions' });
		await expect(toolbar).toHaveCSS('opacity', '0', { timeout: 10_000 });
		const at = await centre(viewer.getByRole('button', { name: 'Close' }));
		await page.touchscreen.tap(at.x, at.y);
		await expect(toolbar).toHaveCSS('opacity', '1');
		await expect(viewer).toBeVisible();
		await page.touchscreen.tap(at.x, at.y);
		await expect(viewer).toHaveCount(0);
	});

	test('phone: a pinch zooms the photo; it neither steps to another photo nor closes the view', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const was = await alt(viewer);
		const fit = (await viewer.locator('.frame').boundingBox())!.width;
		const mid = await centre(viewer.locator('.stage'));
		await takesInput(page);
		const cdp = await page.context().newCDPSession(page);
		const fingers = (spread: number, lift = 0) =>
			[
				{ id: 1, x: mid.x - 30 - spread, y: mid.y + lift },
				{ id: 2, x: mid.x + 30 + spread, y: mid.y + lift }
			] as const;
		await cdp.send('Input.dispatchTouchEvent', {
			type: 'touchStart',
			touchPoints: [fingers(0)[0]]
		});
		await cdp.send('Input.dispatchTouchEvent', {
			type: 'touchStart',
			touchPoints: [...fingers(0)]
		});
		// Apart and down together, as a pinch that drifts: far past every swipe threshold.
		for (let i = 1; i <= 8; i++)
			await cdp.send('Input.dispatchTouchEvent', {
				type: 'touchMove',
				touchPoints: [...fingers(i * 15, i * 15)]
			});
		await cdp.send('Input.dispatchTouchEvent', {
			type: 'touchEnd',
			touchPoints: [fingers(120, 120)[0]]
		});
		await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
		await cdp.detach();
		await expect(viewer).toBeVisible();
		expect(await alt(viewer)).toBe(was);
		// Fingers that ended five times as far apart: as large as a photo goes, four times.
		await expect
			.poll(async () => (await viewer.locator('.frame').boundingBox())!.width)
			.toBeCloseTo(fit * 4, 0);
		// Back at its fit, one finger swipes again.
		await page.touchscreen.tap(mid.x, mid.y);
		await page.touchscreen.tap(mid.x, mid.y);
		await expect
			.poll(async () => (await viewer.locator('.frame').boundingBox())!.width)
			.toBeCloseTo(fit, 0);
		await touchSwipe(page, mid, { x: mid.x - 200, y: mid.y });
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', was!);
	});

	test('phone: touches made while the photo view is still opening count', async ({ page }) => {
		test.skip(!isPhone(page), 'touch only');
		// The transition, made long enough to be touched for certain.
		await page.addStyleTag({
			content: `::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) {
				animation-duration: 4s !important;
			}`
		});
		const opening = () =>
			page.evaluate(() => document.documentElement.matches(':active-view-transition'));
		const viewer = loupe(page);
		// A tap on Close.
		await page.locator('.tile').first().click();
		await expect(viewer).toBeVisible();
		const close = await centre(viewer.getByRole('button', { name: 'Close' }));
		await takesInput(page);
		expect(await opening()).toBe(true);
		await page.touchscreen.tap(close.x, close.y);
		await expect(viewer).toHaveCount(0);
		await expect.poll(opening).toBe(false);
		// A swipe to the next photo.
		await page.locator('.tile').first().click();
		await expect(viewer).toBeVisible();
		const first = await alt(viewer);
		const photo = await centre(viewer.locator('.stage'));
		expect(await opening()).toBe(true);
		await touchSwipe(page, photo, { x: photo.x - 200, y: photo.y });
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', first!);
	});
});
