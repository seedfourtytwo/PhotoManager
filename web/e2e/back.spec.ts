/**
 * "Opening a sheet or a photo adds a history step, so Back on the phone closes it" (redesign
 * spec §4.2). The photo's own step is in loupe.spec.ts and loupe-gestures.spec.ts, its Details
 * sheet's in back-info.spec.ts; these are the sheets and dialogs.
 */
import {
	delayRoute,
	expect,
	isPhone,
	loupe,
	loupeAction,
	resetMock,
	selectionAction,
	selectTiles,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(async ({ page }) => {
	await resetMock();
	// Every journey starts one page before the one under test: a Back too many is seen.
	await signIn(page, '/collections');
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Library' })
		.click();
	await expect(page.locator('.tile').first()).toBeVisible();
});

const filters = (page: import('@playwright/test').Page) =>
	page.getByRole('complementary', { name: 'Filters' });

test('phone: Back closes the filter sheet and stays in the library', async ({ page }) => {
	test.skip(!isPhone(page), 'the filters are a sheet on a phone only');
	await page.getByRole('button', { name: 'Filter', exact: true }).click();
	await expect(filters(page)).toBeVisible();
	await page.goBack();
	await expect(filters(page)).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	await expect(page.locator('.tile').first()).toBeVisible();
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

test('phone: a filter sheet closed with Done leaves no step behind', async ({ page }) => {
	test.skip(!isPhone(page), 'the filters are a sheet on a phone only');
	await page.getByRole('button', { name: 'Filter', exact: true }).click();
	await filters(page).getByRole('button', { name: 'Done' }).click();
	await expect(filters(page)).toBeHidden();
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

for (const how of ['Back', 'Done'] as const) {
	test(`phone: a filter chosen in the sheet stays when ${how} closes it, and the next Back undoes it`, async ({
		page
	}) => {
		test.skip(!isPhone(page), 'the filters are a sheet on a phone only');
		await page.getByRole('button', { name: 'Filter', exact: true }).click();
		await filters(page).getByRole('button', { name: /^2019/ }).click();
		await expect(page).toHaveURL(/year=2019/);
		await expect(filters(page), 'choosing does not close the sheet').toBeVisible();
		await filters(page).getByLabel('Favourites').check();
		await expect(page).toHaveURL(/year=2019&favourite=true/);
		if (how === 'Back') await page.goBack();
		else await filters(page).getByRole('button', { name: 'Done' }).click();
		await expect(filters(page)).toBeHidden();
		await expect(page).toHaveURL(/year=2019&favourite=true/);
		await page.goBack();
		await expect(page).toHaveURL(/\/$/);
		await page.goBack();
		await expect(page).toHaveURL(/\/collections$/);
	});
}

test('Back closes Fix date and keeps the selection', async ({ page }) => {
	await selectTiles(page, [0, 1]);
	await selectionAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await expect(dialog).toBeVisible();
	await page.goBack();
	await expect(dialog).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByText('2 selected')).toBeVisible();
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

test('a dialog closed with Cancel leaves no step behind', async ({ page }) => {
	await selectTiles(page, [0]);
	await selectionAction(page, 'Fix date');
	const dialog = page.getByRole('dialog', { name: 'Fix date' });
	await dialog.getByRole('button', { name: 'Cancel' }).click();
	await expect(dialog).toBeHidden();
	await expect(page.getByText('1 selected')).toBeVisible();
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

test('over an open photo, Back closes the dialog, then the photo', async ({ page }) => {
	await page.locator('.tile').first().click();
	const viewer = loupe(page);
	await expect(viewer).toBeVisible();
	await loupeAction(page, 'Add to album');
	const dialog = page.getByRole('dialog', { name: 'Add to album' });
	await expect(dialog).toBeVisible();
	await page.goBack();
	await expect(dialog).toBeHidden();
	await expect(viewer).toBeVisible();
	await expect(page).toHaveURL(/photo=\d+/);
	await page.goBack();
	await expect(viewer).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
});

test('Back closes the editor, not the photo under it', async ({ page }) => {
	await page.locator('.tile').first().click();
	const viewer = loupe(page);
	await loupeAction(page, 'Edit');
	const editor = page.getByRole('dialog', { name: 'Edit photo' });
	await expect(editor).toBeVisible();
	await page.goBack();
	await expect(editor).toBeHidden();
	await expect(viewer).toBeVisible();
});

test('the editor asks before unsaved changes go: Back, Escape and Cancel alike', async ({
	page
}) => {
	await page.locator('.tile').first().click();
	const viewer = loupe(page);
	await loupeAction(page, 'Edit');
	const editor = page.getByRole('dialog', { name: 'Edit photo' });
	const ask = page.getByRole('dialog', { name: 'Discard your changes?' });
	const turned = editor.getByRole('button', { name: 'Reset' });
	await expect(editor.getByRole('group', { name: /Crop area/ })).toBeVisible();
	await editor.getByRole('button', { name: 'Rotate right' }).click();

	await page.goBack();
	await expect(ask).toBeVisible();
	await expect(editor).toBeVisible();
	await ask.getByRole('button', { name: 'Keep editing' }).click();
	await expect(ask).toBeHidden();
	await expect(turned, 'the change is still there').toBeEnabled();

	// A second Back asks again: the editor has its step back.
	await page.goBack();
	await expect(ask).toBeVisible();
	await page.goBack(); // Back in the question is "Keep editing"
	await expect(ask).toBeHidden();
	await expect(editor).toBeVisible();

	await page.keyboard.press('Escape');
	await expect(ask).toBeVisible();
	await page.keyboard.press('Escape'); // and so is Escape
	await expect(ask).toBeHidden();
	await expect(editor).toBeVisible();
	await expect(turned).toBeEnabled();

	await editor.getByRole('button', { name: 'Cancel' }).click();
	await ask.getByRole('button', { name: 'Discard changes' }).click();
	await expect(editor).toBeHidden();
	await expect(viewer).toBeVisible();
	await expect(page).toHaveURL(/photo=\d+/);

	// No step is left behind: one Back for the photo, one for the page.
	await page.goBack();
	await expect(viewer).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

test('Back with unsaved changes, then “Discard changes”: the photo is one Back from the library', async ({
	page
}) => {
	await page.locator('.tile').first().click();
	const viewer = loupe(page);
	await loupeAction(page, 'Edit');
	const editor = page.getByRole('dialog', { name: 'Edit photo' });
	const ask = page.getByRole('dialog', { name: 'Discard your changes?' });
	await expect(editor.getByRole('group', { name: /Crop area/ })).toBeVisible();
	await editor.getByRole('button', { name: 'Flip horizontal' }).click();
	const saved = { count: 0 };
	page.on('request', (r) => {
		if (r.method() === 'PUT' && r.url().endsWith('/edit')) saved.count++;
	});
	await page.goBack();
	await ask.getByRole('button', { name: 'Discard changes' }).click();
	await expect(editor).toBeHidden();
	await expect(viewer).toBeVisible();
	await page.goBack();
	await expect(viewer).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
	expect(saved.count).toBe(0);
});

test('a save that lands while the editor is asking closes both and leaves no step behind', async ({
	page
}) => {
	await page.locator('.tile').first().click();
	const viewer = loupe(page);
	await loupeAction(page, 'Edit');
	const editor = page.getByRole('dialog', { name: 'Edit photo' });
	const ask = page.getByRole('dialog', { name: 'Discard your changes?' });
	await expect(editor.getByRole('group', { name: /Crop area/ })).toBeVisible();
	await editor.getByRole('button', { name: 'Rotate right' }).click();
	await delayRoute(page, /\/api\/assets\/\d+\/edit$/, 600);
	await editor.getByRole('button', { name: 'Save' }).click();
	await page.goBack();
	await expect(ask).toBeVisible();
	await expect(editor).toBeHidden();
	await expect(ask).toBeHidden();
	await expect(viewer).toBeVisible();
	await page.goBack();
	await expect(viewer).toBeHidden();
	await expect(page).toHaveURL(/\/$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/collections$/);
});

test('a new album: Back from it is the list of albums, not the dialog', async ({ page }) => {
	await page.goto('/albums');
	await page.getByRole('button', { name: 'New album' }).click();
	const dialog = page.getByRole('dialog', { name: 'New album' });
	await dialog.getByLabel('Title').fill('Back and forth');
	await dialog.getByRole('button', { name: 'Create' }).click();
	await expect(page).toHaveURL(/\/albums\/\d+$/);
	await page.goBack();
	await expect(page).toHaveURL(/\/albums$/);
	await expect(dialog).toBeHidden();
});
