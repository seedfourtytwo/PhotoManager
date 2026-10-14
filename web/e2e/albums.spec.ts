import {
	expect,
	expectAccessible,
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

test('select → add to a new album → reorder → set cover', async ({ page }) => {
	const tiles = page.locator('.tile');
	const ids = await Promise.all([0, 1, 2].map((i) => tiles.nth(i).getAttribute('data-id')));
	await selectTiles(page, [0, 1, 2]);
	await selectionAction(page, 'Add to album');
	const dialog = page.getByRole('dialog', { name: 'Add to album' });
	await dialog.getByLabel('New album title').fill('Test trip');
	await dialog.getByRole('button', { name: 'Add' }).click();
	await expect(toast(page)).toContainText('Created “Test trip” with 3 photos');

	await page.goto('/albums');
	await page.getByRole('link', { name: /Test trip/ }).click();
	await expect(page.getByRole('heading', { name: 'Test trip' })).toBeVisible();
	await expect(page.locator('.tile')).toHaveCount(3);
	await expectAccessible(page);

	// Keyboard reorder works on both devices: Arrange (behind ⋯), focus a photo, Alt+→.
	await page.getByRole('button', { name: 'More', exact: true }).click();
	await page.getByRole('button', { name: 'Arrange' }).click();
	const order = page.waitForRequest(
		(r) => r.method() === 'PUT' && /\/api\/albums\/\d+\/order$/.test(r.url())
	);
	await page.locator(`.tile[data-id="${ids[0]}"]`).focus();
	await page.keyboard.press('Alt+ArrowRight');
	expect((await order).postDataJSON()).toEqual({ asset_ids: [ids[1], ids[0], ids[2]].map(Number) });
	await expect(page.locator('.tile').nth(1)).toHaveAttribute('data-id', ids[0]!);

	if (!isPhone(page)) {
		// Mouse drag: move the last photo to the front.
		const drop = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/order'));
		await page
			.locator('.tile')
			.nth(2)
			.dragTo(page.locator('.tile').nth(0), {
				targetPosition: { x: 5, y: 20 }
			});
		expect((await drop).postDataJSON().asset_ids[0]).toBe(Number(ids[2]));
	}
	await page.getByRole('button', { name: 'Done arranging' }).click();

	await selectTiles(page, [1]);
	await selectionAction(page, 'Set as cover');
	await expect(toast(page)).toContainText('Cover changed');
});

test('share an album with another person', async ({ page }) => {
	await page.goto('/albums');
	await page.getByRole('link', { name: /Summers at the house/ }).click();
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share album' });
	// Names come from the user directory (v1.1), so owners who aren't admins see them too.
	await expect(dialog.getByRole('listitem').filter({ hasText: 'Partner' })).toBeVisible();
	await dialog.getByLabel('Person to add').selectOption({ label: 'Guest' });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	const put = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/members'));
	await dialog.getByRole('button', { name: 'Save' }).click();
	expect((await put).postDataJSON()).toEqual([
		{ user_id: 2, role: 'editor' },
		{ user_id: 3, role: 'viewer' }
	]);
});

test('share on a slow link: nothing can be saved until the current members are in', async ({
	page
}) => {
	let release = () => {};
	const held = new Promise<void>((resolve) => (release = resolve));
	await page.route('**/api/albums/*/members', async (route) => {
		if (route.request().method() === 'GET') await held;
		await route.fallback();
	});
	await page.goto('/albums');
	await page.getByRole('link', { name: /Summers at the house/ }).click();
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share album' });
	await expect(dialog.getByRole('status')).toHaveText('Loading…');
	await expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled();
	await expect(dialog.getByLabel('Person to add')).toHaveCount(0);
	release();
	await dialog.getByLabel('Person to add').selectOption({ label: 'Guest' });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	const put = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/members'));
	await dialog.getByRole('button', { name: 'Save' }).click();
	// Partner, who was already a member, is still in what gets saved.
	expect((await put).postDataJSON()).toEqual([
		{ user_id: 2, role: 'editor' },
		{ user_id: 3, role: 'viewer' }
	]);
});

test('share when the members cannot be loaded: it says so and Save stays off', async ({ page }) => {
	await page.route('**/api/albums/*/members', (route) =>
		route.fulfill({ status: 503, json: { detail: 'The library is busy; try again.' } })
	);
	await page.goto('/albums');
	await page.getByRole('link', { name: /Summers at the house/ }).click();
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share album' });
	await expect(dialog.getByRole('alert')).toContainText('Could not load who this album is shared');
	await expect(dialog.getByRole('button', { name: 'Save' })).toBeDisabled();
	await expect(dialog.getByLabel('Person to add')).toHaveCount(0);
});

test('remove from album, then Undo puts the photos back where they were', async ({ page }) => {
	await page.goto('/albums/1');
	const tiles = page.locator('.tile');
	await expect(tiles.first()).toBeVisible();
	const order = await tiles.evaluateAll((els) => els.map((e) => e.getAttribute('data-id')));
	await selectTiles(page, [1, 3]);
	await selectionAction(page, 'Remove from album');
	await expect(tiles).toHaveCount(order.length - 2);
	await toast(page).getByRole('button', { name: 'Undo' }).click();
	await expect(tiles).toHaveCount(order.length);
	await expect
		.poll(() => tiles.evaluateAll((els) => els.map((e) => e.getAttribute('data-id'))))
		.toEqual(order);
});

test('New album: Enter in the title creates it; a title stops at 200 characters', async ({
	page
}) => {
	await page.goto('/albums');
	await page.getByRole('button', { name: 'New album' }).click();
	const dialog = page.getByRole('dialog', { name: 'New album' });
	const title = dialog.getByLabel('Title');
	await title.fill('x'.repeat(250));
	await expect(title).toHaveValue('x'.repeat(200));
	await expect(dialog.getByText('A title can be up to 200 characters long.')).toBeVisible();
	await title.fill('Typed and entered');
	await title.press('Enter');
	await expect(page).toHaveURL(/\/albums\/\d+$/);
	await expect(page.getByRole('heading', { name: 'Typed and entered' })).toBeVisible();
	await expect(toast(page)).not.toContainText(/String should have/);
});

test('Rename album: Enter saves; the title field stops at 200 characters', async ({ page }) => {
	await page.goto('/albums');
	await page.getByRole('button', { name: 'New album' }).click();
	const create = page.getByRole('dialog', { name: 'New album' });
	await create.getByLabel('Title').fill('Before');
	await create.getByRole('button', { name: 'Create' }).click();
	await expect(page.getByRole('heading', { name: 'Before' })).toBeVisible();
	await page.getByRole('button', { name: 'More', exact: true }).click();
	await page.getByRole('button', { name: 'Rename' }).click();
	const dialog = page.getByRole('dialog', { name: 'Rename album' });
	await expect(dialog.getByLabel('Title')).toHaveAttribute('maxlength', '200');
	await dialog.getByLabel('Title').fill('After');
	await dialog.getByLabel('Title').press('Enter');
	await expect(page.getByRole('heading', { name: 'After' })).toBeVisible();
	await expect(dialog).toBeHidden();
});

test('Add photos: pick from the library in a sheet; what the album holds is not offered', async ({
	page
}) => {
	await page.goto('/albums/1');
	const tiles = page
		.getByRole('main')
		.getByRole('group', { name: 'Photos', exact: true })
		.locator('.tile');
	await expect(tiles.first()).toBeVisible();
	const before = await tiles.count();
	await expect(page.getByRole('main')).toContainText(`${before} photos, `);
	await page.getByRole('button', { name: 'Add photos' }).click();
	const sheet = page.getByRole('dialog', { name: 'Add photos' });
	const offered = sheet.locator('.tile');
	await expect(offered.first()).toBeVisible();
	const inAlbum = await tiles.evaluateAll((all) => all.map((t) => t.getAttribute('data-id')));
	const shown = await offered.evaluateAll((all) => all.map((t) => t.getAttribute('data-id')));
	expect(shown.filter((id) => inAlbum.includes(id))).toEqual([]);
	await expect(sheet.getByRole('button', { name: 'Add', exact: true })).toBeDisabled();
	await offered.nth(0).click();
	await offered.nth(1).click();
	await expect(offered.nth(0)).toHaveAttribute('aria-pressed', 'true');
	await expectAccessible(page);
	await sheet.getByRole('button', { name: 'Add 2 photos' }).click();
	await expect(toast(page)).toContainText('Added 2 photos');
	await expect(sheet).toBeHidden();
	await expect(tiles).toHaveCount(before + 2);
});
