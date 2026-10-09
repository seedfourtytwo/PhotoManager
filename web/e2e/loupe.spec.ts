/**
 * The loupe (the photo view): its bar, chrome that comes back on touch, real swipes, URL state,
 * rights, guarded actions, toasts on top of it, and the view transition from and to the tile.
 */
import type { Page } from '@playwright/test';
import {
	centre,
	expect,
	expectAccessible,
	GUEST,
	isPhone,
	loupeAction,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	toast,
	touchSwipe,
	viewOnlyPhoto
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

	test('a close request from the browser (Back gesture on a phone) closes the loupe', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await expect(page).toHaveURL(/photo=\d+/);
		// What the browser sends for a close request it lets the page handle.
		await loupe(page).evaluate((d) => d.dispatchEvent(new Event('cancel', { cancelable: true })));
		await expect(loupe(page)).toHaveCount(0);
		await expect(page).not.toHaveURL(/photo=/);
	});

	test('if the browser closes the viewer itself, the page follows', async ({ page }) => {
		await page.locator('.tile').first().click();
		await expect(page).toHaveURL(/photo=\d+/);
		// A repeated close request closes a modal dialog without asking the page.
		await loupe(page).evaluate((d) => (d as HTMLDialogElement).close());
		await expect(page.locator('dialog.loupe')).toHaveCount(0);
		await expect(page).not.toHaveURL(/photo=/);
	});

	test('Escape closes the loupe once: it does not also leave the page', async ({ page }) => {
		await page.goto('/albums');
		await page.goto('/');
		await page.locator('.tile').first().click();
		await expect(loupe(page)).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(loupe(page)).toHaveCount(0);
		await page.waitForTimeout(300);
		await expect(page).toHaveURL(/\/$/);
		await expect(page.locator('.tile').first()).toBeVisible();
	});

	test('phone: a tap where a hidden action sits only brings the actions back', async ({ page }) => {
		test.skip(!isPhone(page), 'touch only');
		let patches = 0;
		page.on('request', (r) => {
			if (r.method() === 'PATCH' && r.url().endsWith('/state')) patches++;
		});
		await page.locator('.tile').first().click();
		const toolbar = loupe(page).getByRole('toolbar', {
			name: 'Photo actions',
			includeHidden: true
		});
		const favourite = loupe(page).locator('.top button', { hasText: 'Favourite' });
		const at = await centre(favourite);
		await expect(toolbar).toHaveCSS('opacity', '0', { timeout: 5000 });
		await page.touchscreen.tap(at.x, at.y);
		await expect(toolbar).toHaveCSS('opacity', '1');
		await page.waitForTimeout(300);
		expect(patches).toBe(0);
		await expect(favourite).toHaveAttribute('aria-pressed', 'false');
		// Now that it can be seen, it works.
		await page.touchscreen.tap(at.x, at.y);
		await expect(favourite).toHaveAttribute('aria-pressed', 'true');
		expect(patches).toBe(1);
	});

	test('two folders whose id and path run together both show under Sources', async ({ page }) => {
		test.skip(isPhone(page), 'the sidenote is open by default on a laptop');
		const errors: string[] = [];
		page.on('pageerror', (e) => errors.push(e.message));
		await page.route(/\/api\/assets\/\d+$/, async (route) => {
			const response = await route.fetch();
			const detail = await response.json();
			const origin = detail.origins[0];
			detail.origins = [
				{ ...origin, source_id: 1, relative_path: '23.jpg' },
				{ ...origin, source_id: 12, relative_path: '3.jpg' }
			];
			await route.fulfill({ response, json: detail });
		});
		await page.locator('.tile').first().click();
		const sources = loupe(page).getByRole('complementary', { name: 'About this photo' });
		await expect(sources.getByText('23.jpg', { exact: true })).toBeVisible();
		await expect(sources.getByText('3.jpg', { exact: true })).toBeVisible();
		expect(errors).toEqual([]);
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
		await loupeAction(page, 'Private');
		expect((await patch).postDataJSON()).toEqual({ private: true });
		await loupe(page).getByRole('button', { name: 'More' }).click();
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
	const id = await viewOnlyPhoto(page);
	await page.goto(`/?photo=${id}`);
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
	await loupeAction(page, 'More like this');
	await expect(page).toHaveURL(/\/search\?like=\d+/);
	await expect(page.getByRole('heading', { name: /Like this photo/ })).toBeVisible();
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('trash and albums: a linked photo that is not in the list leaves no trace in the URL', async ({
	page
}) => {
	await resetMock();
	await signIn(page);
	const album = await (
		await page.request.post('/api/albums', { data: { title: 'Nothing linked here' } })
	).json();
	for (const path of ['/trash', `/albums/${album.id}`]) {
		await page.goto('/albums');
		await page.goto(`${path}?photo=999999`);
		await expect(page).toHaveURL(new RegExp(`${path}$`));
		await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toHaveCount(0);
		// One Back leaves the page: no dead entry was left behind.
		await page.goBack();
		await expect(page).toHaveURL(/\/albums$/);
	}
});

test.describe('photo view', () => {
	test.beforeEach(async ({ page }) => {
		await resetMock();
		await signIn(page);
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

	/** The toast is what a finger or a pointer at its middle would hit: in sight, on top, not inert. */
	const expectOnTop = (page: Page) =>
		expect
			.poll(() =>
				toast(page).evaluate((slip) => {
					const box = slip.getBoundingClientRect();
					const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
					return hit !== null && slip.contains(hit);
				})
			)
			.toBe(true);

	test('a toast raised in the photo view shows on top of it, clear of its bar', async ({
		page
	}) => {
		await page.locator('.tile').first().click();
		await loupe(page).getByRole('button', { name: 'Album' }).click();
		const dialog = page.getByRole('dialog', { name: 'Add to album' });
		await dialog.getByLabel('New album title').fill('Toasted');
		await dialog.getByRole('button', { name: 'Add' }).click();
		await expect(toast(page)).toContainText('Created “Toasted” with 1 photo');
		await expect(loupe(page)).toBeVisible();
		await expectOnTop(page);
		// It is announced: a live region inside the modal viewer, which is the only part of the
		// page a screen reader is given.
		expect(await toast(page).evaluate((slip) => slip.closest('dialog')?.ariaLabel)).toBe(
			'Photo viewer'
		);
		const slip = (await toast(page).boundingBox())!;
		const bar = (await loupe(page).locator('.bar').boundingBox())!;
		expect(slip.y + slip.height).toBeLessThan(bar.y);
		// The viewer closes under it: the toast stays for its time.
		await loupe(page).getByRole('button', { name: 'Close' }).click();
		await expect(loupe(page)).toHaveCount(0);
		await expect(toast(page)).toContainText('Created “Toasted”');
		await expectOnTop(page);
	});

	test('a toast that is showing when a photo opens moves on top of the photo view', async ({
		page
	}) => {
		await selectTiles(page, [0]);
		await selectionAction(page, 'Favourite');
		await expect(toast(page)).toContainText('Marked as favourites.');
		await page.getByRole('button', { name: 'Clear selection' }).click();
		await page.locator('.tile').nth(1).click();
		await expect(loupe(page)).toBeVisible();
		await expect(toast(page)).toContainText('Marked as favourites.');
		await expectOnTop(page);
	});

	test('fixing the date of the open photo keeps the photo view open', async ({ page }) => {
		await page.locator('.tile').nth(2).click();
		const viewer = loupe(page);
		await expect(viewer).toBeVisible();
		const url = page.url();
		// The very same viewer afterwards, not one that closed and opened again.
		await viewer.evaluate((el) => ((el as HTMLElement).dataset.kept = 'yes'));
		const removed = page.evaluate(
			() =>
				new Promise<boolean>((resolve) => {
					const dialog = document.querySelector('dialog[aria-label="Photo viewer"]')!;
					new MutationObserver(() => !dialog.isConnected && resolve(true)).observe(document.body, {
						childList: true,
						subtree: true
					});
					setTimeout(() => resolve(false), 2500);
				})
		);
		await loupeAction(page, 'Fix date');
		const dialog = page.getByRole('dialog', { name: 'Fix date' });
		await dialog.getByLabel('Set exactly').check();
		await dialog.getByLabel('Date and time').fill('2001-02-03T04:05:06');
		await dialog.getByRole('button', { name: 'Change date' }).click();
		await expect(toast(page)).toContainText('Changed the date of 1 photo');
		await expect(viewer.locator('.readout')).toContainText('2001-02-03 · 04:05');
		expect(await removed).toBe(false);
		await expect(viewer).toHaveAttribute('data-kept', 'yes');
		expect(page.url()).toBe(url);
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
