import {
	expect,
	expectAccessible,
	isPhone,
	MEMBER,
	openAccountMenu,
	resetMock,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

test('shell: two places, one search, and the rest behind the account button', async ({ page }) => {
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	for (const name of ['Library', 'Collections', 'Search'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
	for (const name of ['Map', 'People', 'Albums', 'Trash', 'Settings', 'Admin'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeHidden();
	await expect(nav.getByRole('link', { name: 'Library', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await openAccountMenu(page);
	for (const name of ['Trash', 'Settings', 'Admin'])
		await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
	await expect(nav.getByRole('button', { name: 'Sign out' })).toBeVisible();
	await expectAccessible(page);
	await nav.getByRole('link', { name: 'Trash', exact: true }).click();
	await expect(page).toHaveURL(/\/trash$/);
	await expect(nav.getByRole('link', { name: 'Trash', exact: true })).toBeHidden();
});

test('shell: Collections leads to people, places and albums', async ({ page }) => {
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	await nav.getByRole('link', { name: 'Collections', exact: true }).click();
	await expect(page).toHaveURL(/\/collections$/);
	const main = page.getByRole('main');
	for (const name of ['People', 'Places', 'Albums'])
		await expect(main.getByRole('link', { name: new RegExp(`^${name}`) })).toBeVisible();
	await expectAccessible(page);
	await main.getByRole('link', { name: /^Places/ }).click();
	await expect(page).toHaveURL(/\/map$/);
	await expect(nav.getByRole('link', { name: 'Collections', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
});

test('shell: a member has no Admin, and Sign out leaves', async ({ page }) => {
	await signIn(page, '/', MEMBER);
	const nav = await openAccountMenu(page);
	await expect(nav.getByRole('link', { name: 'Settings', exact: true })).toBeVisible();
	await expect(nav.getByRole('link', { name: 'Admin', exact: true })).toHaveCount(0);
	await nav.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login/);
});

test('shell: nothing on the page hides under the bar', async ({ page }) => {
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	const heading = page.getByRole('main').getByRole('heading').first();
	await expect(heading).toBeVisible();
	const bar = (await nav.boundingBox())!;
	const head = (await heading.boundingBox())!;
	if (isPhone(page)) {
		// The dock floats over the bottom edge; the last thing on the page must clear it.
		await page.keyboard.press('End');
		const viewport = page.viewportSize()!;
		expect(bar.y + bar.height).toBeLessThanOrEqual(viewport.height);
		expect(bar.y).toBeGreaterThan(viewport.height / 2);
	} else {
		expect(bar.y).toBe(0);
		expect(head.y).toBeGreaterThanOrEqual(bar.y + bar.height);
		await page.mouse.wheel(0, 2000);
		// A month heading sticks right under the bar: its top edge is the bar's bottom edge.
		const tops = () =>
			page
				.getByRole('main')
				.getByRole('heading', { level: 2 })
				.evaluateAll((all) => all.map((h) => Math.round(h.getBoundingClientRect().top)));
		await expect.poll(async () => (await tops()).includes(Math.round(bar.height))).toBe(true);
	}
});
