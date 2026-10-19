/** Search, people, and the navigation that reaches them on both devices. */
import {
	expect,
	expectAccessible,
	GUEST,
	isPhone,
	loupe,
	MEMBER,
	REAL_BACKEND,
	resetMock,
	signIn,
	test,
	toast
} from './helpers.ts';

test('search without models: one field, word matches, and a quiet line for the admin at the end', async ({
	page
}) => {
	await resetMock();
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	if (isPhone(page)) await nav.getByRole('link', { name: 'Search' }).click();
	else {
		// A laptop's Search opens into a field; Enter with nothing typed opens the page.
		await nav.getByRole('button', { name: 'Search' }).click();
		await page.keyboard.press('Enter');
	}
	await expect(page).toHaveURL(/\/search$/);
	// One field: the top bar's on a laptop, the page's on a phone.
	const box = page.getByRole('searchbox', { name: /^Search/ });
	await expect(box).toHaveCount(1);
	if (!isPhone(page)) await expect(box).toBeFocused();
	// No disclaimer on top for anyone.
	await expect(page.getByRole('note')).toHaveCount(0);
	await box.fill('sarlat');
	await box.press('Enter');
	await expect(page).toHaveURL(/\/search\?q=sarlat$/);
	await expect(page.locator('.meta')).toContainText(/\d+ photos?, matching words/);
	await expect(page.locator('.tile').first()).toBeVisible();
	const setup = page.getByText(/^Search by what is in a photo/);
	await expect(setup.getByRole('link', { name: 'set up in Settings' })).toHaveAttribute(
		'href',
		'/settings/search'
	);
	await expectAccessible(page);
	await page.locator('.tile').first().click();
	await expect(loupe(page)).toBeVisible();
});

test('search as it is typed: the results follow the words, in place; Enter keeps it as recent', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/search');
	const box = page.getByRole('searchbox', { name: /^Search/ });
	const steps = await page.evaluate(() => history.length);
	await box.fill('sarl');
	await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe('sarl');
	await expect(page.locator('.tile').first()).toBeVisible();
	expect(await page.evaluate(() => history.length)).toBe(steps); // no step per letter
	await box.fill('sarlat');
	await box.press('Enter');
	await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe('sarlat');
	await page.goto('/search');
	const recent = page.getByRole('region', { name: 'Recent' });
	await expect(recent.getByRole('link', { name: 'sarlat' })).toBeVisible();
	await recent.getByRole('button', { name: 'Clear' }).click();
	await expect(recent).toHaveCount(0);
});

test('without models, a member reads plain words on Search and People: no command, no way in to Admin', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/search?q=sarlat', MEMBER);
	await expect(page.locator('.tile').first()).toBeVisible();
	// nothing about setting it up: a member could not
	const note = page.getByRole('note');
	await expect(note).toHaveCount(0);
	await expect(page.getByText(/^Search by what is in a photo/)).toHaveCount(0);

	// People says nothing to a member about it: there is nothing a member could do.
	await page.goto('/people');
	await expect(page.getByRole('heading', { name: 'People', level: 1 })).toBeVisible();
	const loaded = page
		.getByText('No people yet.')
		.or(page.getByRole('main').locator('a[href^="/people/"]').first());
	await expect(loaded).toBeVisible();
	await expect(note).toHaveCount(0);
	await expect(page.getByText('Faces are paused')).toHaveCount(0);
});

test('without models, People leads an admin to where faces are set up', async ({ page }) => {
	await resetMock();
	await signIn(page, '/people');
	// one glass row, no command, straight to the setup
	const paused = page.getByRole('link', { name: /^Faces are paused/ });
	await expect(paused.locator('code')).toHaveCount(0);
	await paused.click();
	await expect(page).toHaveURL(/\/settings\/search$/);
	await expect(page.getByRole('heading', { name: 'Search & faces', level: 1 })).toBeVisible();
});

test('search before typing: faces, places and, once search by meaning is set up, things', async ({
	page
}) => {
	await resetMock('seed', { models: true });
	await signIn(page, '/search');
	const people = page.getByRole('region', { name: 'People' });
	await expect(people.getByRole('link', { name: 'Sam', exact: true })).toBeVisible();
	await expect(people.getByRole('link', { name: /^Someone/ })).toHaveCount(0);
	await expect(page.getByRole('region', { name: 'Things' }).getByRole('link')).not.toHaveCount(0);
	await expectAccessible(page);
	const place = page.getByRole('region', { name: 'Places' }).getByRole('link').first();
	const name = (await place.locator('.title').textContent())!.trim();
	await place.click();
	await expect.poll(() => new URL(page.url()).searchParams.get('q')).toMatch(`place:`);
	await expect(page.getByRole('searchbox', { name: /^Search/ })).toHaveValue(
		new RegExp(`^place:"?${name}"?$`)
	);
	await expect(page.locator('.tile').first()).toBeVisible();
});

test('search before typing, without models: no things to suggest, they would find nothing', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/search');
	await expect(page.getByRole('region', { name: 'Places' })).toBeVisible();
	await expect(page.getByRole('region', { name: 'Things' })).toHaveCount(0);
});

test('search with models ranks by meaning; facets are read back', async ({ page }) => {
	await resetMock('seed', { models: true });
	await signIn(page, '/search?q=sunset%20date%3A2019');
	await expect(page.locator('.meta')).toContainText(/ranked by meaning, date: 2019/);
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
	// the person's tools wait behind the round ⋯
	const more = page.getByRole('button', { name: 'More', exact: true });
	await more.click();
	await page.getByRole('button', { name: 'Name', exact: true }).click();
	const dialog = page.getByRole('dialog', { name: 'Name this person' });
	await dialog.getByLabel('Name').fill('Uncle Jo');
	await dialog.getByRole('button', { name: 'Save' }).click();
	await expect(page.getByRole('heading', { name: 'Uncle Jo' })).toBeVisible();

	await more.click();
	await page.getByRole('button', { name: 'Merge with…' }).click();
	const merge = page.getByRole('dialog', { name: 'Merge people' });
	await merge.getByRole('group', { name: 'People to merge' }).getByRole('button').first().click();
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
	await page.getByRole('main').locator('a[href^="/people/"]').first().click();
	await expect(page).toHaveURL(/\/people\/\d+$/);
	await expect(page.getByRole('button', { name: 'More', exact: true })).toHaveCount(0);
	await expect(page.getByRole('button', { name: /^(Name|Rename)$/ })).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Merge with…' })).toHaveCount(0);
});
