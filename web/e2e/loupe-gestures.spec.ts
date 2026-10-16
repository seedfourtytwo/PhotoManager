/** The photo view under the finger: double tap, drag, pinch, and touches that land mid-transition. */
import type { Locator, Page } from '@playwright/test';
import {
	centre,
	expect,
	isPhone,
	loupe,
	NOTHING_HAPPENS_MS,
	resetMock,
	signIn,
	takesInput,
	test,
	touchDown,
	touchSwipe
} from './helpers.ts';

const alt = (viewer: Locator) => viewer.locator('img.photo').getAttribute('alt');

type Frame = { shown: number; next: number; url: string };
/**
 * Records every frame from now on: how many photos are in sight on the stage (more than a
 * tenth of their width each), where the Next button is, and the address. `stop` returns them.
 */
async function frames(page: Page) {
	await page.evaluate(() => {
		const w = window as unknown as { frames$: Frame[]; recording: boolean };
		w.frames$ = [];
		w.recording = true;
		const record = () => {
			if (!w.recording) return;
			const stage = document.querySelector('.stage')!.getBoundingClientRect();
			const shown = [...document.querySelectorAll('.slot .picture')].filter((el) => {
				const r = el.getBoundingClientRect();
				const seen = Math.min(r.right, stage.right) - Math.max(r.left, stage.left);
				return seen > r.width / 10;
			}).length;
			const next = document.querySelector('[aria-label="Next photo"]')!.getBoundingClientRect();
			w.frames$.push({ shown, next: next.x, url: location.href });
			requestAnimationFrame(record);
		};
		requestAnimationFrame(record);
	});
	return () =>
		page.evaluate(() => {
			const w = window as unknown as { frames$: Frame[]; recording: boolean };
			w.recording = false;
			return w.frames$;
		});
}

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

	test('phone: the next photo slides in beside the open one, decoded before it is needed; the address follows after', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const first = await alt(viewer);
		const url = page.url();
		// The neighbour is on the stage before any swipe, its picture decoded and waiting.
		const nextSlot = viewer.locator('.slot[aria-hidden="true"]').last();
		await expect(nextSlot.locator('img:not(.under)')).toHaveAttribute('data-ready', '');
		const screen = page.viewportSize()!.width;
		const from = await centre(viewer.locator('.stage'));
		const lift = await touchDown(page, from, { x: from.x - 150, y: from.y + 60 });
		// Mid-drag: the next photo is in sight at the right edge, and a diagonal finger did not
		// snap the photo back (the drag locked sideways).
		await expect.poll(async () => (await nextSlot.boundingBox())!.x).toBeLessThan(screen);
		await expect
			.poll(async () => Math.round((await nextSlot.boundingBox())!.x))
			.toBeCloseTo(screen - 150 + 16, -1);
		expect(page.url()).toBe(url);
		await lift();
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', first!);
		await expect(page).not.toHaveURL(url);
	});

	test('phone: a quick flick turns the photo, though it went only a little way', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const first = await alt(viewer);
		const from = await centre(viewer.locator('.stage'));
		// 60 px in 32 ms, timed as a phone sends it: far short of a third of the screen, but fast.
		await takesInput(page);
		const cdp = await page.context().newCDPSession(page);
		const start = Date.now() / 1000;
		const touch = (type: 'touchStart' | 'touchMove' | 'touchEnd', dx: number | null, ms: number) =>
			cdp.send('Input.dispatchTouchEvent', {
				type,
				touchPoints: dx === null ? [] : [{ x: from.x + dx, y: from.y }],
				timestamp: start + ms / 1000
			});
		await touch('touchStart', 0, 0);
		await touch('touchMove', -30, 16);
		await touch('touchMove', -60, 32);
		await touch('touchEnd', null, 40);
		await cdp.detach();
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', first!);
	});

	test('phone: before the first photo the drag resists, and springs back', async ({ page }) => {
		test.skip(!isPhone(page), 'touch only');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		// The first tile opens the first photo: nothing before it.
		await expect(viewer.locator('.slot')).toHaveCount(2);
		const frame = viewer.locator('.frame');
		const first = await alt(viewer);
		const rest = (await frame.boundingBox())!.x;
		const from = await centre(frame);
		const lift = await touchDown(page, from, { x: from.x + 150, y: from.y });
		// A third of the finger's way.
		await expect.poll(async () => Math.round((await frame.boundingBox())!.x - rest)).toBe(50);
		await lift();
		await expect
			.poll(async () => Math.round((await frame.boundingBox())!.x))
			.toBe(Math.round(rest));
		expect(await alt(viewer)).toBe(first);
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
		// The edge buttons are not drawn on a touch screen and take no touch; a screen reader
		// (which cannot swipe the photos) still presses them.
		const previous = viewer.getByRole('button', { name: 'Previous photo' });
		await expect(previous).toHaveCSS('clip-path', 'inset(50%)');
		await previous.dispatchEvent('click');
		await expect(viewer.locator('img.photo')).toHaveAttribute('alt', first!);
		await viewer.getByRole('button', { name: 'Next photo' }).dispatchEvent('click');
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
		// A tap on the photo hides the chrome (a finger never hides it by a timer).
		const photo = await centre(viewer.locator('img.photo'));
		await page.touchscreen.tap(photo.x, photo.y);
		await expect(toolbar).toHaveCSS('opacity', '0');
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
		const photo = await centre(viewer.locator('img.photo'));
		await page.touchscreen.tap(photo.x, photo.y);
		await expect(toolbar).toHaveCSS('opacity', '0');
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

	test('laptop: an arrow key slides the next photo in beside the open one; the buttons stay put and the address follows after', async ({
		page
	}) => {
		test.skip(isPhone(page), 'keyboard and edge buttons on a laptop');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const first = await alt(viewer);
		const url = page.url();
		await expect(viewer.locator('.slot img:not(.under)').last()).toHaveAttribute('data-ready', '');
		const stop = await frames(page);
		await page.keyboard.press('ArrowRight');
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', first!);
		const second = await alt(viewer);
		await expect(page).not.toHaveURL(url);
		const seen = await stop();
		// Mid-slide, both photos were in sight together; at rest, only the new one.
		expect(seen.some((f) => f.shown === 2)).toBe(true);
		expect(seen.at(-1)!.shown).toBe(1);
		// The Next button never moved.
		expect(new Set(seen.map((f) => Math.round(f.next))).size).toBe(1);
		// The address changed only once the photo had stopped.
		const moved = seen.findIndex((f) => f.url !== url);
		const lastSliding = seen.findLastIndex((f) => f.shown === 2);
		expect(moved).toBeGreaterThan(lastSliding);
		// The edge button slides back the same way.
		await viewer.getByRole('button', { name: 'Previous photo' }).click();
		await expect(viewer.locator('img.photo')).toHaveAttribute('alt', first!);
		expect(second).not.toBe(first);
	});

	test('laptop: quick arrow presses land on the photo they count to', async ({ page }) => {
		test.skip(isPhone(page), 'keyboard on a laptop');
		const fourth = await page.locator('.tile').nth(3).getAttribute('data-id');
		await page.locator('.tile').first().click();
		await expect(loupe(page)).toBeVisible();
		for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight');
		await expect(page).toHaveURL(new RegExp(`[?&]photo=${fourth}$`));
		// And stays there.
		await page.waitForTimeout(NOTHING_HAPPENS_MS);
		await expect(page).toHaveURL(new RegExp(`[?&]photo=${fourth}$`));
	});

	test('laptop: a two-finger swipe on the trackpad turns the photo', async ({ page }) => {
		test.skip(isPhone(page), 'trackpad on a laptop');
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		const first = await alt(viewer);
		const mid = await centre(viewer.locator('.stage'));
		await page.mouse.move(mid.x, mid.y);
		const stop = await frames(page);
		for (let i = 0; i < 12; i++) {
			await page.mouse.wheel(50, 0);
			await page.waitForTimeout(16);
		}
		await expect(viewer.locator('img.photo')).not.toHaveAttribute('alt', first!);
		await expect(viewer).toBeVisible();
		expect((await stop()).some((f) => f.shown === 2)).toBe(true);
	});
});
