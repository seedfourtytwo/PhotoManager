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

test('select → add to a new album → reorder → set cover', async ({ page }) => {
	const tiles = page.locator('.tile');
	const ids = await Promise.all([0, 1, 2].map((i) => tiles.nth(i).getAttribute('data-id')));
	await selectTiles(page, [0, 1, 2]);
	await page
		.getByRole('toolbar', { name: 'Selected photos' })
		.getByRole('button', { name: 'Add to album' })
		.click();
	const dialog = page.getByRole('dialog', { name: 'Add to album' });
	await dialog.getByLabel('New album title').fill('Test trip');
	await dialog.getByRole('button', { name: 'Add' }).click();
	await expect(page.getByRole('status')).toContainText('Created “Test trip” with 3 photos');

	await page.goto('/albums');
	await page.getByRole('link', { name: /Test trip/ }).click();
	await expect(page.getByRole('heading', { name: 'Test trip' })).toBeVisible();
	await expect(page.locator('.tile')).toHaveCount(3);
	await expectAccessible(page);

	// Keyboard reorder works on both devices: Arrange, focus a photo, Alt+→.
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
	await page.getByRole('button', { name: 'Set as cover' }).click();
	await expect(page.getByRole('status')).toContainText('Cover changed');
});

test('share an album with another person', async ({ page }) => {
	await page.goto('/albums');
	await page.getByRole('link', { name: /Summers at the house/ }).click();
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share album' });
	await expect(dialog.getByText('Partner (partner)')).toBeVisible();
	await dialog.getByLabel('Person to add').selectOption({ label: 'Guest' });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	const put = page.waitForRequest((r) => r.method() === 'PUT' && r.url().endsWith('/members'));
	await dialog.getByRole('button', { name: 'Save' }).click();
	expect((await put).postDataJSON()).toEqual([
		{ user_id: 2, role: 'editor' },
		{ user_id: 3, role: 'viewer' }
	]);
});
