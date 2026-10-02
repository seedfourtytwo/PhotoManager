import {
	expect,
	expectAccessible,
	isPhone,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test,
	GUEST
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
	await expect(dialog.getByText(/2 selected photos\s+· about [\d.]+ [KMG]B/)).toBeVisible();
	await expectAccessible(page);

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
	await page.getByRole('button', { name: 'Download all' }).click();
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByText(/all \d+ matching photos/)).toBeVisible();
	const estimate = page.waitForRequest((r) => r.url().endsWith('/api/downloads/estimate'));
	await dialog.getByLabel('Email · 1280').check();
	expect((await estimate).postDataJSON()).toMatchObject({
		filters: { year: 2019 },
		max_edge: 1280
	});
});

test('fix date: shift a selection with a before → after preview', async ({ page }) => {
	await selectTiles(page, [0]);
	await selectionAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await dialog.getByLabel('Direction').selectOption({ label: 'earlier' });
	await dialog.getByRole('spinbutton').nth(1).fill('2');
	const preview = dialog.getByRole('table', { name: 'Before and after' });
	await expect(preview.getByRole('row')).toHaveCount(1);
	const [before, , after] = await preview.getByRole('cell').allTextContents();
	expect(before).not.toBe(after);
	await expectAccessible(page);
	const post = page.waitForRequest((r) => r.url().endsWith('/api/assets/dates'));
	await dialog.getByRole('button', { name: 'Change date' }).click();
	expect((await post).postDataJSON()).toMatchObject({ shift_minutes: -120 });
	await expect(page.getByRole('status')).toContainText('Changed the date of 1 photo');
});

test('fix date from the loupe: set an exact date', async ({ page }) => {
	await page.locator('.tile').first().click();
	await page.getByRole('button', { name: 'Fix date' }).click();
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await dialog.getByLabel('Set exactly').check();
	await dialog.getByLabel('Date and time').fill('2001-02-03T04:05:06');
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
	if (!isPhone(page)) await expect(page.getByText(/· edited/)).toBeVisible();

	await page.getByRole('button', { name: 'Edit' }).click();
	const del = page.waitForRequest((r) => r.method() === 'DELETE' && r.url().endsWith('/edit'));
	await page.getByRole('button', { name: 'Revert to original' }).click();
	await del;
	await expect(page.getByRole('status')).toContainText('Back to the original');
});

test('trash: move, see it with its thumbnail, open it full size, restore', async ({ page }) => {
	const id = await page.locator('.tile').first().getAttribute('data-id');
	await selectTiles(page, [0]);
	await selectionAction(page, 'Move to trash');
	await expect(page.getByRole('status')).toContainText('Moved 1 photo to the trash');
	await expect(page.locator(`.tile[data-id="${id}"]`)).toHaveCount(0);
	await page.goto('/trash');
	const tile = page.locator(`.tile[data-id="${id}"]`);
	await expect(tile).toBeVisible();
	await expect
		.poll(() => tile.locator('img').evaluate((i: HTMLImageElement) => i.naturalWidth))
		.toBeGreaterThan(0);
	await expectAccessible(page);
	await tile.click();
	const loupe = page.getByRole('dialog', { name: 'Photo viewer' });
	await expect(loupe.locator('img.photo')).toBeVisible();
	await expect
		.poll(() => loupe.locator('img.photo').evaluate((i: HTMLImageElement) => i.naturalWidth))
		.toBeGreaterThan(0);
	await expect(loupe.getByRole('button', { name: 'Edit' })).toHaveCount(0);
	await loupe.getByRole('button', { name: 'Restore' }).click();
	await expect(page.getByRole('status')).toContainText('Restored 1 photo');
	await expect(page.getByText('The trash is empty.')).toBeVisible();
});

test('fix date can be undone: the previous dates come back', async ({ page }) => {
	await selectTiles(page, [0, 1]);
	const before = await page
		.locator('.tile.selected img')
		.evaluateAll((els) => els.map((e) => e.getAttribute('alt')));
	await selectionAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await expect(dialog.getByText(/can be undone/)).toHaveCount(0);
	await dialog.getByLabel('Set exactly').check();
	await dialog.getByLabel('Date and time').fill('2001-02-03T04:05:06');
	await dialog.getByRole('button', { name: 'Change date' }).click();
	await expect(page.getByRole('status')).toContainText('Changed the date of 2 photos');
	const undo = page.waitForRequest((r) => r.url().endsWith('/api/assets/dates'));
	await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
	expect((await undo).postDataJSON()).toHaveProperty('set');
	await expect(page.getByRole('status')).toContainText('Dates put back');
	for (const alt of before) await expect(page.getByAltText(alt!, { exact: true })).toBeVisible();
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
	await expect(page.getByRole('status')).toContainText(
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
	await expect(dialog.getByLabel('Original file (without edits)')).toBeChecked();
	await expect(dialog.getByText(/Choose JPEG to include the edits/)).toBeVisible();
	await dialog.getByLabel('JPEG').check();
	await expect(dialog.getByText(/Choose JPEG/)).toHaveCount(0);
});

test('download: a guest with view-only photos is told why nothing can be downloaded', async ({
	page
}) => {
	await signIn(page, '/?source_id=2&to=2015-12-31', GUEST);
	await selectTiles(page, [0]);
	await selectionAction(page, 'Download');
	const dialog = page.getByRole('dialog', { name: 'Download' });
	await expect(dialog.getByText(/may view these photos but not download them/)).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Download', exact: true })).toBeDisabled();
	await expectAccessible(page);
});
