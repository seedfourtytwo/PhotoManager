import {
	expect,
	expectAccessible,
	isPhone,
	resetMock,
	selectTiles,
	signIn,
	test
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
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'Download' })
		.click();
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
	await expect(dialog.getByText(/all 28 matching photos/)).toBeVisible();
	const estimate = page.waitForRequest((r) => r.url().endsWith('/api/downloads/estimate'));
	await dialog.getByLabel('Email · 1280').check();
	expect((await estimate).postDataJSON()).toMatchObject({
		filters: { year: 2019 },
		max_edge: 1280
	});
});

test('fix date: shift a selection with a before → after preview', async ({ page }) => {
	await selectTiles(page, [0]);
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'Fix date' })
		.click();
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

test('trash: move, restore', async ({ page }) => {
	const id = await page.locator('.tile').first().getAttribute('data-id');
	await selectTiles(page, [0]);
	await page.getByRole('button', { name: 'Move to trash' }).click();
	await expect(page.getByRole('status')).toContainText('Moved 1 photo to the trash');
	await expect(page.locator(`.tile[data-id="${id}"]`)).toHaveCount(0);
	await page.goto('/trash');
	await expect(page.locator(`.tile[data-id="${id}"]`)).toBeVisible();
	await expectAccessible(page);
	await page.locator(`.tile[data-id="${id}"]`).click();
	await page.getByRole('button', { name: 'Restore' }).click();
	await expect(page.getByText('The trash is empty.')).toBeVisible();
});
