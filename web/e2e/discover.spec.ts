/** Search, people, and the navigation that reaches them on both devices. */
import {
	expect,
	expectAccessible,
	GUEST,
	MEMBER,
	REAL_BACKEND,
	resetMock,
	signIn,
	test,
	toast
} from './helpers.ts';

test('search without models: word matches, and a calm note that leads an admin to the setup', async ({
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
	const note = page.getByRole('note');
	await expect(note).toContainText('Search by what is in a photo is not set up yet');
	await expect(note).not.toContainText('just models');
	await expect(note).toContainText('Set it up in Admin, under Search and faces.');
	await expect(note.getByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin');
	await box.fill('sarlat');
	await box.press('Enter');
	await expect(page).toHaveURL(/\/search\?q=sarlat$/);
	await expect(page.locator('.meta')).toContainText(/\d+ photos? · matching words/);
	await expect(page.locator('.tile').first()).toBeVisible();
	await expectAccessible(page);
	await page.locator('.tile').first().click();
	await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toBeVisible();
});

test('without models, a member reads plain words on Search and People: no command, no way in to Admin', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/search', MEMBER);
	const note = page.getByRole('note');
	await expect(note).toContainText('Search by what is in a photo is not set up yet');
	await expect(note).toContainText('words match file names, places, cameras and album titles');
	await expect(note.locator('code')).toHaveCount(0);
	await expect(note.getByRole('link')).toHaveCount(0);

	await page.goto('/people');
	await expect(note).toContainText('New faces are not being found yet');
	await expect(note.locator('code')).toHaveCount(0);
	await expect(note.getByRole('link')).toHaveCount(0);
});

test('without models, People leads an admin to where faces are set up', async ({ page }) => {
	await resetMock();
	await signIn(page, '/people');
	const note = page.getByRole('note');
	await expect(note).toContainText('New faces are not being found yet');
	await expect(note.locator('code')).toHaveCount(0);
	await expect(note).toContainText('Set it up in Admin, under Search and faces.');
	await note.getByRole('link', { name: 'Admin' }).click();
	await expect(page).toHaveURL(/\/admin$/);
	await expect(page.getByRole('heading', { name: 'Search and faces' })).toBeVisible();
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
	await expect(toast(page)).toContainText('Merged 1 into Uncle Jo');
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
