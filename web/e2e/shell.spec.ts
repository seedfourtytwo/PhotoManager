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
/** A laptop's capsule (1024 px and wider); a phone or a tablet has the dock. */
const wide = (page: Page) => (page.viewportSize()?.width ?? 1440) >= 1024;
/** Search in the bar: a round button that opens a field on a laptop, a link on the dock. */
const searchIn = (page: Page) =>
	nav(page).getByRole(wide(page) ? 'button' : 'link', { name: 'Search', exact: true });
/** Whether the root says the laptop's capsule is away (lib/scroll-chrome.svelte.ts). */
const away = (page: Page) =>
	page.evaluate(() => document.documentElement.dataset.chrome === 'away');

test('shell: Home, Library, Collections and Search in the bar; the rest is on You', async ({
	page
}) => {
	await signIn(page);
	for (const name of ['Home', 'Library', 'Collections'])
		await expect(nav(page).getByRole('link', { name, exact: true })).toBeVisible();
	await expect(searchIn(page)).toBeVisible();
	for (const name of ['Map', 'People', 'Albums', 'Trash', 'Settings', 'Admin'])
		await expect(nav(page).getByRole('link', { name, exact: true })).toBeHidden();
	// No account menu: the only button is a laptop's Search.
	await expect(nav(page).getByRole('button')).toHaveCount(wide(page) ? 1 : 0);
	await expect(nav(page).getByRole('link', { name: 'Library', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await expectAccessible(page);
});

test('laptop: a glass capsule floats centred at the top, the avatar on its line at the right', async ({
	page
}) => {
	test.skip(isPhone(page), 'on a phone the avatar is in the page’s title row');
	await signIn(page);
	const capsule = (await nav(page).getByRole('list').boundingBox())!;
	const search = (await searchIn(page).boundingBox())!;
	expect(capsule.y).toBe(16);
	expect(capsule.height).toBe(52);
	expect(search).toMatchObject({ y: 16, width: 52, height: 52 });
	// The capsule and Search beside it sit together in the middle of the window.
	const width = page.viewportSize()!.width;
	expect(Math.abs(capsule.x - (width - search.x - search.width))).toBeLessThanOrEqual(2);
	const me = nav(page).getByRole('link', { name: /^You\b/ });
	const box = (await me.boundingBox())!;
	expect(box.width).toBe(40);
	expect(box.y + box.height / 2).toBe(capsule.y + capsule.height / 2);
	expect(box.x + box.width).toBeGreaterThan(width - 64);
	await expect(me).toHaveText('C');
	await me.click();
	await expect(page).toHaveURL(/\/settings$/);
	await expect(page.getByRole('heading', { name: 'C', level: 1 })).toBeVisible();
	await expect(me).toHaveAttribute('aria-current', 'page');
	const main = page.getByRole('main');
	await expect(
		main.getByRole('navigation', { name: 'Settings' }).getByRole('link', { name: 'Overview' })
	).toHaveAttribute('href', '/settings/overview');
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
	const bar = nav(page).getByRole('list');
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

test('the lens moves to the chosen place, and leaves when none is', async ({ page }) => {
	await signIn(page);
	const places = nav(page).getByRole('list');
	const lens = () =>
		places.evaluate((ul) => {
			const style = getComputedStyle(ul, '::before');
			return { x: Math.round(new DOMMatrix(style.transform).m41), shown: style.opacity === '1' };
		});
	const left = async (i: number) => (await places.getByRole('listitem').nth(i).boundingBox())!.x;
	const step = (await left(1)) - (await left(0));
	// Home, Library, Collections: signing in at "/" asked for the Library, the second place.
	await expect.poll(lens).toEqual({ x: Math.round(step), shown: true });
	await nav(page).getByRole('link', { name: 'Collections', exact: true }).click();
	await expect.poll(async () => Math.round((await lens()).x)).toBe(Math.round(2 * step));
	await follow(page, '/search');
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
	const bar = (await nav(page).getByRole('list').boundingBox())!;
	const head = (await heading.boundingBox())!;
	expect(head.y).toBeGreaterThanOrEqual(bar.y + bar.height);
	await page.mouse.move(600, 500);
	await page.mouse.wheel(0, 2000);
	// Month headings scroll away with their photos (no strip stuck under the capsule); the
	// month in view rides in the compact title that takes the capsule's place.
	await expect(page.getByRole('main').getByRole('heading', { level: 2 }).first()).toHaveCSS(
		'position',
		'static'
	);
	await expect(page.locator('.compact.on .sub')).toHaveText(/^[A-Z][a-z]+ \d{4}$/);
});

test('laptop: the capsule steps away while the page scrolls down and comes back on the way up', async ({
	page
}) => {
	test.skip(isPhone(page), 'the dock stays');
	await signIn(page);
	await expect(page.locator('.tile img').first()).toBeVisible();
	const capsule = nav(page).getByRole('list');
	const bottom = async () => {
		const box = (await capsule.boundingBox())!;
		return box.y + box.height;
	};
	await page.mouse.move(600, 500);
	await page.mouse.wheel(0, 800);
	await expect.poll(() => away(page)).toBe(true);
	await expect.poll(bottom).toBeLessThanOrEqual(0); // above the window, not only faded
	await page.mouse.wheel(0, -40);
	await expect.poll(() => away(page)).toBe(false);
	await expect.poll(bottom).toBe(16 + 52);
	// A new page brings it back too.
	await page.mouse.wheel(0, 800);
	await expect.poll(() => away(page)).toBe(true);
	await follow(page, '/collections');
	await expect.poll(() => away(page)).toBe(false);
});

test('laptop: under reduced motion the capsule goes and comes without moving', async ({ page }) => {
	test.skip(isPhone(page), 'the dock stays');
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await signIn(page);
	const duration = () => nav(page).evaluate((el) => getComputedStyle(el).transitionDuration);
	expect((await duration()).split(', ').every((d) => d === '0s')).toBe(true);
});

test('laptop: keyboard focus brings the capsule back, and it stays while focus is in it', async ({
	page
}) => {
	test.skip(isPhone(page), 'the dock stays');
	await signIn(page);
	await expect(page.locator('.tile img').first()).toBeVisible();
	await page.mouse.move(600, 500);
	await page.mouse.wheel(0, 800);
	await expect.poll(() => away(page)).toBe(true);
	await nav(page).getByRole('link', { name: 'Library', exact: true }).focus();
	await expect.poll(() => away(page)).toBe(false);
	await page.evaluate(() => window.scrollBy(0, 600));
	await page.waitForTimeout(300);
	expect(await away(page)).toBe(false);
});

test('laptop: the capsule stays while a menu is open', async ({ page }) => {
	test.skip(isPhone(page), 'the dock stays');
	await signIn(page);
	await expect(page.locator('.tile img').first()).toBeVisible();
	// The More filter: on a laptop a popover under its chip.
	await page.getByRole('main').getByRole('button', { name: 'More', exact: true }).click();
	await expect(page.getByRole('dialog', { name: 'More' })).toBeVisible();
	await page.evaluate(() => window.scrollBy(0, 600));
	await page.waitForTimeout(300);
	expect(await away(page)).toBe(false);
});

test('laptop: Search opens into a field over the capsule; Enter searches, Escape closes it', async ({
	page
}) => {
	test.skip(isPhone(page), 'the dock’s Search is a link to the page');
	await signIn(page);
	await searchIn(page).click();
	const field = nav(page).getByRole('searchbox', { name: 'Search photos' });
	await expect(field).toBeFocused();
	await expect(searchIn(page)).toHaveAttribute('aria-expanded', 'true');
	await page.keyboard.press('Escape');
	await expect(field).toHaveCount(0);
	await expect(searchIn(page)).toBeFocused();
	await page.keyboard.press('Enter');
	await field.fill('sarlat');
	await field.press('Enter');
	await expect(page).toHaveURL(/\/search\?q=sarlat$/);
	await expect(field).toHaveCount(0);
	// On Search itself the button leads to the page's own field.
	await searchIn(page).click();
	await expect(page.getByRole('main').getByRole('searchbox', { name: 'Search' })).toBeFocused();
	await expect(field).toHaveCount(0);
	await expectAccessible(page);
});

test('the compact title shows once the large title has scrolled away, not before', async ({
	page
}) => {
	await signIn(page);
	await expect(page.locator('.tile img').first()).toBeVisible();
	const compact = page.locator('.compact');
	// The large title with the count under it
	const title = page
		.getByRole('main')
		.getByRole('heading', { name: 'Library', level: 1 })
		.locator('..');
	await expect(compact).toHaveCSS('opacity', '0');
	await page.evaluate(() => window.scrollBy(0, 400));
	// The large title has faded on its way out; on a laptop the compact one takes the
	// capsule's line while the capsule is away.
	await expect(compact).toHaveCSS('opacity', '1');
	await expect(title).toHaveCSS('opacity', '0');
	const box = (await compact.boundingBox())!;
	const width = page.viewportSize()!.width;
	expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThanOrEqual(1);
	if (wide(page)) {
		// Back up a little: the capsule returns and the compact title gives it its line.
		await page.evaluate(() => window.scrollBy(0, -40));
		await expect(compact).toHaveCSS('opacity', '0');
	}
	await page.evaluate(() => window.scrollTo(0, 0));
	await expect(compact).toHaveCSS('opacity', '0');
	await expect(title).toHaveCSS('opacity', '1');
});

test('shell: touch targets in the dock are at least 44 px both ways', async ({ page }) => {
	test.skip(!isPhone(page), 'the 44 px promise is for touch');
	await signIn(page);
	for (const name of ['Library', 'Collections', 'Search']) {
		const box = (await nav(page).getByRole('link', { name, exact: true }).boundingBox())!;
		expect(box.width).toBeGreaterThanOrEqual(44);
		expect(box.height).toBeGreaterThanOrEqual(56); // the dock is 64 px tall
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
