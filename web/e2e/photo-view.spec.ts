/** Redesign step 3 (spec §4.3–4.5): the photo view's bar and gestures, the time ruler, the selection pill. */
import type { Locator, Page } from '@playwright/test';
import {
	centre,
	expect,
	expectAccessible,
	isPhone,
	resetMock,
	selectTiles,
	signIn,
	test,
	toast,
	touchDown,
	touchSwipe,
	transitionOver
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
		await transitionOver(page);
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

	test('opening and closing run a view transition between the tile and the photo', async ({
		page
	}) => {
		await page.addInitScript(() => {
			const real = document.startViewTransition.bind(document);
			const seen = window as unknown as { transitions: number };
			seen.transitions = 0;
			document.startViewTransition = (...args: Parameters<typeof real>) => {
				seen.transitions++;
				return real(...args);
			};
		});
		await page.goto('/');
		const transitions = () =>
			page.evaluate(() => (window as unknown as { transitions: number }).transitions);
		const tile = page.locator('.tile').first();
		await tile.click();
		await expect(loupe(page).locator('.frame')).toHaveCSS('view-transition-name', 'photo');
		expect(await transitions()).toBe(1);
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(loupe(page)).toHaveCount(0);
		expect(await transitions()).toBe(2);
		// The tile only borrows the name for the length of the transition.
		await expect(tile).not.toHaveAttribute('style', /view-transition-name/);
		await expect(tile).toBeFocused();
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

test.describe('time ruler', () => {
	const ruler = (page: Page) => page.getByRole('slider', { name: 'Jump to date' });

	test('laptop: the ruler is a column of years at the right edge with the needle on the month in view', async ({
		page
	}) => {
		test.skip(isPhone(page), 'the phone has it lying above the dock');
		await expect(ruler(page)).toHaveAttribute('aria-orientation', 'vertical');
		const box = (await ruler(page).boundingBox())!;
		expect(box.height).toBeGreaterThan(box.width * 4);
		// The needle's tag reads the month whose photos are at the top, in the data face.
		const month = (await ruler(page).getAttribute('aria-valuetext'))!;
		await expect(page.locator('section h2').first()).toContainText(month);
		const tag = ruler(page).locator('.tag');
		await expect(tag).toHaveText(`${month.slice(0, 3)} ${month.slice(-4)}`);
		await expect(tag).toHaveCSS('font-family', /Martian Mono/);
		// A tap on a written year goes there.
		await ruler(page).getByText('2019', { exact: true }).click();
		await expect(page.locator('section h2', { hasText: '2019' }).first()).toBeInViewport();
		await expect(ruler(page)).toHaveAttribute('aria-valuetext', /2019$/);
		await expectAccessible(page);
	});

	test('phone: the time ruler shows while scrolling, fades when idle, and a drag along it jumps', async ({
		page
	}) => {
		test.skip(!isPhone(page), 'the laptop has it upright, always in sight');
		await expect(page.locator('.tile').first()).toBeVisible();
		await expect(ruler(page)).toHaveAttribute('aria-orientation', 'horizontal');
		await expect(ruler(page)).toHaveCSS('opacity', '0');
		await page.evaluate(() => window.scrollBy(0, 600));
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		await expectAccessible(page);
		// The check above took its time: scroll again, so the ruler is there to be dragged.
		await page.evaluate(() => window.scrollBy(0, 200));
		await expect(ruler(page)).toHaveCSS('opacity', '1');
		// It lies above the dock (56 px, plus the gap under it).
		const box = (await ruler(page).boundingBox())!;
		expect(box.width).toBeGreaterThan(box.height * 4);
		expect(box.y + box.height).toBeLessThan(page.viewportSize()!.height - 56);
		// Time runs left to right: a drag to the left end goes to the oldest photos.
		const y = box.y + box.height / 2;
		await touchSwipe(page, { x: box.x + box.width - 12, y }, { x: box.x + 2, y });
		await expect(page.locator('section h2', { hasText: '2012' }).last()).toBeInViewport();
		await expect(ruler(page)).toHaveCSS('opacity', '0', { timeout: 10_000 });
	});
});

test.describe('selection pill', () => {
	const pill = (page: Page) => page.getByRole('toolbar', { name: 'Selected photos' });

	test('the selection bar is a floating pill at the bottom centre', async ({ page }) => {
		await selectTiles(page, [0, 1]);
		await expect(pill(page)).toHaveCSS('position', 'fixed');
		await expect(pill(page)).toHaveCSS('border-radius', '999px');
		const box = (await pill(page).boundingBox())!;
		const { width, height } = page.viewportSize()!;
		expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThan(2);
		expect(box.x).toBeGreaterThan(4);
		const below = height - (box.y + box.height);
		expect(below).toBeGreaterThan(8);
		expect(below).toBeLessThan(isPhone(page) ? 120 : 60);
		await expect(pill(page).getByRole('status')).toHaveText('2 selected');
		await expectAccessible(page);
	});

	test('the pill offers Add to album, Download, Fix date, Move to trash and More', async ({
		page
	}) => {
		await selectTiles(page, [0]);
		const actions = pill(page).locator('.actions > button');
		// A 390 px phone has room for two beside the count and Clear; the others join the rest
		// under More.
		const onBar = ['Add to album', 'Download', 'Fix date', 'Move to trash'].slice(
			0,
			isPhone(page) ? 2 : 4
		);
		await expect(actions).toHaveText([...onBar, 'More']);
		await expect(actions.locator('svg')).toHaveCount(onBar.length + 1);
		const more = pill(page).getByRole('button', { name: 'More' });
		await more.click();
		for (const name of ['Favourite', 'Hide', 'Make private'])
			await expect(pill(page).getByRole('button', { name, exact: true })).toBeVisible();
		await expect(pill(page).getByRole('button', { name: 'Move to trash' })).toBeVisible();
		// Escape closes More first, then clears the selection.
		await page.keyboard.press('Escape');
		await expect(more).toHaveAttribute('aria-expanded', 'false');
		await expect(pill(page)).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(pill(page)).toHaveCount(0);
		await expect(page.locator('.tile.selected')).toHaveCount(0);
	});

	// From the narrowest phone up: what does not fit goes under More, nothing leaves the glass.
	for (const width of [320, 390, 700])
		test(`at ${width} px everything on the pill is inside it, and the pill inside the screen`, async ({
			page
		}) => {
			test.skip(isPhone(page), 'one project sets the widths itself');
			await page.setViewportSize({ width, height: 800 });
			await page.getByRole('button', { name: /^Select (all|loaded)/ }).click();
			await expect(pill(page).getByRole('status')).toHaveText(/^\d{3} selected$/);
			const glass = (await pill(page).boundingBox())!;
			expect(glass.x).toBeGreaterThanOrEqual(0);
			expect(glass.x + glass.width).toBeLessThanOrEqual(width);
			const inside = pill(page).locator('.count, .actions > button, .clear');
			for (const part of await inside.all()) {
				const box = (await part.boundingBox())!;
				expect(box.x).toBeGreaterThanOrEqual(glass.x);
				expect(box.x + box.width).toBeLessThanOrEqual(glass.x + glass.width);
			}
			await expect(pill(page).getByRole('button', { name: 'Clear selection' })).toBeVisible();
			// Whatever left the pill is still offered, under More.
			await pill(page).getByRole('button', { name: 'More' }).click();
			for (const name of ['Add to album', 'Download', 'Fix date', 'Move to trash'])
				await expect(pill(page).getByRole('button', { name, exact: true })).toBeVisible();
		});

	test('phone: long-press then drag selects a run of photos', async ({ page }) => {
		test.skip(!isPhone(page), 'touch only');
		const tiles = page.locator('.tile');
		const from = await centre(tiles.nth(0));
		const to = await centre(tiles.nth(3));
		const lift = await touchDown(page, from, to, { hold: 600 });
		await expect(page.getByText('4 selected')).toBeVisible();
		await lift();
		// The page stayed put under the finger, and lifting it changes nothing.
		expect(await page.evaluate(() => window.scrollY)).toBe(0);
		await expect(page.getByText('4 selected')).toBeVisible();
		await expect(page.locator('.tile.selected')).toHaveCount(4);
	});
});
