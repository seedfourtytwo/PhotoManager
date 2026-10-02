/** Search, people, and the navigation that reaches them on both devices. */
import {
	expect,
	expectAccessible,
	GUEST,
	isPhone,
	REAL_BACKEND,
	resetMock,
	signIn,
	test
} from './helpers.ts';

test('search without models: word matches and a calm note on how to get AI search', async ({
	page
}) => {
	await resetMock();
	await signIn(page);
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Search' })
		.click();
	await expect(page).toHaveURL(/\/search$/);
	const box = page.getByRole('searchbox', { name: 'Search' });
	await expect(box).toBeFocused();
	await expect(page.getByRole('note')).toContainText('run just models on the server');
	await box.fill('sarlat');
	await box.press('Enter');
	await expect(page).toHaveURL(/\/search\?q=sarlat$/);
	await expect(page.locator('.meta')).toContainText(/\d+ photos? · matching words/);
	await expect(page.locator('.tile').first()).toBeVisible();
	await expectAccessible(page);
	await page.locator('.tile').first().click();
	await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toBeVisible();
});

test('search with models ranks by meaning; facets are read back', async ({ page }) => {
	await resetMock('seed', { models: true });
	await signIn(page, '/search?q=sunset%20date%3A2019');
	await expect(page.locator('.meta')).toContainText(/ranked by meaning · date: 2019/);
	await expect(page.getByRole('note')).toHaveCount(0);
});

test('people: grid of faces, rename, merge, and a person’s photos', async ({ page }) => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await resetMock();
	await signIn(page, '/people');
	await expect(page.getByRole('heading', { name: 'People' })).toBeVisible();
	await expectAccessible(page);
	const someone = page.getByRole('link', { name: /^Someone/ }).first();
	await someone.click();
	await expect(page.locator('.tile').first()).toBeVisible();
	await page.getByRole('button', { name: 'Name' }).click();
	const dialog = page.getByRole('dialog', { name: 'Name this person' });
	await dialog.getByLabel('Name').fill('Uncle Jo');
	await dialog.getByRole('button', { name: 'Save' }).click();
	await expect(page.getByRole('heading', { name: 'Uncle Jo' })).toBeVisible();

	await page.getByRole('button', { name: 'Merge with…' }).click();
	const merge = page.getByRole('dialog', { name: 'Merge people' });
	await merge.getByRole('checkbox').first().check();
	const post = page.waitForRequest((r) => r.url().endsWith('/merge'));
	await merge.getByRole('button', { name: /^Merge/ }).click();
	expect((await post).postDataJSON().source_ids).toHaveLength(1);
	await expect(page.getByRole('status')).toContainText('Merged 1 into Uncle Jo');
	await page.goto('/people');
	await expect(page.getByRole('link', { name: /Uncle Jo/ })).toBeVisible();
});

test('guests see people but cannot rename or merge', async ({ page }) => {
	test.skip(REAL_BACKEND, 'faces need the ML models, which the E2E server does not have');
	await resetMock();
	await signIn(page, '/people', GUEST);
	await page
		.getByRole('link', { name: /photos$/ })
		.first()
		.click();
	await expect(page.getByRole('button', { name: /^(Name|Rename)$/ })).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Merge with…' })).toHaveCount(0);
});

test('navigation: the same five places everywhere; Trash and Settings under More on a phone', async ({
	page
}) => {
	await resetMock();
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	for (const name of ['Library', 'Map', 'People', 'Albums', 'Search'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
	if (isPhone(page)) {
		await expect(nav.getByRole('link', { name: 'Trash' })).toBeHidden();
		await nav.getByRole('button', { name: 'More' }).click();
	}
	await nav.getByRole('link', { name: 'Trash' }).click();
	await expect(page).toHaveURL(/\/trash$/);
	if (isPhone(page)) await nav.getByRole('button', { name: 'More' }).click();
	await expect(nav.getByRole('link', { name: 'Admin' })).toBeVisible();
	await expectAccessible(page);
});
