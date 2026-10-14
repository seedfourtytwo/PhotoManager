import type { Page } from '@playwright/test';
import {
	avatar,
	expect,
	expectAccessible,
	follow,
	isPhone,
	MEMBER,
	resetMock,
	signIn,
	test
} from './helpers.ts';

test.beforeEach(async () => {
	await resetMock();
});

const nav = (page: Page) => page.getByRole('navigation', { name: 'Main' });

test('shell: the places and Search in the bar; the rest is on You', async ({ page }) => {
	await signIn(page);
	for (const name of ['Library', 'Collections', 'Search'])
		await expect(nav(page).getByRole('link', { name, exact: true })).toBeVisible();
	for (const name of ['Map', 'People', 'Albums', 'Trash', 'Settings', 'Admin'])
		await expect(nav(page).getByRole('link', { name, exact: true })).toBeHidden();
	await expect(nav(page).getByRole('button')).toHaveCount(0); // no account menu
	await expect(nav(page).getByRole('link', { name: 'Library', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await expectAccessible(page);
});

test('laptop: the avatar sits at the right of the bar and opens You', async ({ page }) => {
	test.skip(isPhone(page), 'on a phone the avatar is in the page’s title row');
	await signIn(page);
	const me = nav(page).getByRole('link', { name: /^You\b/ });
	const bar = (await nav(page).boundingBox())!;
	const box = (await me.boundingBox())!;
	expect(box.x + box.width).toBeGreaterThan(bar.x + bar.width - 64);
	await expect(me).toHaveText('C');
	await me.click();
	await expect(page).toHaveURL(/\/settings$/);
	await expect(page.getByRole('heading', { name: 'C', level: 1 })).toBeVisible();
	await expect(me).toHaveAttribute('aria-current', 'page');
	const main = page.getByRole('main');
	await expect(main.getByRole('link', { name: /^Admin/ })).toHaveAttribute('href', '/admin');
	await expect(main.getByRole('button', { name: 'Change PIN' })).toBeVisible();
	await expect(main.getByRole('button', { name: 'Sign out' })).toBeVisible();
});

test('phone: the dock has no account button, and You has no avatar of its own', async ({
	page
}) => {
	test.skip(!isPhone(page), 'the dock is the phone’s');
	await signIn(page);
	await expect(nav(page).getByRole('link', { name: /^You\b/ })).toBeHidden();
	// You itself has no avatar of its own to press: it is where the avatar leads.
	await follow(page, '/settings');
	await expect(page).toHaveURL(/\/settings$/);
	await expect(avatar(page)).toHaveCount(0);
});

test('shell: the bar is frosted glass, and solid when the device asks for less transparency', async ({
	page
}) => {
	await signIn(page);
	// A laptop frosts the bar itself, a phone the pieces of the dock.
	const bar = isPhone(page) ? nav(page).getByRole('list') : nav(page);
	const backdrop = () => bar.evaluate((el) => getComputedStyle(el).backdropFilter);
	expect(await backdrop()).toContain('blur');
	const cdp = await page.context().newCDPSession(page);
	await cdp.send('Emulation.setEmulatedMedia', {
		features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }]
	});
	await expect.poll(backdrop).toBe('none');
});

test('shell: Collections leads to people, places and albums', async ({ page }) => {
	await signIn(page);
	await nav(page).getByRole('link', { name: 'Collections', exact: true }).click();
	await expect(page).toHaveURL(/\/collections$/);
	const main = page.getByRole('main');
	for (const name of ['People', 'Places', 'Albums'])
		await expect(main.getByRole('link', { name: new RegExp(`^${name}`) })).toBeVisible();
	await expectAccessible(page);
	await main.getByRole('link', { name: /^Places/ }).click();
	await expect(page).toHaveURL(/\/map$/);
	await expect(nav(page).getByRole('link', { name: 'Collections', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
});

test('phone: the lens moves to the chosen place, and leaves when none is', async ({ page }) => {
	test.skip(!isPhone(page), 'the sliding lens is the dock’s');
	await signIn(page);
	const places = nav(page).getByRole('list');
	const lens = () =>
		places.evaluate((ul) => {
			const style = getComputedStyle(ul, '::before');
			return { x: new DOMMatrix(style.transform).m41, shown: style.opacity === '1' };
		});
	const left = async (i: number) => (await places.getByRole('listitem').nth(i).boundingBox())!.x;
	const step = (await left(1)) - (await left(0));
	await expect.poll(lens).toEqual({ x: 0, shown: true });
	await nav(page).getByRole('link', { name: 'Collections', exact: true }).click();
	await expect.poll(async () => Math.round((await lens()).x)).toBe(Math.round(step));
	await nav(page).getByRole('link', { name: 'Search', exact: true }).click();
	await expect.poll(async () => (await lens()).shown).toBe(false);
});

test('shell: a member has no Admin and nothing that needs them, and Sign out leaves', async ({
	page
}) => {
	await signIn(page, '/settings', MEMBER);
	const main = page.getByRole('main');
	await expect(main.getByRole('heading', { name: MEMBER.name, level: 1 })).toBeVisible();
	await expect(main.getByText('Member', { exact: true })).toBeVisible();
	await expect(main.getByRole('link', { name: /^Admin/ })).toHaveCount(0);
	await expect(main.getByRole('region', { name: 'Needs you' })).toHaveCount(0);
	if (!isPhone(page)) await expect(avatar(page)).toHaveAccessibleName('You');
	await expectAccessible(page);
	await main.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login/);
});

test('shell: nothing on the page hides under the bar', async ({ page }) => {
	if (isPhone(page)) {
		// The dock floats over the bottom edge; the last thing on a finite page must clear it.
		await signIn(page, '/settings');
		const dock = (await nav(page).boundingBox())!;
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
	const heading = page.getByRole('main').getByRole('heading').first();
	await expect(heading).toBeVisible();
	const bar = (await nav(page).boundingBox())!;
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

test('shell: touch targets in the dock are at least 44 px both ways', async ({ page }) => {
	test.skip(!isPhone(page), 'the 44 px promise is for touch');
	await signIn(page);
	for (const name of ['Library', 'Collections', 'Search']) {
		const box = (await nav(page).getByRole('link', { name, exact: true }).boundingBox())!;
		expect(box.width).toBeGreaterThanOrEqual(44);
		expect(box.height).toBeGreaterThanOrEqual(44);
	}
});

test('shell: on a tablet or a landscape phone the dock is a capsule, not a bar', async ({
	page
}) => {
	await page.setViewportSize({ width: 900, height: 600 });
	await signIn(page);
	const pill = (await nav(page).getByRole('list').boundingBox())!;
	const search = (await nav(page)
		.getByRole('link', { name: 'Search', exact: true })
		.boundingBox())!;
	expect(pill.width).toBeLessThanOrEqual(26 * 16); // 26rem
	// The two pieces sit together in the middle of the screen.
	const right = search.x + search.width;
	expect(Math.abs(pill.x - (900 - right))).toBeLessThanOrEqual(2 * 16);
	expect(search.x).toBeGreaterThan(pill.x + pill.width);
});

/** Which page moves the root shows while `act` changes the page ('' when none). */
async function movesDuring(page: Page, act: () => Promise<unknown>) {
	await page.evaluate(() => {
		const seen: string[] = [];
		(window as unknown as { seen: string[] }).seen = seen;
		new MutationObserver(() => {
			const move = document.documentElement.dataset.pageMove;
			if (move) seen.push(move);
		}).observe(document.documentElement, { attributeFilter: ['data-page-move'] });
	});
	await act();
	await page.waitForTimeout(100);
	return page.evaluate(() => (window as unknown as { seen: string[] }).seen.join(' '));
}

test('page changes: places fade, a page opened slides in, Back slides back', async ({ page }) => {
	await signIn(page);
	const switched = await movesDuring(page, () =>
		nav(page).getByRole('link', { name: 'Collections', exact: true }).click()
	);
	expect(switched).toBe('switch');
	await expect(page).toHaveURL(/\/collections$/);
	const drilled = await movesDuring(page, () =>
		page
			.getByRole('main')
			.getByRole('link', { name: /^People/ })
			.first()
			.click()
	);
	expect(drilled).toBe('forward');
	await expect(page).toHaveURL(/\/people$/);
	const back = await movesDuring(page, () => page.goBack());
	expect(back).toBe('back');
	await expect(page).toHaveURL(/\/collections$/);
	// Once over, nothing of the move is left: the photo view's own transition has the page out.
	await expect(page.locator('html')).not.toHaveAttribute('data-page-move');
	// Opening a photo is not a page change: it opens from its tile as before.
	await nav(page).getByRole('link', { name: 'Library', exact: true }).click();
	await expect(page.locator('.tile').first()).toBeVisible();
	await expect(page.locator('html')).not.toHaveAttribute('data-page-move');
	const opened = await movesDuring(page, () => page.locator('.tile').first().click());
	expect(opened).toBe('');
});

test('page changes: nothing moves under reduced motion', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await signIn(page);
	const moved = await movesDuring(page, () =>
		nav(page).getByRole('link', { name: 'Collections', exact: true }).click()
	);
	expect(moved).toBe('');
	await expect(page).toHaveURL(/\/collections$/);
});

test('You: Back returns to the page it was opened from, as it was left', async ({ page }) => {
	await signIn(page, '/collections');
	await follow(page, '/settings');
	await expect(page).toHaveURL(/\/settings$/);
	await page.getByRole('main').getByRole('link', { name: 'Collections', exact: true }).click();
	await expect(page).toHaveURL(/\/collections$/);
	// It went back in the history, not forward to a copy: Forward leads to You again.
	await page.goForward();
	await expect(page).toHaveURL(/\/settings$/);
});
