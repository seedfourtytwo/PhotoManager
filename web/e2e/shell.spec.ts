import {
	expect,
	expectAccessible,
	isPhone,
	MEMBER,
	openAccountMenu,
	resetMock,
	selectTiles,
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
	if (isPhone(page)) {
		// The dock floats over the bottom edge; the last thing on a finite page must clear it.
		await signIn(page, '/settings');
		const dock = (await page.getByRole('navigation', { name: 'Main' }).boundingBox())!;
		const viewport = page.viewportSize()!;
		expect(dock.y + dock.height).toBeLessThanOrEqual(viewport.height);
		expect(dock.y).toBeGreaterThan(viewport.height / 2);
		await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
		await expect
			.poll(() =>
				page.evaluate(
					() => window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1
				)
			)
			.toBe(true);
		const lastBottom = await page.evaluate(() => {
			const last = [...document.querySelectorAll('main *')]
				.filter((el) => el.getBoundingClientRect().height > 0)
				.map((el) => el.getBoundingClientRect().bottom);
			return Math.max(...last);
		});
		expect(lastBottom).toBeLessThanOrEqual(dock.y);
		return;
	}
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	const heading = page.getByRole('main').getByRole('heading').first();
	await expect(heading).toBeVisible();
	const bar = (await nav.boundingBox())!;
	const head = (await heading.boundingBox())!;
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
});

test('shell: with a selection, every account menu row is the top thing at its centre', async ({
	page
}) => {
	test.skip(!isPhone(page), 'the selection bar sits over the dock on phones');
	await signIn(page);
	await selectTiles(page, [0]);
	const nav = await openAccountMenu(page);
	const rows = nav.locator('ul[id] a, ul[id] button');
	const count = await rows.count();
	expect(count).toBeGreaterThanOrEqual(4);
	for (let i = 0; i < count; i++) {
		const covered = await rows.nth(i).evaluate((el) => {
			const r = el.getBoundingClientRect();
			const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
			return !(top && el.contains(top));
		});
		expect(covered, `row ${i} is covered`).toBe(false);
	}
	await nav.getByRole('link', { name: 'Settings', exact: true }).click();
	await expect(page).toHaveURL(/\/settings$/);
});

test('shell: touch targets in the bar are at least 44 px both ways', async ({ page }) => {
	test.skip(!isPhone(page), 'the 44 px promise is for touch');
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	const targets = [
		nav.getByRole('link', { name: 'Library', exact: true }),
		nav.getByRole('link', { name: 'Collections', exact: true }),
		nav.getByRole('link', { name: 'Search', exact: true }),
		nav.getByRole('button', { name: /^Account/ })
	];
	for (const target of targets) {
		const box = (await target.boundingBox())!;
		expect(box.width).toBeGreaterThanOrEqual(44);
		expect(box.height).toBeGreaterThanOrEqual(44);
	}
	await openAccountMenu(page);
	const rows = nav.locator('ul[id] a, ul[id] button');
	for (let i = 0; i < (await rows.count()); i++) {
		const box = (await rows.nth(i).boundingBox())!;
		expect(box.width).toBeGreaterThanOrEqual(44);
		expect(box.height).toBeGreaterThanOrEqual(44);
	}
});

test('shell: on a tablet or a landscape phone the dock is a pill, not a bar', async ({ page }) => {
	await page.setViewportSize({ width: 900, height: 600 });
	await signIn(page);
	const nav = page.getByRole('navigation', { name: 'Main' });
	const pill = (await nav.getByRole('list').boundingBox())!;
	const search = (await nav.getByRole('link', { name: 'Search', exact: true }).boundingBox())!;
	const account = (await nav.getByRole('button', { name: /^Account/ }).boundingBox())!;
	expect(pill.width).toBeLessThanOrEqual(26 * 14);
	// The three pieces sit together in the middle of the screen.
	const left = pill.x;
	const right = account.x + account.width;
	expect(Math.abs(left - (900 - right))).toBeLessThanOrEqual(2 * 14);
	expect(search.x).toBeGreaterThan(pill.x + pill.width);
	expect(account.x).toBeGreaterThan(search.x);
});
