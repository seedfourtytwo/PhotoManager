/**
 * The per-account look (spec 2026-10-08 §5): an account chooses its mode in Settings; an
 * admin sets any account's look in Settings → People, trying it on their own screen first.
 */
import type { Browser, Locator, Page } from '@playwright/test';
import {
	ADMIN,
	MEMBER,
	expect,
	expectAccessible,
	isPhone,
	follow,
	loupe,
	resetMock,
	sheetStepGone,
	signIn,
	test,
	toast
} from './helpers.ts';

const root = (page: Page) => page.locator('html');
/** One of the three modes on You (a segmented control: pressed is chosen). */
const mode = (page: Page, label: string) =>
	page.getByRole('group', { name: 'Mode' }).getByRole('button', { name: label, exact: true });
const variable = (page: Page, name: string) =>
	page.evaluate((n) => document.documentElement.style.getPropertyValue(n), name);

/** Admin → People: the person's tile opens their sheet, whose Look card opens the form. */
async function openLookOf(page: Page, name: string) {
	await page
		.getByRole('region', { name: 'People' })
		.getByRole('button', { name: new RegExp(`^${name}\\b`) })
		.click();
	await page
		.getByRole('dialog', { name })
		.getByRole('button', { name: 'Look', exact: true })
		.click();
	const form = page.getByRole('dialog', { name: `Look for ${name}` });
	await expect(form.getByRole('combobox', { name: 'Theme', exact: true })).toBeVisible();
	return form;
}

/** The same account in another browser: nothing cached, only what the server holds. */
async function elsewhere(browser: Browser, baseURL: string | undefined, who: typeof ADMIN) {
	const context = await browser.newContext({ baseURL });
	const page = await context.newPage();
	await signIn(page, '/', who);
	return { page, close: () => context.close() };
}

/** The signed-in admin sets their own look through the API, as the form would. */
async function setMyLook(page: Page, sheet: Record<string, unknown>) {
	const status = await page.evaluate(async (body) => {
		const me = (await (await fetch('/api/auth/me')).json()) as { id: number };
		const saved = await fetch(`/api/admin/accounts/${me.id}/look`, {
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(body)
		});
		return saved.status;
	}, sheet);
	expect(status).toBe(200);
}

test('a member chooses light on You; it is on their account and painted before the app loads', async ({
	page,
	browser,
	baseURL
}) => {
	await resetMock();
	await signIn(page, '/settings/appearance', MEMBER);
	await expect(root(page)).toHaveAttribute('data-theme', 'dark');
	await expect(mode(page, 'Dark')).toHaveAttribute('aria-pressed', 'true');

	await mode(page, 'Light').click();
	await expect(root(page)).toHaveAttribute('data-theme', 'light');
	await expect
		.poll(async () => (await (await page.request.get('/api/me/look')).json()).mode)
		.toBe('light');
	await expectAccessible(page);

	// With the server out of reach, the cached look is still what the page opens in.
	await page.route('**/api/**', (route) => route.abort());
	await page.reload();
	await expect(root(page)).toHaveAttribute('data-theme', 'light');
	await page.unroute('**/api/**');

	// On the account, not in this browser: a browser that never saw it gets it too.
	const other = await elsewhere(browser, baseURL, MEMBER);
	await expect(root(other.page)).toHaveAttribute('data-theme', 'light');
	await other.close();

	// And only this account's: the admin is still dark.
	const admin = await elsewhere(browser, baseURL, ADMIN);
	await expect(root(admin.page)).toHaveAttribute('data-theme', 'dark');
	await admin.close();
});

test('following the device: light on a light device, dark on a dark one', async ({ page }) => {
	await resetMock();
	await page.emulateMedia({ colorScheme: 'light' });
	await signIn(page, '/settings/appearance', MEMBER);
	await mode(page, 'Auto').click();
	await expect(root(page)).not.toHaveAttribute('data-theme');
	const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
	await expect.poll(background).toBe('rgb(245, 245, 247)'); // --bg, light (themes.css)
	await page.emulateMedia({ colorScheme: 'dark' });
	await expect.poll(background).toBe('rgb(0, 0, 0)');
});

test('an admin tries a look for Partner on their own screen, stops, then saves it; Partner gets it', async ({
	page,
	browser,
	baseURL
}) => {
	await resetMock();
	await signIn(page, '/settings/people');
	let form = await openLookOf(page, MEMBER.name);
	await form.getByRole('checkbox', { name: 'Accent colour: the theme’s own' }).uncheck();
	await form.getByRole('slider', { name: 'Accent hue' }).fill('200');
	await form.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('album');
	expect(await variable(page, '--acc-h')).toBe(''); // nothing shows until it is tried

	await form.getByRole('button', { name: 'Try on my screen' }).click();
	await expect(root(page)).toHaveAttribute('data-look', 'album');
	expect(await variable(page, '--acc-h')).toBe('200');
	await expectAccessible(page);

	// The trial follows the admin around the app, with the way out on every page.
	await form.getByRole('button', { name: 'Cancel' }).click();
	const trial = page.getByRole('status').filter({ hasText: 'Trying a look for Partner' });
	await expect(trial).toBeVisible();
	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Library' })
		.click();
	await expect(page.locator('.tile img').first()).toBeVisible();
	await expect(trial).toBeVisible();
	await expect(root(page)).toHaveAttribute('data-look', 'album');
	// Nothing was saved: Partner still has the defaults.
	const before = await elsewhere(browser, baseURL, MEMBER);
	await expect(root(before.page)).not.toHaveAttribute('data-look');
	await before.close();

	await trial.getByRole('button', { name: 'Stop trying' }).click();
	await expect(trial).toHaveCount(0);
	await expect(root(page)).not.toHaveAttribute('data-look');
	expect(await variable(page, '--acc-h')).toBe('');

	await page.goto('/settings/people');
	form = await openLookOf(page, MEMBER.name);
	await form.getByRole('checkbox', { name: 'Accent colour: the theme’s own' }).uncheck();
	await form.getByRole('slider', { name: 'Accent hue' }).fill('200');
	await form.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('album');
	await form.getByRole('button', { name: 'Try on my screen' }).click();
	await form.getByRole('button', { name: 'Save for Partner' }).click();
	await expect(toast(page)).toContainText('Saved the look for Partner');
	await expect(form).toHaveCount(0);
	// Saving for someone else ends the trial and leaves the admin's own look alone.
	await expect(root(page)).not.toHaveAttribute('data-look');
	expect(await variable(page, '--acc-h')).toBe('');

	const after = await elsewhere(browser, baseURL, MEMBER);
	await expect(root(after.page)).toHaveAttribute('data-look', 'album');
	await expect.poll(() => variable(after.page, '--acc-h')).toBe('200');
	await after.close();
});

test('a trial ends when the page is reloaded', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings/people');
	const form = await openLookOf(page, MEMBER.name);
	await form.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('album');
	await form.getByRole('button', { name: 'Try on my screen' }).click();
	await expect(root(page)).toHaveAttribute('data-look', 'album');
	await page.reload();
	await expect(page.getByRole('region', { name: 'People' })).toBeVisible();
	await expect(root(page)).not.toHaveAttribute('data-look');
	await expect(page.getByText('Trying a look')).toHaveCount(0);
});

test('a trial ends when the admin signs out: the next person does not get it', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings/people');
	const form = await openLookOf(page, MEMBER.name);
	await form.getByRole('combobox', { name: 'Theme', exact: true }).selectOption('album');
	await form.getByRole('button', { name: 'Try on my screen' }).click();
	await form.getByRole('button', { name: 'Cancel' }).click();
	await expect(root(page)).toHaveAttribute('data-look', 'album');
	await sheetStepGone(page); // the form's history step is taken back first
	await follow(page, '/settings'); // to You, without a reload (a reload ends a trial too)
	await page.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login$/); // the app went there itself: no reload
	await expect(root(page)).not.toHaveAttribute('data-look');
});

test('a member has no way to anyone’s look but their mode', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings/appearance', MEMBER);
	await expect(page.getByRole('group', { name: 'Mode' }).getByRole('button')).toHaveCount(3);
	await expect(page.getByRole('button', { name: 'Look', exact: true })).toHaveCount(0);
	const answers = await page.evaluate(async () => {
		const put = (url: string, body: unknown) =>
			fetch(url, {
				method: 'PUT',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			}).then((r) => r.status);
		return [
			await put('/api/me/look', { mode: 'light', accentHue: 200 }),
			await put('/api/me/look', { theme: 'album' }),
			await put('/api/admin/accounts/1/look', { theme: 'album' }),
			(await fetch('/api/admin/accounts/1/look')).status
		];
	});
	expect(answers).toEqual([422, 422, 403, 403]);
});

test('the switches: Collections rows in the look’s order, dock words on or off', async ({
	page
}) => {
	await resetMock();
	await signIn(page, '/collections');
	const rows = page.getByRole('main').getByRole('listitem');
	await expect(rows).toHaveText([/^People/, /^Places/, /^Albums/]);
	const library = page.getByRole('navigation', { name: 'Main' }).getByRole('link', {
		name: 'Library'
	});
	const wordWidth = () =>
		library.locator('span').evaluate((el) => el.getBoundingClientRect().width);
	expect(await wordWidth()).toBeGreaterThan(20);

	await setMyLook(page, { collectionsRows: ['albums', 'people'], dockLabels: false, photoGap: 8 });
	await page.reload();
	await expect(rows).toHaveText([/^Albums/, /^People/]);
	await expect(library).toBeVisible(); // still named for screen readers either way
	if (isPhone(page)) await expect.poll(wordWidth).toBeLessThanOrEqual(1);
	else expect(await wordWidth()).toBeGreaterThan(20); // the switch is about the phone dock
	await expectAccessible(page);

	// The gap dial reaches the photo grid.
	await library.click();
	const tiles = page.locator('.tile');
	await expect(tiles.nth(1)).toBeVisible();
	const first = (await tiles.nth(0).boundingBox())!;
	const second = (await tiles.nth(1).boundingBox())!;
	expect(Math.round(second.x - (first.x + first.width))).toBe(8);
});

test('text size and corners reach the page', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	const size = () =>
		page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
	const normal = await size();
	await setMyLook(page, { textScale: 1.25, corners: 0 });
	await page.reload();
	await expect.poll(size).toBeCloseTo(normal * 1.25, 1);
	const radius = await page
		.getByRole('button', { name: 'Change PIN' })
		.evaluate((el) => getComputedStyle(el).borderRadius);
	expect(radius).toBe('0px');
});

// DESIGN_PRINCIPLES §1.1: the corners dial rounds controls and surfaces, never a photo.
test('photos stay square-cornered with the corners dial at its most', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	await setMyLook(page, { corners: 22 });
	await page.goto('/');
	const radius = (target: Locator) => target.evaluate((el) => getComputedStyle(el).borderRadius);

	const tile = page.locator('.tile').first();
	await expect(tile).toBeVisible();
	expect(await radius(tile)).toBe('0px');
	expect(await radius(tile.locator('img').first())).toBe('0px');

	await tile.click();
	const photo = loupe(page).locator('img.photo').first();
	await expect(photo).toBeVisible();
	expect(await radius(photo)).toBe('0px');

	await page.goto('/albums');
	const cover = page.locator('.cover').first();
	await expect(cover).toBeVisible();
	expect(await radius(cover)).toBe('0px');
	expect(await radius(cover.locator('img'))).toBe('0px');
	// …while a control does take the dial.
	expect(await radius(page.getByRole('button', { name: 'New album' }))).not.toBe('0px');
});

test('the old per-browser theme setting moves to the account once, then is gone', async ({
	page,
	context
}) => {
	await resetMock();
	// As left by the app before this change; set once, so its removal can be seen.
	await context.addInitScript(() => {
		if (sessionStorage.getItem('seeded')) return;
		sessionStorage.setItem('seeded', '1');
		localStorage.setItem('pa.theme', 'light');
	});
	await page.goto('/login');
	await expect(root(page)).toHaveAttribute('data-theme', 'light'); // honoured before sign-in
	await signIn(page, '/settings/appearance', MEMBER);
	await expect(mode(page, 'Light')).toHaveAttribute('aria-pressed', 'true');
	await expect
		.poll(async () => (await (await page.request.get('/api/me/look')).json()).mode)
		.toBe('light');
	await expect.poll(() => page.evaluate(() => localStorage.getItem('pa.theme'))).toBeNull();
});

test('the old per-browser setting does not overwrite a mode chosen on another device', async ({
	page,
	context,
	browser,
	baseURL
}) => {
	await resetMock();
	const phone = await elsewhere(browser, baseURL, MEMBER);
	await phone.page.goto('/settings/appearance');
	await mode(phone.page, 'Auto').click();
	await expect
		.poll(async () => (await (await phone.page.request.get('/api/me/look')).json()).mode)
		.toBe('system');
	await phone.close();

	await context.addInitScript(() => {
		if (sessionStorage.getItem('seeded')) return;
		sessionStorage.setItem('seeded', '1');
		localStorage.setItem('pa.theme', 'light');
	});
	await signIn(page, '/settings/appearance', MEMBER);
	await expect(mode(page, 'Auto')).toHaveAttribute('aria-pressed', 'true');
	await expect.poll(() => page.evaluate(() => localStorage.getItem('pa.theme'))).toBeNull();
	expect((await (await page.request.get('/api/me/look')).json()).mode).toBe('system');
});

test('a photo size once chosen on this device is gone: the look gives the size again', async ({
	page,
	context
}) => {
	await resetMock();
	// As left by the app before this change; set once, so its removal can be seen.
	await context.addInitScript(() => {
		if (sessionStorage.getItem('seeded')) return;
		sessionStorage.setItem('seeded', '1');
		localStorage.setItem('pa.density', 'large');
	});
	await signIn(page, '/settings/appearance');
	await expect(page.getByRole('group', { name: 'Mode' })).toBeVisible();
	await expect(page.getByRole('group', { name: /Photo size/ })).toHaveCount(0);
	await expect.poll(() => page.evaluate(() => localStorage.getItem('pa.density'))).toBeNull();

	// Rows are justified, so one tile's height says little: the middle one of the first twenty.
	const tiles = page.locator('.tile');
	const height = () =>
		tiles.evaluateAll((all) => {
			const heights = all.slice(0, 20).map((tile) => tile.getBoundingClientRect().height);
			return heights.sort((a, b) => a - b)[Math.floor(heights.length / 2)] ?? 0;
		});
	await page.goto('/');
	await expect(tiles.nth(19)).toBeVisible();
	const medium = await height();
	await setMyLook(page, { thumbSize: 'large' });
	await page.reload();
	await expect.poll(height).toBeGreaterThan(medium * 1.2);
	await setMyLook(page, { thumbSize: 'small' });
	await page.reload();
	await expect.poll(height).toBeLessThan(medium * 0.9);
});

test('on a shared device the next person does not get the last one’s look', async ({ page }) => {
	await resetMock();
	await signIn(page, '/settings');
	await setMyLook(page, { theme: 'album', mode: 'light', accentHue: 200 });
	await page.reload();
	await expect(root(page)).toHaveAttribute('data-look', 'album');
	await expect.poll(() => variable(page, '--acc-h')).toBe('200');

	await page.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL(/\/login$/);
	// gone from the sign-in page, and from what the next opening would paint
	await expect(root(page)).not.toHaveAttribute('data-look');
	await expect(root(page)).toHaveAttribute('data-theme', 'dark');
	expect(await variable(page, '--acc-h')).toBe('');
	expect(await page.evaluate(() => localStorage.getItem('pa.look'))).toBeNull();

	// Partner signs in while the server cannot say what their look is: the defaults, not the admin's.
	await page.route('**/api/me/look', (route) => route.abort());
	await signIn(page, '/settings/appearance', MEMBER);
	await expect(mode(page, 'Dark')).toHaveAttribute('aria-pressed', 'true');
	await expect(root(page)).not.toHaveAttribute('data-look');
	expect(await variable(page, '--acc-h')).toBe('');
});

test('a session that ended elsewhere takes the look with it', async ({ page, context }) => {
	await resetMock();
	await signIn(page, '/settings');
	await setMyLook(page, { theme: 'album' });
	await page.reload();
	await expect(root(page)).toHaveAttribute('data-look', 'album');

	await context.clearCookies(); // as if the session ran out
	await page.reload();
	await expect(page).toHaveURL(/\/login/);
	await expect(root(page)).not.toHaveAttribute('data-look');
	expect(await page.evaluate(() => localStorage.getItem('pa.look'))).toBeNull();
});
