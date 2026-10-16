import type { Page } from '@playwright/test';
import {
	centre,
	expect,
	expectAccessible,
	GUEST,
	isPhone,
	longPress,
	loupe,
	loupeAction,
	REAL_BACKEND,
	resetMock,
	scrollToTile,
	selectEverything,
	selectionAction,
	selectTiles,
	signIn,
	takesInput,
	test,
	toast,
	touchDown,
	viewOnlyPhoto
} from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	await signIn(page);
});

test('download dialog: estimate, options, and the streamed ZIP request body', async ({ page }) => {
	const ids = await Promise.all(
		[0, 1].map(async (i) => Number(await page.locator('.tile').nth(i).getAttribute('data-id')))
	);
	await selectTiles(page, [0, 1]);
	await selectionAction(page, 'Download');
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByText(/2 selected photos, about [\d.]+ [KMG]B/)).toBeVisible();
	await expectAccessible(page);

	await dialog.getByRole('button', { name: 'More options' }).click();
	await dialog.getByLabel('JPEG').check();
	await dialog.getByLabel('2048').check();
	await dialog.getByLabel('Remove location').check();
	await dialog.getByLabel('Names').selectOption('date');
	await dialog.getByLabel('Folders').selectOption('year');

	const post = page.waitForRequest(
		(r) => r.method() === 'POST' && r.url().endsWith('/api/downloads')
	);
	await dialog.getByRole('button', { name: 'Download', exact: true }).click();
	const request = await post;
	const form = new URLSearchParams(request.postData() ?? '');
	expect(JSON.parse(form.get('request')!)).toEqual({
		ids,
		format: 'jpeg',
		quality: 90,
		max_edge: 2048,
		strip_location: true,
		strip_all_metadata: false,
		naming: 'date',
		folders: 'year'
	});
	const response = await request.response();
	expect(response?.headers()['content-type']).toBe('application/zip');
});

test('download everything matching a filter', async ({ page }) => {
	await page.goto('/?year=2019');
	// It needs no photo chosen: Select, then the pill's More.
	await page.getByRole('button', { name: 'Select', exact: true }).click();
	await selectionAction(page, /^Download all \d+ photos$/);
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByText(/all \d+ matching photos/)).toBeVisible();
	await dialog.getByRole('button', { name: 'More options' }).click();
	const estimate = page.waitForRequest((r) => r.url().endsWith('/api/downloads/estimate'));
	await dialog.getByLabel('Email, 1280 px').check();
	expect((await estimate).postDataJSON()).toMatchObject({
		filters: { year: 2019 },
		max_edge: 1280
	});
});

test('fix date: shift a selection with a before → after preview', async ({ page }) => {
	await selectTiles(page, [0]);
	await selectionAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await dialog.getByRole('radio', { name: 'Earlier' }).check();
	await dialog.getByRole('spinbutton').nth(1).fill('2');
	const preview = dialog.getByRole('table', { name: 'Before and after' });
	await expect(preview.getByRole('row')).toHaveCount(1);
	const [before, , after] = await preview.getByRole('cell').allTextContents();
	expect(before).not.toBe(after);
	await expectAccessible(page);
	const post = page.waitForRequest((r) => r.url().endsWith('/api/assets/dates'));
	await dialog.getByRole('button', { name: 'Change date' }).click();
	expect((await post).postDataJSON()).toMatchObject({ shift_minutes: -120 });
	await expect(toast(page)).toContainText('Changed the date of 1 photo');
});

test('fix date from the loupe: set an exact date', async ({ page }) => {
	await page.locator('.tile').first().click();
	await loupeAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await dialog.getByLabel('Set exactly').check();
	await dialog.getByLabel('Date and time').fill('03/02/2001 04:05:06');
	await expect(dialog.getByRole('cell').last()).toHaveText('3 Feb 2001, 04:05');
	const post = page.waitForRequest((r) => r.url().endsWith('/api/assets/dates'));
	await dialog.getByRole('button', { name: 'Change date' }).click();
	expect((await post).postDataJSON()).toMatchObject({ set: '2001-02-03T04:05:06' });
});

test('edit: rotate and save a recipe, then revert', async ({ page }) => {
	await page.locator('.tile').first().click();
	await page.getByRole('button', { name: 'Edit' }).click();
	const editor = page.getByRole('dialog', { name: 'Edit photo' });
	await expect(editor.getByRole('group', { name: /Crop area/ })).toBeVisible();
	await editor.getByRole('button', { name: 'Rotate right' }).click();
	await editor.getByRole('button', { name: '1:1' }).click();
	await expectAccessible(page);
	const put = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/edit'));
	await editor.getByRole('button', { name: 'Save' }).click();
	const recipe = (await put).postDataJSON();
	expect(recipe).toMatchObject({ rotate: 90, flip_horizontal: false, straighten: 0 });
	expect(recipe.crop.w).toBeGreaterThan(0);
	await expect(editor).toHaveCount(0);
	if (!isPhone(page))
		await expect(
			loupe(page)
				.getByRole('complementary', { name: 'Details' })
				.getByText('edited', { exact: true })
		).toBeVisible();

	await page.getByRole('button', { name: 'Edit' }).click();
	const del = page.waitForRequest((r) => r.method() === 'DELETE' && r.url().endsWith('/edit'));
	await page.getByRole('button', { name: 'Revert to original' }).click();
	// It asks first: the saved edit is deleted.
	await page
		.getByRole('dialog', { name: 'Go back to the original?' })
		.getByRole('button', { name: 'Revert', exact: true })
		.click();
	await del;
	await expect(toast(page)).toContainText('Back to the original');
});

test('trash: move, see it with its thumbnail, open it full size, restore', async ({ page }) => {
	const id = await page.locator('.tile').first().getAttribute('data-id');
	await selectTiles(page, [0]);
	await selectionAction(page, 'Move to trash');
	await expect(toast(page)).toContainText('Moved 1 photo to the trash');
	await expect(page.locator(`.tile[data-id="${id}"]`)).toHaveCount(0);
	await page.goto('/trash');
	const tile = page.locator(`.tile[data-id="${id}"]`);
	await expect(tile).toBeVisible();
	await expect
		.poll(() => tile.locator('img').evaluate((i: HTMLImageElement) => i.naturalWidth))
		.toBeGreaterThan(0);
	await expectAccessible(page);
	await tile.click();
	const viewer = loupe(page);
	await expect(viewer.locator('img.photo')).toBeVisible();
	await expect
		.poll(() => viewer.locator('img.photo').evaluate((i: HTMLImageElement) => i.naturalWidth))
		.toBeGreaterThan(0);
	await expect(viewer.getByRole('button', { name: 'Edit' })).toHaveCount(0);
	await viewer.getByRole('button', { name: 'Restore' }).click();
	await expect(toast(page)).toContainText('Restored 1 photo');
	await expect(page.getByText('The trash is empty.')).toBeVisible();
});

test('fix date can be undone: the previous dates come back', async ({ page }) => {
	await selectTiles(page, [0, 1]);
	// The photo in words, as its tile says it: the picture's alt text, or the tile's own words
	// where the thumbnail did not load (the real backend's reset brings back rows, not files).
	const before = await page
		.locator('.tile.selected')
		.evaluateAll((els) =>
			els.map((e) => [
				e.getAttribute('data-id'),
				(e.querySelector('img')?.getAttribute('alt') ?? e.textContent ?? '')
					.replace('(preview missing)', '')
					.trim()
			])
		);
	await selectionAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await expect(dialog.getByText(/can be undone/)).toHaveCount(0);
	await dialog.getByLabel('Set exactly').check();
	await dialog.getByLabel('Date and time').fill('03/02/2001 04:05:06');
	await dialog.getByRole('button', { name: 'Change date' }).click();
	await expect(toast(page)).toContainText('Changed the date of 2 photos');
	const undo = page.waitForRequest((r) => r.url().endsWith('/api/assets/dates'));
	await toast(page).getByRole('button', { name: 'Undo' }).click();
	expect((await undo).postDataJSON()).toHaveProperty('set');
	await expect(toast(page)).toContainText('Dates put back');
	for (const [id, words] of before) {
		expect(words).toMatch(/^Photo, \d/);
		await expect(page.locator(`.tile[data-id="${id}"]`)).toHaveAccessibleName(
			new RegExp(`^${words!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}( \\(preview missing\\))?$`)
		);
	}
});

test('download: a server error or an expired session is said, not swallowed', async ({ page }) => {
	await selectTiles(page, [0]);
	await selectionAction(page, 'Download');
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByText(/about [\d.]+ [KMG]B/)).toBeVisible();
	await page.route('**/api/downloads', (route) =>
		route.request().method() === 'POST'
			? route.fulfill({ status: 500, json: { detail: 'not enough space for the ZIP' } })
			: route.continue()
	);
	await dialog.getByRole('button', { name: 'Download', exact: true }).click();
	await expect(toast(page)).toContainText(
		'The download did not start: Not enough space for the ZIP'
	);

	await page.getByRole('button', { name: 'Clear selection' }).click();
	await selectTiles(page, [1]);
	await selectionAction(page, 'Download');
	await expect(dialog.getByText(/about [\d.]+ [KMG]B/)).toBeVisible();
	await page.context().clearCookies();
	await dialog.getByRole('button', { name: 'Download', exact: true }).click();
	await expect(page).toHaveURL(/\/login\?next=/);
});

test('download: original files are labelled as without edits, with a hint for edited ones', async ({
	page
}) => {
	await page.locator('.tile').first().click();
	await page.getByRole('button', { name: 'Edit' }).click();
	await page.getByRole('button', { name: 'Rotate right' }).click();
	await page.getByRole('button', { name: 'Save' }).click();
	await page.getByRole('button', { name: 'Download' }).click();
	const dialog = page.getByRole('dialog', { name: 'Download photo' });
	await expect(dialog.getByLabel('Full size', { exact: true })).toBeChecked();
	await expect(dialog.getByText(/as it was taken, without the edits/)).toBeVisible();
	await expect(dialog.getByLabel('With edits', { exact: true })).toBeVisible();
	await dialog.getByRole('button', { name: 'More options' }).click();
	await expect(dialog.getByLabel('Original file (without edits)')).toBeChecked();
	await expect(dialog.getByText(/Choose JPEG to include the edits/)).toBeVisible();
	await dialog.getByLabel('JPEG').check();
	await expect(dialog.getByText(/Choose JPEG/)).toHaveCount(0);
	await expect(dialog.getByLabel('With edits', { exact: true })).toBeChecked();
});

test('download: two plain choices, and Smaller sends a 2048 JPEG without opening More options', async ({
	page
}) => {
	await selectTiles(page, [0, 1]);
	await selectionAction(page, 'Download');
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByRole('radio')).toHaveCount(2);
	await expect(dialog.getByLabel('Full size', { exact: true })).toBeChecked();
	await expect(dialog.getByLabel('Folders')).toHaveCount(0);
	await dialog.getByLabel('Smaller', { exact: true }).check();
	await expectAccessible(page);

	const post = page.waitForRequest(
		(r) => r.method() === 'POST' && r.url().endsWith('/api/downloads')
	);
	await dialog.getByRole('button', { name: 'Download', exact: true }).click();
	const form = new URLSearchParams((await post).postData() ?? '');
	expect(JSON.parse(form.get('request')!)).toMatchObject({
		format: 'jpeg',
		quality: 90,
		max_edge: 2048,
		strip_location: false,
		naming: 'name',
		folders: 'flat'
	});
});

test('download: a guest with view-only photos is told why nothing can be downloaded', async ({
	page
}) => {
	await signIn(page, '/', GUEST);
	const id = await viewOnlyPhoto(page);
	await page.goto('/?source_id=2');
	const tile = await scrollToTile(page, id);
	if (isPhone(page)) await longPress(tile);
	else await tile.locator('.check').click({ force: true });
	await expect(page.getByText('1 selected')).toBeVisible();
	await selectionAction(page, 'Download');
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByText(/may view these photos but not download them/)).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Download', exact: true })).toBeDisabled();
	await expectAccessible(page);
});

test('trash: “Delete for good” for a selection and “Empty trash” both ask first', async ({
	page
}) => {
	await selectTiles(page, [0, 1]);
	await selectionAction(page, 'Move to trash');
	await expect(
		page.getByRole('status').filter({ hasText: 'Moved 2 photos to the trash' })
	).toBeVisible();
	await page.goto('/trash');
	const tiles = page.locator('.tile');
	await expect(tiles).toHaveCount(2);

	// One selected photo: the dialog counts it, Cancel keeps it.
	await selectTiles(page, [0]);
	await selectionAction(page, 'Delete for good');
	const confirm = page.getByRole('dialog', { name: 'Delete for good?' });
	await expect(confirm).toContainText('1 library copy and its preview will be removed');
	await expect(confirm).toContainText('Originals in source folders stay where they are');
	await expectAccessible(page);
	await confirm.getByRole('button', { name: 'Cancel' }).click();
	await expect(tiles).toHaveCount(2);

	await selectionAction(page, 'Delete for good');
	const purge = page.waitForRequest((r) => r.url().endsWith('/api/trash/empty'));
	await confirm.getByRole('button', { name: 'Delete for good' }).click();
	expect((await purge).postDataJSON().ids).toHaveLength(1);
	await expect(
		page.getByRole('status').filter({ hasText: 'Deleted 1 library copy for good.' })
	).toBeVisible();
	await expect(confirm).toBeHidden();
	await expect(tiles).toHaveCount(1);

	// Nothing selected: Empty trash, behind ⋯ in the head, takes what is left.
	await page.getByRole('button', { name: 'More', exact: true }).click();
	await page.getByRole('button', { name: 'Empty trash' }).click();
	await expect(confirm).toContainText('1 library copy');
	await confirm.getByRole('button', { name: 'Delete for good' }).click();
	await expect(page.getByText('The trash is empty.')).toBeVisible();
	// an empty trash has nothing to select or empty
	await expect(page.getByRole('button', { name: 'More', exact: true })).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Select', exact: true })).toHaveCount(0);
});

test.describe('selection pill', () => {
	const pill = (page: Page) => page.getByRole('toolbar', { name: 'Selected photos' });

	test('the selection pill floats at the bottom centre', async ({ page }) => {
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

	test('the pill: its ×, the count, then Add to album, Download, Move to trash and More', async ({
		page
	}) => {
		await selectTiles(page, [0]);
		await expect(pill(page).getByRole('button').first()).toHaveAccessibleName('Clear selection');
		await expect(pill(page).getByRole('status').locator('.n')).toHaveText('1');
		const actions = pill(page).locator('.actions > button');
		// Icons alone, named by their words: all three fit beside the count on a 390 px phone.
		await expect
			.poll(() => actions.evaluateAll((all) => all.map((b) => b.getAttribute('aria-label'))))
			.toEqual(['Add to album', 'Download', 'Move to trash', 'More']);
		await expect(actions.locator('svg')).toHaveCount(4);
		const more = pill(page).getByRole('button', { name: 'More' });
		await more.click();
		// The library pages in as it scrolls: until it all has, Select all says what it takes.
		await expect(pill(page).getByRole('button', { name: /^Select (all|loaded)/ })).toBeVisible();
		for (const name of ['Fix date', 'Favourite', 'Hide', 'Make private'])
			await expect(pill(page).getByRole('button', { name, exact: true })).toBeVisible();
		// Escape closes More first, then clears the selection.
		await page.keyboard.press('Escape');
		await expect(more).toHaveAttribute('aria-expanded', 'false');
		await expect(pill(page)).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(pill(page)).toHaveCount(0);
		await expect(page.locator('.tile.selected')).toHaveCount(0);
	});

	test('a selected photo that is gone after a reload leaves the selection', async ({ page }) => {
		// Hiding a photo leaves a toast whose Undo reloads the library.
		await selectTiles(page, [0]);
		await selectionAction(page, 'Hide');
		await expect(toast(page)).toContainText('Hid 1 photo');
		await expect(pill(page)).toHaveCount(0);
		await selectTiles(page, [0]);
		const gone = await page.locator('.tile.selected').getAttribute('data-id');
		// Meanwhile the selected photo goes to the trash on another device.
		await page.request.delete('/api/assets', { data: { ids: [Number(gone)] } });
		await toast(page).getByRole('button', { name: 'Undo' }).click();
		await expect(page.locator(`.tile[data-id="${gone}"]`)).toHaveCount(0);
		// Nothing is selected any more, anywhere: no pill, and a press opens a photo again.
		await expect(pill(page)).toHaveCount(0);
		await page.locator('.tile').first().click();
		await expect(loupe(page)).toBeVisible();
	});

	test('with a filter sheet open, Escape closes the sheet and keeps the selection', async ({
		page
	}) => {
		await selectTiles(page, [0]);
		await page
			.getByRole('group', { name: 'Filters' })
			.getByRole('button', { name: 'When', exact: true })
			.click();
		const sheet = page.getByRole('dialog', { name: 'When' });
		await expect(sheet).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(sheet).toBeHidden();
		await expect(pill(page).getByRole('status')).toHaveText('1 selected');
		await page.keyboard.press('Escape');
		await expect(pill(page)).toHaveCount(0);
	});

	// From the narrowest phone up, at the look's largest text and with a long count: what does
	// not fit goes under More, nothing leaves the glass.
	const fitsInside = async (page: Page, width: number) => {
		const glass = (await pill(page).boundingBox())!;
		expect(glass.x).toBeGreaterThanOrEqual(0);
		expect(glass.x + glass.width).toBeLessThanOrEqual(width);
		const inside = pill(page).locator('.count, .actions > button, .clear');
		for (const part of await inside.all()) {
			const box = (await part.boundingBox())!;
			expect(box.x).toBeGreaterThanOrEqual(glass.x);
			expect(box.x + box.width).toBeLessThanOrEqual(glass.x + glass.width);
		}
	};
	const bigText = (page: Page) =>
		page.evaluate(() => document.documentElement.style.setProperty('--text-scale', '1.25'));

	for (const { width, scale, one } of [
		{ width: 320, scale: 1, one: false },
		{ width: 320, scale: 1, one: true },
		{ width: 320, scale: 1.25, one: false },
		{ width: 390, scale: 1, one: false },
		{ width: 390, scale: 1.25, one: false },
		{ width: 390, scale: 1.25, one: true },
		{ width: 700, scale: 1, one: false },
		{ width: 700, scale: 1.25, one: false }
	])
		test(`at ${width} px, text ${scale}, ${one ? 'one photo' : 'hundreds'} selected: everything on the pill is inside it`, async ({
			page
		}) => {
			test.skip(isPhone(page), 'one project sets the widths itself');
			await page.setViewportSize({ width, height: 800 });
			if (one) await page.locator('.tile .check').first().click({ force: true });
			else await selectEverything(page);
			await expect(pill(page).getByRole('status')).toHaveText(
				one ? '1 selected' : /^\d{3} selected$/
			);
			// The text grows under a pill that is already there: it is measured again.
			if (scale !== 1) await bigText(page);
			await expect(async () => fitsInside(page, width)).toPass({ timeout: 3000 });
			await expect(pill(page).getByRole('button', { name: 'Clear selection' })).toBeVisible();
			// Whatever left the pill is still offered, under More.
			await pill(page).getByRole('button', { name: 'More' }).click();
			for (const name of ['Add to album', 'Download', 'Fix date', 'Move to trash'])
				await expect(pill(page).getByRole('button', { name, exact: true })).toBeVisible();
		});

	test('320 px, the largest text and a four-figure count still fit', async ({ page }) => {
		test.skip(isPhone(page), 'one project sets the widths itself');
		test.skip(REAL_BACKEND, 'a library of a thousand photos is a mock-only switch');
		await resetMock('seed', { count: 1100 });
		await signIn(page);
		await page.setViewportSize({ width: 320, height: 800 });
		await bigText(page);
		// "Select all" once every page has loaded ("Select loaded (n)" until then).
		await page.getByRole('button', { name: 'Select', exact: true }).click();
		const more = pill(page).getByRole('button', { name: 'More' });
		const all = pill(page).getByRole('button', { name: 'Select all', exact: true });
		await expect(async () => {
			await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
			if ((await more.getAttribute('aria-expanded')) !== 'true') await more.click();
			await expect(all).toBeVisible({ timeout: 500 });
		}).toPass({ timeout: 20_000 });
		await all.click();
		await expect(pill(page).getByRole('status')).toHaveText(/^\d{4} selected$/);
		await expect(async () => fitsInside(page, 320)).toPass({ timeout: 3000 });
		await pill(page).getByRole('button', { name: 'More' }).click();
		await expect(pill(page).getByRole('button', { name: 'Download', exact: true })).toBeVisible();
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

test.describe('keyboard focus is never left on nothing', () => {
	const pill = (page: Page) => page.getByRole('toolbar', { name: 'Selected photos' });
	/** Where the focus is: a photo, the page, or a named control; "nothing" when it fell to the body. */
	const focus = (page: Page) =>
		page.evaluate(() => {
			const el = document.activeElement;
			if (!el || el === document.body) return 'nothing';
			if (el.matches('.tile')) return 'a photo';
			return el.id === 'main' ? 'the page' : (el.textContent ?? '').trim();
		});

	test('after an action from the pill’s More, and when the pill goes away', async ({ page }) => {
		await selectTiles(page, [0, 1]);
		await selectionAction(page, 'Favourite');
		await expect(toast(page)).toContainText('Marked as favourites.');
		expect(await focus(page)).toBe('More');
		await selectionAction(page, 'Hide');
		await expect(pill(page)).toHaveCount(0);
		await expect.poll(() => focus(page)).toBe('a photo');
		await selectTiles(page, [0]);
		await selectionAction(page, 'Add to album');
		const dialog = page.getByRole('dialog', { name: 'Add to album' });
		await dialog.getByLabel('New album title').fill('Focus');
		await dialog.getByRole('button', { name: 'Add' }).click();
		await expect(pill(page)).toHaveCount(0);
		await expect.poll(() => focus(page)).toBe('a photo');
	});

	test('in the trash, after Restore from the photo view and after Delete for good', async ({
		page
	}) => {
		await selectTiles(page, [0, 1, 2]);
		await selectionAction(page, 'Move to trash');
		await expect(toast(page)).toContainText('Moved 3 photos to the trash');
		await page.goto('/trash');
		await page.locator('.tile').first().click();
		await loupe(page).getByRole('button', { name: 'Restore' }).click();
		await expect(toast(page)).toContainText('Restored 1 photo');
		await expect(loupe(page)).toHaveCount(0);
		await expect(page.locator('.tile')).toHaveCount(2);
		await expect.poll(() => focus(page)).toBe('a photo');
		await takesInput(page);
		await selectTiles(page, [0]);
		await selectionAction(page, 'Delete for good');
		await page
			.getByRole('dialog', { name: 'Delete for good?' })
			.getByRole('button', { name: 'Delete for good' })
			.click();
		await expect(toast(page)).toContainText('Deleted 1 library copy for good');
		await expect.poll(() => focus(page)).toBe('a photo');
		// The last one goes: there is no photo left to take the focus, the page does.
		await page.getByRole('button', { name: 'More', exact: true }).click();
		await page.getByRole('button', { name: 'Empty trash' }).click();
		await page
			.getByRole('dialog', { name: 'Delete for good?' })
			.getByRole('button', { name: 'Delete for good' })
			.click();
		await expect(page.getByText('The trash is empty.')).toBeVisible();
		await expect.poll(() => focus(page)).toBe('the page');
	});
});
