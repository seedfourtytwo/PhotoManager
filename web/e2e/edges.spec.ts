/**
 * The whole screen of an iPhone: the page reaches under the clock, the notch and the home bar,
 * and nothing to read or press sits under them. The insets are given to the browser here, as
 * a phone with a notch reports them.
 */
import type { Locator, Page } from '@playwright/test';
import {
	expect,
	follow,
	isPhone,
	loupe,
	resetMock,
	selectTiles,
	selectionAction,
	signIn,
	test
} from './helpers.ts';

type Insets = { top: number; right: number; bottom: number; left: number };
const UPRIGHT: Insets = { top: 47, right: 0, bottom: 34, left: 0 };
const ON_ITS_SIDE: Insets = { top: 0, right: 47, bottom: 21, left: 47 };

async function withInsets(page: Page, insets: Insets) {
	const cdp = await page.context().newCDPSession(page);
	await cdp.send('Emulation.setSafeAreaInsetsOverride', { insets });
}

/** The piece lies wholly inside what the notch and the bars leave free. */
async function expectClear(page: Page, piece: Locator, insets: Insets) {
	await expect(piece).toBeVisible();
	const box = (await piece.boundingBox())!;
	const screen = page.viewportSize()!;
	expect(box.y).toBeGreaterThanOrEqual(insets.top);
	expect(box.x).toBeGreaterThanOrEqual(insets.left);
	expect(box.x + box.width).toBeLessThanOrEqual(screen.width - insets.right);
	expect(box.y + box.height).toBeLessThanOrEqual(screen.height - insets.bottom);
}

test.beforeEach(async ({ page }) => {
	test.skip(!isPhone(page), 'a phone has the notch and the home bar');
	await resetMock();
});

test('edges: the page asks for the whole screen', async ({ page }) => {
	await page.goto('/login');
	await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
		'content',
		/viewport-fit=cover/
	);
});

// prettier-ignore
const PAGES = ['/home', '/', '/collections', '/search', '/settings', '/settings/appearance', '/settings/overview', '/settings/folders', '/settings/backups', '/settings/people', '/albums', '/people', '/map', '/calendar', '/trash', '/review'];

// A page even a little wider than the screen slides sideways under the finger, and on a phone
// that is the whole app wobbling; Chrome shrinks it instead and the dock sinks into the home bar.
test('edges: no page is wider than the screen', async ({ page }) => {
	await withInsets(page, UPRIGHT);
	await signIn(page);
	const screen = page.viewportSize()!.width;
	const tooWide: string[] = [];
	for (const path of PAGES) {
		await follow(page, path);
		await expect(page).toHaveURL(new RegExp(`${path}$`));
		await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
		await page.waitForLoadState('networkidle');
		const wide = await page.evaluate(() => document.documentElement.scrollWidth);
		if (wide > screen) tooWide.push(`${path}: ${wide} px`);
	}
	expect(tooWide).toEqual([]);
});

for (const [name, insets, size] of [
	['upright', UPRIGHT, { width: 390, height: 844 }],
	['on its side', ON_ITS_SIDE, { width: 844, height: 390 }]
] as const) {
	test(`edges, ${name}: the library, its dock and the sign-in clear the notch and the home bar`, async ({
		page
	}) => {
		await page.setViewportSize(size);
		await withInsets(page, insets);
		await page.goto('/login');
		await expectClear(page, page.getByRole('heading', { level: 1 }), insets);
		await signIn(page);
		const nav = page.getByRole('navigation', { name: 'Main' });
		for (const link of await nav.getByRole('link').all()) await expectClear(page, link, insets);
		await expectClear(page, page.getByRole('heading', { level: 1 }), insets);
		// A month heading sticks under the clock, not behind it, and under the page's compact
		// title, which is a touch target (44 px) tall.
		const sticks = await page
			.getByRole('main')
			.getByRole('heading', { level: 2 })
			.first()
			.evaluate((h) => parseFloat(getComputedStyle(h).top));
		expect(sticks).toBe(insets.top + 44);
	});

	test(`edges, ${name}: the photo view's pills and bar clear the notch and the home bar`, async ({
		page
	}) => {
		await page.setViewportSize(size);
		await withInsets(page, insets);
		await signIn(page);
		await page.locator('.tile').first().click();
		const viewer = loupe(page);
		for (const label of ['Close', 'Details', 'Zoom', 'Favourite', 'More'])
			await expectClear(page, viewer.getByRole('button', { name: label }), insets);
		// The photo itself has the whole screen: it runs under the notch and the bars.
		const stage = (await viewer.locator('.stage').boundingBox())!;
		expect(stage.x).toBe(0);
		expect(stage.width).toBe(size.width);
	});
}

/**
 * Where what scrolls in an element ends on the screen: the bottom of its scrolling area, inside
 * its bottom border. (`clientHeight` is rounded to whole pixels; the box is not.)
 */
const scrollEnd = (scroller: Locator) =>
	scroller.evaluate(
		(e) => e.getBoundingClientRect().bottom - parseFloat(getComputedStyle(e).borderBottomWidth)
	);

// Opened from the Home Screen an iPhone 15 gives the page all of its screen, the home bar
// included; Safari's own toolbar no longer covers that strip. Upright a filter or a dialog is a
// bottom sheet; on its side a filter hangs under its chip and a dialog sits in the middle.
for (const [name, insets, size] of [
	['upright', { top: 59, right: 0, bottom: 34, left: 0 }, { width: 393, height: 852 }],
	['on its side', { top: 0, right: 59, bottom: 21, left: 59 }, { width: 852, height: 393 }]
] as const) {
	async function fromHomeScreen(page: Page) {
		await page.setViewportSize(size);
		await withInsets(page, insets);
		await page.addInitScript(() =>
			Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true })
		);
		await signIn(page);
	}

	test(`edges, from the Home Screen, ${name}: a filter sheet shows nothing under the home bar`, async ({
		page
	}) => {
		await fromHomeScreen(page);
		await page
			.getByRole('group', { name: 'Filters' })
			.getByRole('button', { name: 'When', exact: true })
			.click();
		const sheet = page.getByRole('dialog', { name: 'When' });
		await expect.poll(() => sheet.evaluate((d) => d.getAnimations().length)).toBe(0);
		// What scrolls in the sheet stops above the home bar…
		await expectClear(page, sheet.locator('.body'), insets);
		// …and its last fields scroll up clear of it.
		const to = sheet.getByLabel('To', { exact: true });
		await to.scrollIntoViewIfNeeded();
		await expectClear(page, to, insets);
	});

	test(`edges, from the Home Screen, ${name}: a dialog taller than the screen shows nothing under the home bar`, async ({
		page
	}) => {
		await fromHomeScreen(page);
		await selectTiles(page, [1, 2]);
		await selectionAction(page, 'Download');
		const dialog = page.getByRole('dialog', { name: 'Download' });
		await dialog.getByRole('button', { name: 'More options' }).click();
		await expect.poll(() => dialog.evaluate((d) => d.getAnimations().length)).toBe(0);
		// What it holds is taller than the screen leaves it, so it scrolls…
		const body = dialog.locator('.body');
		expect(await body.evaluate((d) => d.scrollHeight > d.clientHeight)).toBe(true);
		// …and the sheet, what scrolls in it included, stops above the home bar…
		expect(await scrollEnd(dialog)).toBeLessThanOrEqual(size.height - insets.bottom);
		await expectClear(page, body, insets);
		// …and its actions are clear of it without scrolling: they never scroll away.
		await expectClear(page, dialog.getByRole('button', { name: 'Download', exact: true }), insets);
		await expectClear(page, dialog.getByRole('button', { name: 'Cancel' }), insets);
	});
}
